import argparse
import json
import time

from app.buckets import projection
from app.services import neo4j


def main():
    parser = argparse.ArgumentParser(description="Graph schema, backfill, incremental delivery and reconciliation")
    parser.add_argument(
        "command", choices=["init", "backfill", "reconcile", "rebuild", "incremental", "status", "retry-dead", "worker"]
    )
    parser.add_argument("--generation", type=int)
    args = parser.parse_args()
    if args.command == "init":
        neo4j.initialize()
    elif args.command in ("backfill", "reconcile"):
        print(json.dumps(projection.backfill()))
    elif args.command == "rebuild":
        print(json.dumps(projection.rebuild(args.generation)))
    elif args.command == "incremental":
        print(json.dumps(projection.incremental()))
    elif args.command == "status":
        print(json.dumps(projection.status()))
    elif args.command == "retry-dead":
        from app.buckets.db import execute, rows, transaction

        with transaction() as core:
            sites = [None] + [row["site_id"] for row in rows(core, "SELECT site_id FROM site_registry WHERE active")]
        for site in sites:
            with transaction(site) as connection:
                execute(
                    connection,
                    "UPDATE app_delivery SET status='pending',attempts=0,available_at=now() WHERE status='dead'",
                )
    else:
        neo4j.initialize()
        while True:
            try:
                print(json.dumps(projection.incremental()), flush=True)
            except Exception as error:
                print(json.dumps({"error_code": type(error).__name__}), flush=True)
            time.sleep(5)


if __name__ == "__main__":
    main()
