"""Freeze an additive PostgreSQL index change as a new transactional SQL migration."""

import argparse
import json
import os
import tempfile
from contextlib import closing
from pathlib import Path

from pydantic import ValidationError

from app.services.index_config import CATALOG_PATH, DATABASE_DIR, load_catalog
from app.services.index_postgres import create_sql, plan_postgres
from app.services.index_releases import release_catalog


def require_additive(previous, desired):
    current = {(i.schema_name, i.name): i for i in desired.postgresql}
    for old in previous.postgresql:
        new = current.get((old.schema_name, old.name))
        if new is None or new != old:
            raise ValueError(
                f"Removing/replacing {old.name} requires an explicit reviewed SQL migration; "
                "automatic generation is additive"
            )


def generate(connection, catalog, database_dir=DATABASE_DIR):
    root = Path(database_dir)
    previous = release_catalog(connection, root)
    require_additive(previous, catalog)
    plan = plan_postgres(connection, catalog)
    if any(i["status"] == "conflict" for i in plan["indexes"]):
        raise ValueError("PostgreSQL index conflict; inspect plan before generating SQL")
    old_ids = {(i.schema_name, i.name) for i in previous.postgresql}
    additions = [i for i in catalog.postgresql if (i.schema_name, i.name) not in old_ids]
    missing = {(i["schema"], i["name"]) for i in plan["indexes"] if i["status"] == "missing"}
    # No DDL is needed merely to move an existing matching declaration to JSON.
    if not additions and not missing:
        return {"generated": False, "reason": "No PostgreSQL index changes"}
    if any(i.managed_by != "application" for i in additions):
        raise ValueError("New constraint definitions must use a schema migration")
    files = sorted((root / "04_migrations").glob("[0-9][0-9][0-9]_*.sql"))
    with connection.cursor() as cursor:
        cursor.execute("SELECT version FROM public.schema_migrations ORDER BY version")
        applied = [r[0] for r in cursor.fetchall()]
    if applied != [p.name[:3] for p in files]:
        raise ValueError("Apply existing migrations before generating another index migration")
    version = int(files[-1].name[:3]) + 1
    if version > 999:
        raise ValueError("Migration version exceeds existing runner format")
    version = f"{version:03d}"
    snapshot = root / "indexing/snapshots" / (catalog.revision + ".json")
    if snapshot.exists() or catalog.revision == previous.revision:
        raise ValueError("Choose a new revision before generating a changed index catalog")
    specs = [i for i in catalog.postgresql if (i.schema_name, i.name) in missing]
    if not specs:
        raise ValueError("New definitions already exist outside release history; review adoption explicitly")
    sql = f"-- index-catalog: {catalog.revision} {catalog.digest()}\n"
    sql += "-- Generated from a frozen JSON snapshot. Do not edit after applying.\n"
    sql += "\n".join(create_sql(i) for i in specs) + "\n"
    target = root / "04_migrations" / f"{version}_indexes_{catalog.revision}.sql"
    releases_path = root / "indexing/releases.json"
    releases = json.loads(releases_path.read_text())
    releases.append({"migration": version, "revision": catalog.revision, "sha256": catalog.digest()})
    created = []
    temporary = None
    try:
        for path, content in ((snapshot, json.dumps(catalog.payload(), indent=2) + "\n"), (target, sql)):
            with path.open("x", encoding="utf-8") as stream:
                created.append(path)
                stream.write(content)
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=releases_path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(json.dumps(releases, indent=2) + "\n")
        os.replace(temporary, releases_path)
    except BaseException:
        for path in created:
            path.unlink(missing_ok=True)
        if temporary:
            temporary.unlink(missing_ok=True)
        raise
    return {
        "generated": True,
        "migration": target.name,
        "revision": catalog.revision,
        "sha256": catalog.digest(),
        "indexes": [i.name for i in specs],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=CATALOG_PATH)
    args = parser.parse_args()
    try:
        catalog = load_catalog(args.catalog)
        from scripts.migrate import connect

        with closing(connect()) as connection:
            connection.set_session(readonly=True)
            result = {"result": "PASS", **generate(connection, catalog)}
    except ValidationError:
        result = {"result": "FAIL", "error": "Invalid catalog or database configuration"}
    except (ValueError, OSError) as error:
        result = {"result": "FAIL", "error": str(error)}
    except Exception as error:
        result = {
            "result": "FAIL",
            "error_type": type(error).__name__,
            "error": "Database operation failed; check connectivity and privileges",
        }
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["result"] == "PASS" else 1)


if __name__ == "__main__":
    main()
