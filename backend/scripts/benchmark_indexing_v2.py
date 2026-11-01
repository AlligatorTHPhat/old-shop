"""Compare indexing candidates on a NEW disposable indexing_v2_* PG database.

Refuses existing databases and never resets an application database. Candidate DDL
is tested one at a time, then removed. Raw plans and result fingerprints are saved.
"""

import argparse
import csv
import hashlib
import json
import platform
import statistics
import tempfile
import time
from pathlib import Path

from app.core.config import settings
from scripts.benchmark_day4 import SEED
from scripts.init_db import ensure_database, load_schema
from scripts.migrate import DATABASE_DIR, connect, run_migrations

VISIBLE = "p.status=1 AND NOT p.is_deleted AND c.is_active AND NOT c.is_deleted"
CATALOGUE = (
    "SELECT p.product_id,p.title,p.price FROM product p JOIN category c USING(category_id) "
    f"WHERE {VISIBLE} "
)
QUERIES = {
    "Q01_category": CATALOGUE
    + "AND p.category_id=1 ORDER BY p.created_at DESC,p.product_id ASC LIMIT 20",
    "Q01_seller_exclusion": CATALOGUE
    + "AND p.category_id=1 AND p.seller_id<>1000001 ORDER BY p.created_at DESC,p.product_id ASC LIMIT 20",
    "Q01_offset": CATALOGUE
    + "AND p.category_id=1 ORDER BY p.created_at DESC,p.product_id ASC OFFSET 1000 LIMIT 20",
    "Q01_candidates": CATALOGUE
    + "AND p.product_id BETWEEN 1000001 AND 1005000 ORDER BY p.created_at DESC,p.product_id ASC LIMIT 20",
    "Q02_all": CATALOGUE + "ORDER BY p.created_at DESC,p.product_id ASC LIMIT 20",
    "Q02_price": CATALOGUE
    + "AND p.category_id=1 ORDER BY p.price,p.product_id LIMIT 20",
    "Q03_search": "SELECT product_id FROM product WHERE status=1 AND NOT is_deleted AND (title ILIKE '%needlexyz%' OR description ILIKE '%needlexyz%') ORDER BY product_id LIMIT 100",
    "Q03_short": "SELECT product_id FROM product WHERE status=1 AND NOT is_deleted AND (title ILIKE '%a%' OR description ILIKE '%a%') ORDER BY product_id LIMIT 20",
    "Q03_vietnamese": "SELECT product_id FROM product WHERE status=1 AND NOT is_deleted AND (title ILIKE '%máy%' OR description ILIKE '%máy%') ORDER BY product_id LIMIT 20",
    "Q04_detail": "SELECT product_id,price,quantity FROM product WHERE product_id=1000042 AND NOT is_deleted",
    "Q05_images": "SELECT image_id,image_url,content_type,size_bytes,is_primary,display_order FROM product_image WHERE product_id=1000042 ORDER BY display_order,image_id",
    "Q06_buyer": 'SELECT order_id,order_date FROM "order" WHERE buyer_id=1000542 AND NOT is_deleted ORDER BY order_date DESC LIMIT 20',
    "Q07_seller": 'SELECT DISTINCT o.* FROM "order" o JOIN order_detail d USING(order_id) JOIN product p USING(product_id) WHERE p.seller_id=1000001 AND NOT o.is_deleted ORDER BY o.order_date DESC LIMIT 20',
    "Q08_cart": "SELECT cart_item_id,quantity FROM shopping_cart_item WHERE cart_id=1000042 AND product_id=1000041",
    "Q09_login": "SELECT user_id FROM user_core WHERE email='index_user_42@example.invalid'",
    "Q10_paypal_reuse": 'SELECT order_id FROM "order" WHERE buyer_id=1000542 AND payment_method_id=1 AND order_status=0 AND NOT is_deleted ORDER BY order_date DESC LIMIT 1',
    "Q11_items": "SELECT order_detail_id,product_id,quantity FROM order_detail WHERE order_id=1000042 ORDER BY order_detail_id",
    "Q11_payments": "SELECT transaction_id FROM transaction WHERE order_id=1 ORDER BY transaction_id",
    "Q12_poll": "SELECT * FROM etl_outbox WHERE status IN ('pending','dead') AND available_at<=clock_timestamp() ORDER BY event_id LIMIT 100 FOR UPDATE SKIP LOCKED",
    "Q12_stable": "SELECT * FROM etl_outbox WHERE status IN ('pending','dead') AND available_at<=statement_timestamp() ORDER BY event_id LIMIT 100 FOR UPDATE SKIP LOCKED",
    "Q13_retry": "SELECT event_id FROM etl_outbox WHERE entity_type='product' AND entity_key='{\"id\":1000042}'::jsonb AND status<>'done' ORDER BY event_id LIMIT 1",
    "Q14_status": "SELECT run_id,started_at,status FROM etl_runs ORDER BY started_at DESC LIMIT 1",
    "Q14_aggregate": "SELECT ended_at FROM etl_runs WHERE status='success' AND details ? 'aggregate' ORDER BY ended_at DESC LIMIT 1",
    "Q15_image_missing": "SELECT EXISTS(SELECT 1 FROM product_image WHERE image_url='/media/products/index_missing.jpg')",
    "Q15_image_unique": "SELECT EXISTS(SELECT 1 FROM product_image WHERE image_url='/media/products/index_199999.jpg')",
    "Q15_image_shared": "SELECT EXISTS(SELECT 1 FROM product_image WHERE image_url='/media/products/index_shared.jpg')",
    "Q15_avatar_missing": "SELECT EXISTS(SELECT 1 FROM user_profile WHERE avatar_url='/media/users/index_missing.png')",
    "Q15_avatar_unique": "SELECT EXISTS(SELECT 1 FROM user_profile WHERE avatar_url='/media/users/index_2049000.png')",
    "Q16_audit": "SELECT log_id,created_at FROM system_log WHERE resource_type='product' AND resource_id=1000042 ORDER BY created_at DESC LIMIT 50",
    "Q17_voucher": 'SELECT order_id FROM "order" WHERE voucher_id=1 ORDER BY order_id',
    "Q18_report": "SELECT report_date,sum(gross_sales_vnd),sum(item_quantity) FROM report_daily_sales WHERE report_date>='2026-01-01' AND report_date<'2027-01-01' GROUP BY report_date ORDER BY report_date",
    "role_lookup": "SELECT user_id FROM user_role WHERE role_id=2 ORDER BY user_id",
    "token_lookup": "SELECT user_id FROM user_secret WHERE password_reset_token='index-token-2000042'",
    "cleanup_poll": "SELECT * FROM media_deletions WHERE status='pending' AND available_at<=clock_timestamp() ORDER BY deletion_id LIMIT 100",
    "cleanup_stable": "SELECT * FROM media_deletions WHERE status='pending' AND available_at<=statement_timestamp() ORDER BY deletion_id LIMIT 100",
}
# Names/definitions are explicit, not dynamically copied from executable Markdown.
CANDIDATES = {
    "I01": (
        "idx_product_catalogue_order_v2",
        "product(category_id,created_at DESC,product_id ASC) WHERE status=1 AND is_deleted=FALSE",
        ["Q01_category", "Q01_seller_exclusion", "Q01_offset"],
    ),
    "I02": (
        "idx_product_visible_date_id",
        "product(created_at DESC,product_id ASC) WHERE status=1 AND is_deleted=FALSE",
        ["Q02_all", "Q01_candidates"],
    ),
    "I03": (
        "idx_product_visible_category_price_id",
        "product(category_id,price ASC,product_id ASC) WHERE status=1 AND is_deleted=FALSE",
        ["Q02_price"],
    ),
    "I04": (
        "idx_product_image_url",
        "product_image(image_url)",
        ["Q15_image_missing", "Q15_image_unique", "Q15_image_shared"],
    ),
    "I05": (
        "idx_user_profile_avatar_url",
        "user_profile(avatar_url)",
        ["Q15_avatar_missing", "Q15_avatar_unique"],
    ),
    "I06": (
        "idx_product_image_display",
        "product_image(product_id,display_order,image_id)",
        ["Q05_images"],
    ),
    "I07": ("idx_order_voucher_lookup", '"order"(voucher_id)', ["Q17_voucher"]),
    "I08": ("idx_etl_runs_started", "etl_runs(started_at DESC)", ["Q14_status"]),
    "I09": (
        "idx_etl_runs_aggregate_success",
        "etl_runs(ended_at DESC) WHERE status='success' AND details ? 'aggregate'",
        ["Q14_aggregate"],
    ),
    "I10": (
        "idx_etl_outbox_entity_pending",
        "etl_outbox(entity_type,entity_key,event_id) WHERE status<>'done'",
        ["Q13_retry"],
    ),
    "I11": (
        "idx_etl_outbox_pending_event",
        "etl_outbox(event_id,available_at) WHERE status IN ('pending','dead')",
        ["Q12_poll", "Q12_stable"],
    ),
    "I12": ("idx_user_role_role_user", "user_role(role_id,user_id)", ["role_lookup"]),
    "I13": (
        "idx_user_secret_reset_token",
        "user_secret(password_reset_token) WHERE password_reset_token IS NOT NULL",
        ["token_lookup"],
    ),
    "I14": (
        "idx_system_log_resource_date",
        "system_log(resource_type,resource_id,created_at DESC)",
        ["Q16_audit"],
    ),
}
EXTRA_SEED = """
INSERT INTO "user"(user_id,username,email,password_hash,random_key,full_name,avatar_url,password_reset_token)
SELECT 2000000+g,'index_user_'||g,'index_user_'||g||'@example.invalid','benchmark-not-a-login',
 md5(('index-user-'||g)::text),'Synthetic index user',
 '/media/users/index_'||(2000000+g)||'.png',
 CASE WHEN g%42=0 THEN 'index-token-'||(2000000+g) END FROM generate_series(1,49000) g;
INSERT INTO user_role SELECT user_id,CASE WHEN user_id%100=0 THEN 2 ELSE 3 END
FROM "user" WHERE user_id>=1000000;
INSERT INTO product_image(product_id,image_url,alt_text,is_primary,display_order)
SELECT 1000001+((g-1)%50000),
 CASE WHEN g%10=0 THEN '/media/products/index_shared.jpg' ELSE '/media/products/index_'||g||'.jpg' END,
 'Synthetic benchmark image',g<=50000,1+(g-1)/50000 FROM generate_series(1,200000) g;
UPDATE product SET created_at=date_trunc('day',created_at), is_deleted=(product_id%29=0)
WHERE product_id>=1000000;
UPDATE "order" SET voucher_id=CASE WHEN order_id%20=0 THEN 1+(order_id%4) END,
 is_deleted=(order_id%29=0) WHERE order_id>=1000000;
UPDATE system_log SET resource_type='product',resource_id=1000001+(log_id%50000);
"""
OPERATIONS_SEED = """
INSERT INTO etl_runs(run_id,mode,started_at,ended_at,status,details)
SELECT md5(('index-run-'||g)::text)::uuid,'incremental',
 timestamptz '2026-11-01 00:00:00+00'-g*interval '1 minute',
 timestamptz '2026-11-01 00:00:01+00'-g*interval '1 minute',
 CASE WHEN g%5=0 THEN 'partial' ELSE 'success' END,
 CASE WHEN g%3=0 THEN '{"aggregate":{"groups":1}}'::jsonb ELSE '{}'::jsonb END
FROM generate_series(1,20000) g;
INSERT INTO etl_outbox(source_table,source_key,entity_type,entity_key,operation,status,available_at)
SELECT 'product',jsonb_build_object('product_id',1000001+g%50000),'product',
 jsonb_build_object('id',1000001+g%50000),'UPDATE',
 CASE WHEN g<=190000 THEN 'done' WHEN g%7=0 THEN 'dead' ELSE 'pending' END,
 CASE WHEN g%3=0 THEN timestamptz '2020-01-01' ELSE timestamptz '2100-01-01' END
FROM generate_series(1,200000) g;
INSERT INTO media_deletions(url_path,status,available_at)
SELECT '/media/products/index_cleanup_'||g||'.jpg',CASE WHEN g<=190000 THEN 'done' ELSE 'pending' END,
 CASE WHEN g%3=0 THEN timestamptz '2020-01-01' ELSE timestamptz '2100-01-01' END
FROM generate_series(1,200000) g;
INSERT INTO report_daily_sales
SELECT o.order_date::date,p.seller_id,p.category_id,count(DISTINCT o.order_id),sum(d.quantity),sum(d.subtotal),
 CURRENT_TIMESTAMP,md5('index-report')::uuid
FROM "order" o JOIN order_detail d USING(order_id) JOIN product p USING(product_id)
WHERE o.order_status=3 AND NOT o.is_deleted GROUP BY 1,2,3;
"""
WRITES = {
    "view_count": "UPDATE product SET view_count=view_count+1 WHERE product_id=1000042",
    "reserve": "UPDATE product SET quantity=quantity-1 WHERE product_id=1000042",
    "moderate": "UPDATE product SET status=0 WHERE product_id=1000043",
    "description": "UPDATE product SET description=description||' measured' WHERE product_id=1000042",
    "image_insert": "INSERT INTO product_image(product_id,image_url) VALUES(1000042,'/media/products/index_write.jpg')",
    "avatar": "UPDATE user_profile SET avatar_url='/media/users/index_write.png' WHERE user_id=2000042",
    "run_insert": "INSERT INTO etl_runs(run_id,mode) VALUES(gen_random_uuid(),'incremental')",
    "event_ack": "UPDATE etl_outbox SET status='done' WHERE event_id=199998",
}


