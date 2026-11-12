"""Compare candidate indexes in UUID databases, never in the application DB.

FRAGMENT_TEST_PG_DSN must name a disposable trust-auth PostgreSQL lab server.
Optional FRAGMENT_TEST_MONGO_URI enables an independent UUID Mongo database.
"""

import argparse
import json
import math
import os
import platform
import statistics
import subprocess
import time
import uuid
from pathlib import Path

import psycopg2

from scripts.fragmentation_lab import disposable_lab
from scripts.verify_fragmentation import audit, read

CANDIDATES = {
    "category": (
        "idx_product_visible_category_date_id",
        "product",
        "category_id,created_at DESC,product_id ASC",
        " WHERE status=1 AND NOT is_deleted",
        "SELECT product_id,title,price FROM product WHERE category_id=2 AND status=1 AND NOT is_deleted "
        "ORDER BY created_at DESC,product_id ASC LIMIT 20",
    ),
    "seller": (
        "idx_product_visible_seller_date_id",
        "product",
        "seller_id,created_at DESC,product_id ASC",
        " WHERE status=1 AND NOT is_deleted",
        "SELECT product_id,title,price FROM product WHERE seller_id=103 AND status=1 AND NOT is_deleted "
        "ORDER BY created_at DESC,product_id ASC LIMIT 20",
    ),
    "price": (
        "idx_product_visible_price_id",
        "product",
        "price ASC,product_id ASC",
        " WHERE status=1 AND NOT is_deleted",
        "SELECT product_id,title,price FROM product "
        "WHERE status=1 AND NOT is_deleted ORDER BY price ASC,product_id ASC LIMIT 20",
    ),
    "images": (
        "idx_product_image_order",
        "product_image",
        "product_id,display_order,image_id",
        "",
        "SELECT image_id,product_id,image_url FROM product_image WHERE product_id=100001 "
        "ORDER BY display_order,image_id",
    ),
}


def latency(values):
    ordered = sorted(values)
    return {"p50_ms": statistics.median(values), "p95_ms": ordered[math.ceil(len(values) * 0.95) - 1]}


def nodes(plan):
    yield plan
    for child in plan.get("Plans", []):
        yield from nodes(child)


def measure(connection, query, samples):
    with connection.cursor() as cursor:
        for _ in range(3):
            cursor.execute(query)
            cursor.fetchall()
        times, runs = [], []
        for _ in range(samples):
            started = time.perf_counter()
            cursor.execute(query)
            cursor.fetchall()
            times.append((time.perf_counter() - started) * 1000)
        for _ in range(3):
            cursor.execute("EXPLAIN(ANALYZE,BUFFERS,VERBOSE,FORMAT JSON) " + query)
            runs.append(cursor.fetchone()[0][0])
        return {**latency(times), "runs_ms": times, "explain": runs}


def write_measure(connection, samples, images=False):
    # Roll back each sample so every candidate sees the same rows. Updates touch
    # indexed fields and exercise their maintenance, rather than a HOT-only case.
    times = []
    for _ in range(samples + 3):
        with connection.cursor() as cursor:
            cursor.execute("SAVEPOINT write_sample")
            started = time.perf_counter()
            cursor.execute(
                "UPDATE product_image SET display_order=display_order+1 WHERE product_id=100001"
                if images
                else "UPDATE product SET price=price+1,created_at=created_at+interval '1 second' "
                "WHERE product_id BETWEEN 100001 AND 100199"
            )
            elapsed = (time.perf_counter() - started) * 1000
            cursor.execute("ROLLBACK TO SAVEPOINT write_sample; RELEASE SAVEPOINT write_sample")
            times.append(elapsed)
    return {**latency(times[3:]), "runs_ms": times[3:], "transaction": "rolled back; commit/fsync cost excluded"}


