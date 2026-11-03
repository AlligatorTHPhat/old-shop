"""Validate, plan, apply and verify JSON-defined indexes for each database independently."""

import argparse
import json
from contextlib import closing
from pathlib import Path

from pydantic import ValidationError

from app.services.index_config import CATALOG_PATH, load_catalog


def successful(plan):
    return all(i["status"] == "matched" for i in plan["indexes"])


def execute(command, engine="all", catalog_path=CATALOG_PATH, desired=False):
    catalog = None if command == "verify" and not desired else load_catalog(catalog_path)
    result = {"command": command, "engines": {}}
    if catalog is not None:
        result.update(desired_revision=catalog.revision, desired_sha256=catalog.digest())
    if command == "validate":
        return {
            "result": "PASS",
            **result,
            "counts": {"postgresql": len(catalog.postgresql), "mongodb": len(catalog.mongodb)},
        }
    engines = ["postgresql", "mongodb"] if engine == "all" else [engine]
    # Preflight both engines before applying either. No DDL or validator changes here.
    if command == "apply":
        for name in engines:
            preflight = execute("plan", name, catalog_path)
            if preflight["result"] != "PASS":
                return {
                    "result": "FAIL",
                    **result,
                    "error": "Index preflight failed; inspect report",
                    "preflight": preflight,
                }
    for name in engines:
        try:
            if name == "postgresql":
                from app.services.index_postgres import plan_postgres
                from app.services.index_releases import release_catalog
                from scripts.migrate import connect, run_migrations

                with closing(connect()) as connection:
                    connection.set_session(readonly=True)
                    selected = release_catalog(connection) if command == "verify" and not desired else catalog
                    if command == "apply":
                        from scripts.generate_index_migration import require_additive

                        applied_before = release_catalog(connection)
                        require_additive(applied_before, catalog)
                    plan = plan_postgres(connection, selected)
                    if command == "apply" and successful(plan) and applied_before.postgresql != catalog.postgresql:
                        raise ValueError(
                            "New PostgreSQL definitions already exist outside release history; "
                            "review adoption explicitly"
                        )
                if command == "apply" and not successful(plan):
                    from app.services.index_config import DATABASE_DIR

                    releases = json.loads((DATABASE_DIR / "indexing/releases.json").read_text())
                    candidates = [
                        load_catalog(DATABASE_DIR / "indexing/snapshots" / (r["revision"] + ".json"))
                        for r in releases
                        if r["revision"] == catalog.revision and r["sha256"] == catalog.digest()
                    ]
                    if not candidates:
                        raise ValueError("Generate and review a migration for this catalog before PostgreSQL apply")
                    run_migrations()
                    with closing(connect()) as connection:
                        connection.set_session(readonly=True)
                        applied = release_catalog(connection)
                        if applied.digest() != catalog.digest():
                            raise ValueError("Applied PostgreSQL snapshot differs from desired catalog")
                        plan = plan_postgres(connection, catalog)
                result["engines"][name] = {"revision": selected.revision, "sha256": selected.digest(), **plan}
            else:
                from app.services.index_mongo import applied_mongo_catalog, apply_mongo, plan_mongo
                from app.services.mongo import get_database

                database = get_database()
                selected = applied_mongo_catalog(database) if command == "verify" and not desired else catalog
                plan = apply_mongo(database, selected) if command == "apply" else plan_mongo(database, selected)
                result["engines"][name] = {"revision": selected.revision, "sha256": selected.digest(), **plan}
        except ValidationError:
            return {"result": "FAIL", **result, "failed_engine": name, "error": "Invalid database configuration"}
        except ValueError as error:
            return {"result": "FAIL", **result, "failed_engine": name, "error": str(error)}
        except Exception as error:
            # Driver exceptions can contain connection details; keep output safe.
            return {
                "result": "FAIL",
                **result,
                "failed_engine": name,
                "error_type": type(error).__name__,
                "error": "Database operation failed; check connectivity, privileges and index/data compatibility",
            }
    ok = all(
        not any(i["status"] == "conflict" for i in p["indexes"]) if command == "plan" else successful(p)
        for p in result["engines"].values()
    )
    return {"result": "PASS" if ok else "FAIL", **result}


def main(default_command=None):
    parser = argparse.ArgumentParser(description=__doc__)
    if default_command is None:
        parser.add_argument("command", choices=["validate", "plan", "apply", "verify"])
    parser.add_argument("--engine", choices=["all", "postgresql", "mongodb"], default="all")
    parser.add_argument("--catalog", type=Path, default=CATALOG_PATH)
    parser.add_argument(
        "--desired", action="store_true", help="Verify the proposed catalog instead of the applied snapshot"
    )
    parser.add_argument("--output", type=Path, help="Write the JSON report as well as printing it")
    args = parser.parse_args()
    try:
        result = execute(default_command or args.command, args.engine, args.catalog, args.desired)
    except ValidationError as error:
        result = {
            "result": "FAIL",
            "errors": [
                {"location": list(e["loc"]), "message": e["msg"]}
                for e in error.errors(include_input=False, include_url=False)
            ],
        }
    except (ValueError, OSError) as error:
        result = {"result": "FAIL", "error": str(error)}
    output = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output)
    print(output, end="")
    raise SystemExit(0 if result["result"] == "PASS" else 1)


if __name__ == "__main__":
    main()