def dump(path, value):
    path.write_text(json.dumps(value, indent=2, default=str, ensure_ascii=False) + "\n")


def nodes(plan):
    yield plan
    for child in plan.get("Plans", []):
        yield from nodes(child)


def fingerprint(rows):
    return hashlib.sha256(
        json.dumps(rows, default=str, sort_keys=True).encode()
    ).hexdigest()


def read_measure(connection, name, query, output, repeats):
    plans = []
    rows = None
    for attempt in range(repeats + 1):
        with connection.cursor() as cursor:
            cursor.execute("BEGIN")
            try:
                cursor.execute(query)
                current = cursor.fetchall()
                if rows is None:
                    rows = current
                assert fingerprint(current) == fingerprint(rows), name
                cursor.execute("EXPLAIN (ANALYZE,BUFFERS,FORMAT JSON) " + query)
                plan = cursor.fetchone()[0][0]
            finally:
                cursor.execute("ROLLBACK")
        if attempt:
            plans.append(plan)
    dump(
        output / f"{name}.json",
        {"sql": query, "plans": plans, "result_sha256": fingerprint(rows)},
    )
    samples = [p["Execution Time"] for p in plans]
    return {
        "median_ms": statistics.median(samples),
        "min_ms": min(samples),
        "max_ms": max(samples),
        "shared_hit_blocks": statistics.median(
            p["Plan"].get("Shared Hit Blocks", 0) for p in plans
        ),
        "shared_read_blocks": statistics.median(
            p["Plan"].get("Shared Read Blocks", 0) for p in plans
        ),
        "indexes": sorted(
            {
                n["Index Name"]
                for p in plans
                for n in nodes(p["Plan"])
                if "Index Name" in n
            }
        ),
        "sorts": sorted(
            {
                n["Node Type"]
                for p in plans
                for n in nodes(p["Plan"])
                if "Sort" in n["Node Type"]
            }
        ),
        "result_sha256": fingerprint(rows),
        "returned": len(rows),
    }


