"""Read-only integrity audit. DSNs are supplied in environment, never written to evidence."""

import argparse
import hashlib
import json
import os
from collections import Counter
from contextlib import ExitStack, closing
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor

from app.services.fragment_router import load_contract


def read(connection, statement):
    with connection.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(statement)
        return [dict(row) for row in cursor.fetchall()]


def canonical(rows):
    return Counter(json.dumps(row, sort_keys=True, default=str) for row in rows)


def audit(connections, reference=None):
    contract = load_contract()
    states, fragments, checks = {}, {}, {}
    for site, connection in connections.items():
        state = read(connection, "SELECT * FROM v_fragment_identity")
        contract.validate_state(state[0] if len(state) == 1 else {}, site)
        states[site] = state[0]
        fragments[site] = {table: read(connection, f"SELECT * FROM {table}") for table in ("product", "product_image")}
        owners = {r["seller_id"]: r["site_id"] for r in read(connection, "SELECT * FROM seller_site")}
        products = fragments[site]["product"]
        product_ids = {p["product_id"] for p in products}
        checks[site + "_ownership"] = all(
            p["site_id"] == site == owners.get(p["seller_id"]) and contract.product_site(p["product_id"]) == site
            for p in products
        )
        checks[site + "_derived"] = all(
            i["product_id"] in product_ids and i["image_id"] > 0 and i["image_id"] % 2 == state[0]["id_remainder"]
            for i in fragments[site]["product_image"]
        )
        missing = read(
            connection,
            """SELECT count(*) AS n FROM user_core c
            LEFT JOIN user_profile p USING(user_id) LEFT JOIN user_secret s USING(user_id)
            LEFT JOIN user_wallet w USING(user_id)
            WHERE p.user_id IS NULL OR s.user_id IS NULL OR w.user_id IS NULL""",
        )[0]["n"]
        checks[site + "_vertical_rows"] = missing == 0
        columns = {
            table: {
                r["column_name"]
                for r in read(
                    connection,
                    "SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name='"
                    + table
                    + "'",
                )
            }
            for table in ("user_core", "user_profile", "user_secret", "user_wallet", "users_full")
        }
        sets = [columns[t] for t in ("user_core", "user_profile", "user_secret", "user_wallet")]
        checks[site + "_vertical_columns"] = set.union(*sets) == columns["users_full"] and all(
            left & right == {"user_id"} for pos, left in enumerate(sets) for right in sets[pos + 1 :]
        )
    checks["reference_copies"] = states["A"]["reference_sha256"] == states["B"]["reference_sha256"]
    summaries = {}
    for table, view, key in (("product", "v_product", "product_id"), ("product_image", "v_product_image", "image_id")):
        a, b = fragments["A"][table], fragments["B"][table]
        union = a + b
        checks[table + "_disjoint"] = not ({r[key] for r in a} & {r[key] for r in b})
        checks[table + "_reconstruction"] = canonical(read(connections["A"], f"SELECT * FROM {view}")) == canonical(
            union
        )
        if reference is not None:
            checks[table + "_independent_completeness"] = canonical(union) == canonical(reference[table])
        summaries[table] = {
            "A": len(a),
            "B": len(b),
            "global": len(union),
            "sha256": hashlib.sha256(json.dumps(sorted(canonical(union).items())).encode()).hexdigest(),
        }
    return {
        "result": "PASS" if all(checks.values()) else "FAIL",
        "read_only": True,
        "independent_reference_checked": reference is not None,
        "checks": checks,
        "rows": summaries,
        "limitations": [
            "Independent completeness requires --reference captured from the source before fragmentation",
            "Separate DB snapshots do not form an atomic global snapshot; audit during a controlled write pause",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        with ExitStack() as stack:
            connections = {}
            for site in "AB":
                connection = stack.enter_context(
                    closing(psycopg2.connect(os.environ[f"FRAGMENT_SITE_{site}_DSN"], connect_timeout=3))
                )
                connection.set_session(readonly=True, isolation_level="REPEATABLE READ")
                with connection.cursor() as cursor:
                    cursor.execute("SET LOCAL statement_timeout='30s'")
                connections[site] = connection
            report = audit(connections, json.loads(args.reference.read_text()) if args.reference else None)
    except (KeyError, ValueError, OSError, psycopg2.Error) as error:
        report = {
            "result": "FAIL",
            "error_type": type(error).__name__,
            "error": "Audit failed; inspect contract, permissions, connectivity and reference input",
        }
    output = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output)
    print(output, end="")
    raise SystemExit(0 if report["result"] == "PASS" else 1)


if __name__ == "__main__":
    main()
