"""Measure existing application data without generating rows or changing indexes.

Run from backend/: python -m scripts.benchmark_current --output ../docs/benchmark
The output directory must not exist. PostgreSQL uses one repeatable-read, read-only
transaction; MongoDB uses only count/find/listIndexes/explain/buildInfo commands.
"""

import argparse
import hashlib
import json
import statistics
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from psycopg2 import sql

from app.schemas.documents import DOCUMENT_MODELS
from app.services.mongo import get_database
from scripts.migrate import connect


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def one(cursor, query, params=()):
    cursor.execute(query, params)
    return cursor.fetchone()


def pg_cases(cursor):
    """Choose filters from rows that actually exist; empty tables are not padded."""
    cases = {}

    def add(name, query, params=(), reason=None):
        cases[name] = {"query": query, "parameters": params, "skip_reason": reason}

    visible = (
        " FROM product p JOIN category c USING(category_id) WHERE p.status=1 "
        "AND NOT p.is_deleted AND NOT c.is_deleted AND c.is_active"
    )
    catalogue = "SELECT p.product_id,p.title,p.price" + visible
    ordering = " ORDER BY p.created_at DESC,p.product_id ASC LIMIT 100"
    product = one(cursor, "SELECT p.product_id,p.category_id,p.title" + visible + " ORDER BY p.product_id LIMIT 1")
    empty = None if product else "No visible products in the current database"
    add("catalogue", catalogue + ordering, reason=empty)
    add("catalogue_category", catalogue + " AND p.category_id=%s" + ordering, (product[1],) if product else (), empty)
    # Use a title token that exists, rather than a synthetic benchmark marker.
    keyword = next((word for word in product[2].split() if len(word) >= 3), product[2]) if product else None
    add(
        "search",
        catalogue + " AND (p.title ILIKE %s OR p.description ILIKE %s)" + ordering,
        (f"%{keyword}%", f"%{keyword}%") if product else (),
        empty,
    )
    buyer = one(
        cursor,
        'SELECT buyer_id FROM "order" WHERE NOT is_deleted GROUP BY buyer_id '
        "ORDER BY count(*) DESC,buyer_id LIMIT 1",
    )
    add(
        "buyer_history",
        'SELECT order_id,order_date,final_amount FROM "order" WHERE buyer_id=%s '
        "AND NOT is_deleted ORDER BY order_date DESC LIMIT 20",
        buyer or (),
        None if buyer else "No active orders",
    )
    seller = one(
        cursor,
        "SELECT p.seller_id FROM order_detail d JOIN product p USING(product_id) "
        'JOIN "order" o USING(order_id) WHERE NOT o.is_deleted '
        "GROUP BY p.seller_id ORDER BY count(*) DESC,p.seller_id LIMIT 1",
    )
    add(
        "seller_orders",
        'SELECT DISTINCT o.order_id,o.order_date,o.final_amount FROM "order" o '
        "JOIN order_detail d USING(order_id) JOIN product p USING(product_id) "
        "WHERE p.seller_id=%s AND NOT o.is_deleted ORDER BY o.order_date DESC LIMIT 20",
        seller or (),
        None if seller else "No seller orders",
    )
    review = one(cursor, "SELECT product_id FROM review WHERE NOT is_deleted ORDER BY review_id LIMIT 1")
    add(
        "review_history",
        "SELECT review_id,rating,created_at FROM review WHERE product_id=%s "
        "AND NOT is_deleted ORDER BY created_at DESC LIMIT 20",
        review or (),
        None if review else "No active reviews",
    )
    report = one(cursor, "SELECT review_id FROM review WHERE rating=0 AND NOT is_deleted LIMIT 1")
    add(
        "reports",
        "SELECT review_id,product_id FROM review WHERE rating=0 AND NOT is_deleted",
        reason=None if report else "No active reports (rating=0)",
    )
    cart = one(cursor, "SELECT cart_id,product_id FROM shopping_cart_item ORDER BY cart_id,product_id LIMIT 1")
    add(
        "cart_lookup",
        "SELECT cart_id,product_id,quantity FROM shopping_cart_item WHERE cart_id=%s AND product_id=%s",
        cart or (),
        None if cart else "shopping_cart_item is empty",
    )
    order = one(cursor, 'SELECT order_id FROM "order" WHERE NOT is_deleted ORDER BY order_id LIMIT 1')
    add(
        "order_pk_pruning",
        'SELECT order_id,order_status FROM "order" WHERE order_id=%s AND NOT is_deleted',
        order or (),
        None if order else "No active orders",
    )
    month = one(cursor, "SELECT date_trunc('month',min(created_at)) FROM system_log")[0]
    add(
        "log_month_pruning",
        "SELECT count(*) FROM system_log WHERE created_at>=%s " "AND created_at<%s + interval '1 month'",
        (month, month) if month else (),
        None if month else "system_log is empty",
    )
    add(
        "product_images",
        "SELECT image_id,product_id FROM product_image WHERE product_id=%s ORDER BY display_order",
        (product[0],) if product else (),
        empty,
    )
    run = one(cursor, "SELECT run_id FROM etl_runs LIMIT 1")
    add(
        "etl_status",
        "SELECT run_id,started_at,status FROM etl_runs ORDER BY started_at DESC LIMIT 1",
        reason=None if run else "etl_runs is empty",
    )
    # Selection only: do not acquire locks or claim/ack any real worker events.
    add(
        "etl_poll_selection",
        "SELECT event_id FROM etl_outbox WHERE status IN ('pending','dead') "
        "AND available_at<=clock_timestamp() ORDER BY event_id LIMIT 100",
    )
    return cases