def write_measure(connection, output, repeats):
    results = {}
    for name, query in WRITES.items():
        plans = []
        for _ in range(repeats + 1):
            with connection.cursor() as cursor:
                cursor.execute("BEGIN")
                try:
                    cursor.execute("EXPLAIN (ANALYZE,BUFFERS,WAL,FORMAT JSON) " + query)
                    plans.append(cursor.fetchone()[0][0])
                finally:
                    cursor.execute("ROLLBACK")
        plans = plans[1:]
        dump(
            output / f"write_{name}.json",
            {
                "sql": query,
                "representative_plan": plans[0],
                "samples": [
                    {
                        "execution_ms": p["Execution Time"],
                        "wal_bytes": p["Plan"].get("WAL Bytes", 0),
                        "triggers": p.get("Triggers", []),
                    }
                    for p in plans
                ],
            },
        )
        times = sorted(p["Execution Time"] for p in plans)
        results[name] = {
            "median_ms": statistics.median(times),
            "p95_ms": times[int(0.95 * (len(times) - 1))],
            "samples": len(times),
            "wal_bytes": statistics.median(
                p["Plan"].get("WAL Bytes", 0) for p in plans
            ),
        }
    return results


def inventory(connection, output):
    with connection.cursor() as cursor:
        cursor.execute("""SELECT t.relname,ix.relname,am.amname,i.indisprimary,i.indisunique,
        i.indisvalid,pg_get_indexdef(ix.oid),pg_relation_size(ix.oid)
        FROM pg_index i JOIN pg_class t ON t.oid=i.indrelid JOIN pg_class ix ON ix.oid=i.indexrelid
        JOIN pg_am am ON am.oid=ix.relam WHERE t.relnamespace='public'::regnamespace
        ORDER BY t.relname,ix.relname""")
        rows = cursor.fetchall()
    with output.open("w") as target:
        writer = csv.writer(target)
        writer.writerow(
            [
                "table",
                "index",
                "method",
                "primary",
                "unique",
                "valid",
                "definition",
                "bytes",
            ]
        )
        writer.writerows(rows)
    return sum(r[-1] for r in rows)