def pg_benchmark(dsn, rows, samples):
    with disposable_lab(dsn) as lab:
        connections = {site: psycopg2.connect(lab.dsn(site)) for site in "AB"}
        try:
            # Controlled fixture, before any benchmark mutations, kept only in memory.
            reference = {
                t: [r for site in "AB" for r in read(connections[site], f"SELECT * FROM {t}")]
                for t in ("product", "product_image")
            }
            integrity = audit(connections, reference)
            for connection in connections.values():
                connection.rollback()
            for site, connection in connections.items():
                lab.sql(site, "DROP INDEX IF EXISTS idx_product_visible_seller_date_id")
                with connection.cursor() as cursor:
                    cursor.execute("SET timezone='UTC'")
                    # 2:1 site skew, repeated timestamps/prices and minority seller/category.
                    n = rows if site == "A" else rows // 2
                    start = 100001 if site == "A" else 100002
                    sellers = (101, 103) if site == "A" else (202, 204)
                    cursor.execute(
                        """INSERT INTO product(product_id,seller_id,category_id,title,description,
                        price,quantity,status,created_at) SELECT %s+2*g,
                        CASE WHEN g%%10=0 THEN %s ELSE %s END,CASE WHEN g%%10=0 THEN 2 ELSE 1 END,
                        'Benchmark product '||g,'Synthetic controlled workload', (g%%100)*100,10,1,
                        timestamp '2026-01-01' + (g%%240)*interval '1 hour' FROM generate_series(0,%s) g""",
                        (start, sellers[1], sellers[0], n - 1),
                    )
                    cursor.execute(
                        """INSERT INTO product_image(image_id,product_id,image_url,display_order)
                        SELECT %s+2*g,%s,'/synthetic/'||g,g%%10 FROM generate_series(0,999) g""",
                        (start, start),
                    )
                    cursor.execute("ANALYZE product; ANALYZE product_image")
                connection.commit()
            connection = connections["A"]
            report = {
                "integrity_before_benchmark": integrity,
                "rows_generated": {"A": rows, "B": rows // 2},
                "candidates": {},
            }
            for case, (name, table, keys, predicate, query) in CANDIDATES.items():
                before = measure(connection, query, samples)
                before_write = write_measure(connection, samples, case == "images")
                connection.rollback()
                started = time.perf_counter()
                with connection.cursor() as cursor:
                    cursor.execute(f"CREATE INDEX {name} ON {table}({keys}){predicate}")
                connection.commit()
                build_ms = (time.perf_counter() - started) * 1000
                after = measure(connection, query, samples)
                after_write = write_measure(connection, samples, case == "images")
                with connection.cursor() as cursor:
                    cursor.execute("SELECT pg_relation_size(%s::regclass)", (name,))
                    size = cursor.fetchone()[0]
                improvement = (1 - after["p95_ms"] / before["p95_ms"]) * 100
                write_overhead = (after_write["p95_ms"] / before_write["p95_ms"] - 1) * 100
                report["candidates"][case] = {
                    "index": name,
                    "query": query,
                    "before": before,
                    "after": after,
                    "write_before": before_write,
                    "write_after": after_write,
                    "build_ms": build_ms,
                    "index_bytes": size,
                    "read_p95_improvement_percent": improvement,
                    "write_p95_overhead_percent": write_overhead,
                    "threshold_passed": improvement >= 20 and write_overhead <= 10,
                    "decision": "candidate_only; review representative workload before release",
                }
                connection.rollback()
                lab.sql("A", f"DROP INDEX {name}")
            report["remote_pushdown"] = measure(
                connection,
                "SELECT product_id FROM v_remote_product WHERE seller_id=204 AND status=1 AND NOT is_deleted "
                "ORDER BY created_at DESC,product_id ASC LIMIT 20",
                samples,
            )
            with connection.cursor() as cursor:
                cursor.execute('EXPLAIN(FORMAT JSON) SELECT * FROM "order" WHERE order_id=1')
                report["order_pruning"] = cursor.fetchone()[0]
                cursor.execute(
                    "EXPLAIN(FORMAT JSON) SELECT * FROM system_log WHERE created_at>=timestamp '2026-11-01' "
                    "AND created_at<timestamp '2026-12-01'"
                )
                report["log_pruning"] = cursor.fetchone()[0]
                cursor.execute("SELECT version()")
                report["version"] = cursor.fetchone()[0]
            return report
        finally:
            for connection in connections.values():
                connection.close()


def mongo_benchmark(uri, rows, samples):
    from pymongo import MongoClient

    with MongoClient(uri, serverSelectionTimeoutMS=5000) as client:
        name = "fragment_benchmark_" + uuid.uuid4().hex
        database = client[name]
        try:
            collection = database.product_details
            collection.insert_many(
                [
                    {
                        "product_id": i,
                        "deleted": False,
                        "attributes": {"brand": "minor" if i % 100 == 0 else "common"},
                        "created_at": i,
                    }
                    for i in range(rows)
                ]
            )
            collection.create_index("product_id", unique=True)
            command = {
                "find": "product_details",
                "filter": {"deleted": False, "attributes.brand": "minor"},
                "projection": {"_id": 0, "product_id": 1},
                "limit": 5001,
            }

            def measure_mongo():
                for _ in range(3):
                    list(collection.find(command["filter"], command["projection"]).limit(5001))
                times = []
                for _ in range(samples):
                    started = time.perf_counter()
                    list(collection.find(command["filter"], command["projection"]).limit(5001))
                    times.append((time.perf_counter() - started) * 1000)
                explain = database.command("explain", command, verbosity="executionStats")
                return {**latency(times), "runs_ms": times, "explain": explain}

            before = measure_mongo()
            collection.create_index(
                [("attributes.brand", 1), ("product_id", 1)],
                name="candidate_brand_product",
                partialFilterExpression={"deleted": False},
            )
            after = measure_mongo()
            return {
                "version": client.server_info()["version"],
                "rows_generated": rows,
                "query": command,
                "before": before,
                "after": after,
                "decision": "candidate_only; brand frequency in production has not been established",
                "write_cost": "not measured; candidate must not be released on these read results alone",
            }
        finally:
            client.drop_database(name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--rows", default=20000, type=int)
    parser.add_argument("--samples", default=30, type=int)
    args = parser.parse_args()
    if args.rows < 1000 or args.samples < 30:
        parser.error("Use at least 1000 rows and 30 samples")
    args.output.mkdir(parents=True, exist_ok=False)
    report = {
        "dataset": "Synthetic deterministic isolated lab, 2:1 site skew",
        "samples": args.samples,
        "warmups": 3,
        "concurrency": 1,
        "cache": "warm",
        "machine": platform.platform(),
        "commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "limitations": [
            "Local single-host experiment; not production HTTP load or concurrent throughput",
            "Individual index trials, not the cumulative overhead of all candidates",
            "Write samples exclude commit/fsync; no release decision from these numbers alone",
        ],
    }
    report["postgresql"] = pg_benchmark(os.environ["FRAGMENT_TEST_PG_DSN"], args.rows, args.samples)
    (args.output / "postgresql.json").write_text(json.dumps(report, indent=2, default=str) + "\n")
    if os.getenv("FRAGMENT_TEST_MONGO_URI"):
        report["mongodb"] = mongo_benchmark(os.environ["FRAGMENT_TEST_MONGO_URI"], args.rows, args.samples)
    (args.output / "results.json").write_text(json.dumps(report, indent=2, default=str) + "\n")
    print(
        json.dumps(
            {
                "output": str(args.output),
                "integrity": report["postgresql"]["integrity_before_benchmark"]["result"],
                "candidates": {
                    n: {
                        k: v
                        for k, v in r.items()
                        if k in ("threshold_passed", "read_p95_improvement_percent", "write_p95_overhead_percent")
                    }
                    for n, r in report["postgresql"]["candidates"].items()
                },
            }
        )
    )


if __name__ == "__main__":
    main()
