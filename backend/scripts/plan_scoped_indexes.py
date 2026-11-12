"""Read-only PG index planning by explicit deployment scope; no DSNs in reports."""

import argparse
import json
import os
from contextlib import closing

import psycopg2

from app.services.index_config import DATABASE_DIR, IndexCatalog, load_catalog, no_duplicates
from app.services.index_postgres import plan_postgres


def scoped_catalog(catalog, tables):
    if tables != "*" and (not isinstance(tables, list) or not tables or any(type(t) is not str for t in tables)):
        raise ValueError("Scope tables must be '*' or a nonempty list")
    available = {i.table for i in catalog.postgresql}
    if tables != "*" and not set(tables).issubset(available):
        raise ValueError("Unknown scope table")
    return IndexCatalog(
        schema_version=1,
        revision=catalog.revision,
        postgresql=[i for i in catalog.postgresql if tables == "*" or i.table in tables],
        mongodb=[],
    )


def plan_scopes(catalog, scopes, *, verify=False):
    reports = {}
    for name, spec in scopes.items():
        selected = scoped_catalog(catalog, spec["tables"])
        try:
            dsn = os.environ[spec["dsn_env"]]
            with closing(psycopg2.connect(dsn, connect_timeout=3)) as connection:
                connection.set_session(readonly=True)
                with connection.cursor() as cursor:
                    cursor.execute("SET LOCAL statement_timeout='15s'")
                plan = plan_postgres(connection, selected)
            ok = all(i["status"] == "matched" if verify else i["status"] != "conflict" for i in plan["indexes"])
            reports[name] = {"result": "PASS" if ok else "FAIL", "scope_sha256": selected.digest(), **plan}
        except (KeyError, psycopg2.Error) as error:
            reports[name] = {
                "result": "FAIL",
                "error_type": type(error).__name__,
                "error": "Scope unavailable; check DSN environment, connectivity and privileges",
            }
    return {
        "result": "PASS" if all(v["result"] == "PASS" for v in reports.values()) else "FAIL",
        "read_only": True,
        "desired_revision": catalog.revision,
        "desired_sha256": catalog.digest(),
        "scopes": reports,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scope", action="append", choices=["commerce", "site-a", "site-b"], required=True)
    parser.add_argument("--verify", action="store_true", help="Missing indexes fail verification")
    args = parser.parse_args()
    config = json.loads((DATABASE_DIR / "indexing/scopes.json").read_text(), object_pairs_hook=no_duplicates)
    if config["schema_version"] != 1:
        raise ValueError("Unsupported scope version")
    result = plan_scopes(load_catalog(), {n: config["postgresql"][n] for n in args.scope}, verify=args.verify)
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["result"] == "PASS" else 1)


if __name__ == "__main__":
    main()