def physical_index_bytes(connection, name):
    with connection.cursor() as cursor:
        cursor.execute(
            """WITH RECURSIVE tree(oid) AS (
            SELECT %s::regclass::oid UNION ALL
            SELECT i.inhrelid FROM pg_inherits i JOIN tree t ON i.inhparent=t.oid)
            SELECT sum(pg_relation_size(oid)) FROM tree""",
            (name,),
        )
        return int(cursor.fetchone()[0])


def queue_matrix(connection, output, repeats):
    result = {}
    for scenario, available in {
        "mixed": "CASE WHEN event_id%3=0 THEN timestamptz '2020-01-01' ELSE timestamptz '2100-01-01' END",
        "old_deferred": "CASE WHEN event_id>=199800 THEN timestamptz '2020-01-01' ELSE timestamptz '2100-01-01' END",
        "all_deferred": "timestamptz '2100-01-01'",
    }.items():
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE etl_outbox SET available_at="
                + available
                + " WHERE status<>'done'"
            )
            cursor.execute("VACUUM ANALYZE etl_outbox")
        destination = output / scenario
        destination.mkdir()
        result[scenario] = {
            q: read_measure(connection, q, QUERIES[q], destination, repeats)
            for q in ("Q12_poll", "Q12_stable")
        }
        assert (
            result[scenario]["Q12_poll"]["result_sha256"]
            == result[scenario]["Q12_stable"]["result_sha256"]
        )
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE etl_outbox SET available_at=CASE WHEN event_id%3=0 THEN timestamptz '2020-01-01' ELSE timestamptz '2100-01-01' END WHERE status<>'done'"
        )
        cursor.execute("VACUUM ANALYZE etl_outbox")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--write-repeats", type=int, default=100)
    parser.add_argument(
        "--prepared",
        action="store_true",
        help="Measure an already prepared, untouched 001-006 benchmark fixture",
    )
    args = parser.parse_args()
    if not settings.DB_NAME.startswith("indexing_v2_"):
        raise SystemExit("Refusing benchmark outside a NEW indexing_v2_* database")
    with connect("postgres") as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT 1 FROM pg_database WHERE datname=%s", (settings.DB_NAME,)
        )
        exists = cursor.fetchone() is not None
        if exists != args.prepared:
            raise SystemExit(
                "Use a NEW database, or --prepared only for an untouched 001-006 benchmark fixture"
            )
    if args.output.exists() and any(args.output.iterdir()):
        raise SystemExit("Evidence directory is not empty; choose a fresh destination")
    args.output.mkdir(parents=True, exist_ok=True)
    if not args.prepared:
        ensure_database()
        load_schema()
        with connect() as connection, connection.cursor() as cursor:
            cursor.execute(SEED)
            cursor.execute(EXTRA_SEED)
        with tempfile.TemporaryDirectory(prefix="indexing-v2-baseline-") as folder:
            directory = Path(folder)
            for path in (DATABASE_DIR / "04_migrations").glob("*.sql"):
                if path.name[:3].isdigit() and int(path.name[:3]) <= 6:
                    (directory / path.name).write_bytes(path.read_bytes())
            run_migrations(directory)
    with connect() as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT version,checksum FROM schema_migrations ORDER BY version"
        )
        history = cursor.fetchall()
        baseline_versions = [r[0] for r in history]
        assert baseline_versions == ["001", "002", "003", "004", "005", "006"]
        for version, checksum in history:
            paths = list((DATABASE_DIR / "04_migrations").glob(version + "_*.sql"))
            assert (
                len(paths) == 1
                and hashlib.sha256(paths[0].read_bytes()).hexdigest() == checksum
            )
    connection = connect()
    connection.autocommit = True
    try:
        with connection.cursor() as cursor:
            if not args.prepared:
                cursor.execute(OPERATIONS_SEED)
            cursor.execute(
                'SELECT (SELECT count(*) FROM product), (SELECT count(*) FROM "order"), '
                "(SELECT count(*) FROM etl_outbox), (SELECT count(*) FROM product_image)"
            )
            assert cursor.fetchone() == (51000, 100030, 200000, 202000), (
                "Unexpected benchmark fixture"
            )
            cursor.execute("VACUUM ANALYZE")
            cursor.execute(
                "SELECT version(),current_setting('server_encoding'),(SELECT datcollate FROM pg_database WHERE datname=current_database())"
            )
            version = cursor.fetchone()
            cursor.execute(
                "SELECT relname,n_live_tup FROM pg_stat_user_tables ORDER BY relname"
            )
            counts = cursor.fetchall()
        dump(
            args.output / "environment.json",
            {
                "database": settings.DB_NAME,
                "postgres": version,
                "python": platform.python_version(),
                "baseline_versions": baseline_versions,
                "approximate_rows": counts,
                "read_samples": args.repeats,
                "write_samples": args.write_repeats,
                "forced_planner": False,
            },
        )
        baseline_dir = args.output / "before"
        baseline_dir.mkdir()
        baseline_bytes = inventory(connection, args.output / "inventory.csv")
        baseline = {
            name: read_measure(connection, name, query, baseline_dir, args.repeats)
            for name, query in QUERIES.items()
        }
        before_writes = write_measure(connection, baseline_dir, args.write_repeats)
        queue_dir = baseline_dir / "queue"
        queue_dir.mkdir()
        before_queue = queue_matrix(connection, queue_dir, args.repeats)
        summary = {
            "before": baseline,
            "before_writes": before_writes,
            "before_queue": before_queue,
            "baseline_index_bytes": baseline_bytes,
            "candidates": {},
        }
        for code, (name, definition, queries) in CANDIDATES.items():
            destination = args.output / code
            destination.mkdir()
            with connection.cursor() as cursor:
                start = time.perf_counter()
                cursor.execute(f"CREATE INDEX {name} ON {definition}")
                seconds = time.perf_counter() - start
                cursor.execute("VACUUM ANALYZE")
            try:
                measured = {
                    q: read_measure(
                        connection, q, QUERIES[q], destination, args.repeats
                    )
                    for q in queries
                }
                for q, value in measured.items():
                    assert value["result_sha256"] == baseline[q]["result_sha256"], (
                        code,
                        q,
                    )
                measured_writes = write_measure(
                    connection, destination, args.write_repeats
                )
                item = {
                    "index": name,
                    "ddl": f"CREATE INDEX {name} ON {definition};",
                    "build_seconds": seconds,
                    "added_index_bytes": physical_index_bytes(connection, name),
                    "total_index_bytes_delta_including_trial_bloat": inventory(
                        connection, destination / "inventory.csv"
                    )
                    - baseline_bytes,
                    "queries": measured,
                    "writes": measured_writes,
                }
                if code == "I11":
                    qdir = destination / "queue"
                    qdir.mkdir()
                    item["queue"] = queue_matrix(connection, qdir, args.repeats)
                summary["candidates"][code] = item
                dump(args.output / "summary.json", summary)
                print(
                    json.dumps(
                        {
                            "candidate": code,
                            "queries_ms": {
                                q: v["median_ms"] for q, v in measured.items()
                            },
                            "bytes": item["added_index_bytes"],
                        }
                    ),
                    flush=True,
                )
            finally:
                with connection.cursor() as cursor:
                    cursor.execute(f"DROP INDEX {name}")
                    cursor.execute("VACUUM ANALYZE")
        with (args.output / "summary.csv").open("w") as target:
            writer = csv.writer(target)
            writer.writerow(
                [
                    "candidate",
                    "query",
                    "before_ms",
                    "after_ms",
                    "before_hits",
                    "after_hits",
                    "added_bytes",
                ]
            )
            for code, value in summary["candidates"].items():
                for name, measured in value["queries"].items():
                    writer.writerow(
                        [
                            code,
                            name,
                            baseline[name]["median_ms"],
                            measured["median_ms"],
                            baseline[name]["shared_hit_blocks"],
                            measured["shared_hit_blocks"],
                            value["added_index_bytes"],
                        ]
                    )
        dump(args.output / "summary.json", summary)
    finally:
        connection.close()


if __name__ == "__main__":
    main()