def measure_pg(output, samples, warmups):
    connection = connect()
    try:
        connection.set_session(readonly=True, isolation_level="REPEATABLE READ")
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL statement_timeout='15s'")
            cursor.execute("SET LOCAL lock_timeout='2s'")
            cursor.execute("SET LOCAL TIME ZONE 'UTC'")
            version = one(cursor, "SELECT version()")[0]
            database = one(cursor, "SELECT current_database()")[0]
            readonly = one(cursor, "SHOW transaction_read_only")[0]
            cursor.execute("SELECT version,checksum FROM schema_migrations ORDER BY version")
            migrations = [dict(zip(("version", "checksum"), row, strict=True)) for row in cursor.fetchall()]
            cursor.execute(
                "SELECT tablename FROM pg_tables WHERE schemaname='public' "
                "AND tablename NOT IN (SELECT relname FROM pg_class WHERE relispartition) ORDER BY tablename"
            )
            tables = [row[0] for row in cursor.fetchall()]
            counts = {
                name: one(cursor, sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(name)))[0] for name in tables
            }
            cursor.execute(
                "SELECT tablename,indexname,indexdef FROM pg_indexes WHERE schemaname='public' "
                "ORDER BY tablename,indexname"
            )
            indexes = [dict(zip(("table", "name", "definition"), row, strict=True)) for row in cursor.fetchall()]
            index_bytes = one(
                cursor,
                "SELECT coalesce(sum(pg_relation_size(indexrelid)),0) "
                "FROM pg_index i JOIN pg_class c ON c.oid=i.indrelid "
                "WHERE c.relnamespace='public'::regnamespace",
            )[0]
            cases = {}
            for name, case in pg_cases(cursor).items():
                if case["skip_reason"]:
                    cases[name] = {"status": "skipped", "reason": case["skip_reason"]}
                    continue
                query, params = case["query"], case["parameters"]
                for _ in range(warmups):
                    cursor.execute(query, params)
                    cursor.fetchall()
                runs = []
                for _ in range(samples):
                    cursor.execute("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + query, params)
                    runs.append(cursor.fetchone()[0][0])
                rendered = cursor.mogrify(query, params).decode(connection.encoding)
                # Render text from one of the measured plans, without an extra execution.
                representative = sorted(runs, key=lambda run: run["Execution Time"])[len(runs) // 2]
                text = rendered + "\n\n" + json.dumps(representative, indent=2) + "\n"
                (output / f"{name}.txt").write_text(text, encoding="utf-8")
                save(output / f"{name}.json", {"sql": query, "parameters": params, "runs": runs})
                cases[name] = {
                    "status": "measured",
                    "median_execution_ms": statistics.median(r["Execution Time"] for r in runs),
                    "median_planning_ms": statistics.median(r["Planning Time"] for r in runs),
                    "returned_rows": [r["Plan"]["Actual Rows"] for r in runs],
                }
            summary = {
                "source": "current_application_database",
                "database": database,
                "postgresql": version,
                "transaction_read_only": readonly,
                "isolation": "REPEATABLE READ",
                "rows": counts,
                "migrations": migrations,
                "index_bytes": int(index_bytes),
                "samples": samples,
                "warmups": warmups,
                "cases": cases,
            }
            save(output / "indexes.json", indexes)
            save(output / "summary.json", summary)
            return summary
    finally:
        connection.rollback()
        connection.close()


def measure_mongo(output, samples, warmups):
    database = get_database()
    names = sorted(DOCUMENT_MODELS)
    counts_before = {name: database[name].count_documents({}) for name in names}
    indexes = {name: list(database[name].list_indexes()) for name in names}
    cases = {}
    product = database.product_details.find_one(
        {"deleted": False}, {"product_id": 1, "category_id": 1}, sort=[("product_id", 1)]
    )
    review = database.reviews.find_one({"deleted": False}, {"product_id": 1}, sort=[("product_id", 1)])
    order = database.order_snapshots.find_one({"deleted": False}, {"buyer.id": 1}, sort=[("order_id", 1)])
    queries = {
        "product_details": (
            "product_details",
            {"product_id": product["product_id"], "category_id": product["category_id"], "deleted": False}
            if product
            else None,
            None,
        ),
        "reviews": (
            "reviews",
            {"product_id": review["product_id"], "deleted": False} if review else None,
            {"created_at": -1},
        ),
        "order_snapshots": (
            "order_snapshots",
            {"buyer.id": order["buyer"]["id"], "deleted": False} if order else None,
            {"order_date": -1},
        ),
    }
    # Metadata may be empty in the actual seed. Do not invent brand/RAM values.
    metadata = database.product_details.find_one({"deleted": False, "attributes": {"$ne": {}}}, {"attributes": 1})
    attribute = next(
        (
            (key, value)
            for key, value in (metadata or {}).get("attributes", {}).items()
            if isinstance(value, str | bool | int | float)
        ),
        None,
    )
    queries["attribute_search"] = (
        "product_details",
        {"deleted": False, f"attributes.{attribute[0]}": attribute[1]} if attribute else None,
        None,
    )
    for name, (collection, query, sort) in queries.items():
        if query is None:
            cases[name] = {"status": "skipped", "reason": "No existing document/attribute for this query"}
            continue
        command = {"find": collection, "filter": query, "limit": 20, "projection": {"_id": 1}, "maxTimeMS": 5000}
        if sort:
            command["sort"] = sort
        for _ in range(warmups):
            database.command("explain", command, verbosity="executionStats")
        runs = [database.command("explain", command, verbosity="executionStats") for _ in range(samples)]
        save(output / f"{name}.json", {"command": command, "runs": runs})
        stats = [run["executionStats"] for run in runs]
        cases[name] = {
            "status": "measured",
            **{
                f"median_{key}": statistics.median(run[key] for run in stats)
                for key in ("executionTimeMillis", "totalDocsExamined", "totalKeysExamined", "nReturned")
            },
        }
    counts_after = {name: database[name].count_documents({}) for name in names}
    summary = {
        "source": "current_application_database",
        "database": database.name,
        "version": database.command("buildInfo")["version"],
        "read_only_commands": True,
        "consistency": "Sequential reads; no shared snapshot with PostgreSQL or across Mongo commands",
        "counts_before": counts_before,
        "counts_after": counts_after,
        "counts_unchanged": counts_before == counts_after,
        "samples": samples,
        "warmups": warmups,
        "cases": cases,
    }
    save(output / "indexes.json", indexes)
    save(output / "summary.json", summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, default=Path(__file__).resolve().parent.parent.parent)
    parser.add_argument("--samples", type=int, default=5)
    parser.add_argument("--warmups", type=int, default=1)
    args = parser.parse_args()
    if args.samples < 1 or args.warmups < 0:
        parser.error("samples must be positive and warmups nonnegative")
    args.output.mkdir(parents=True, exist_ok=False)
    started = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).isoformat()
    for folder in ("pg", "mongo"):
        (args.output / folder).mkdir()
    pg = measure_pg(args.output / "pg", args.samples, args.warmups)
    mongo = measure_mongo(args.output / "mongo", args.samples, args.warmups)
    seed_root = args.source_root / "database/03_seeds"
    if not seed_root.is_dir():
        raise RuntimeError("Seed source directory not found; pass --source-root pointing to the repository")
    seed_files = {
        str(path.relative_to(args.source_root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(seed_root.rglob("*.sql"))
    }
    save(
        args.output / "manifest.json",
        {
            "started_at": started,
            "finished_at": datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).isoformat(),
            "dataset": "Existing seeded application databases, including changes made after seeding",
            "generated_rows": 0,
            "mutations": [],
            "seed_sql_sha256": seed_files,
            "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "pg_rows": pg["rows"],
            "mongo_counts": mongo["counts_after"],
            "limitations": [
                "Current indexes only; no before/after optimization comparison",
                "Server execution time, not HTTP latency or concurrent throughput",
                "Mongo integer millisecond resolution; zero is not zero work",
                "No writes, ANALYZE, migrations, index changes, ETL or seeding performed",
                "Running application/worker can change data between stores or commands",
            ],
        },
    )
    print(json.dumps({"output": str(args.output), "pg_rows": pg["rows"], "mongo_counts": mongo["counts_after"]}))


if __name__ == "__main__":
    main()
