"""Generate a disposable v0 database, measure real plans, migrate, measure again.

DB_NAME MUST start with day4_bench_; existing databases are refused, never reset.
"""

import argparse
import json
import statistics
import time
from pathlib import Path

from psycopg2 import sql

from app.core.config import settings
from scripts.init_db import ensure_database, load_schema
from scripts.migrate import connect, run_migrations

QUERIES = {
    "catalogue": (
        "SELECT product_id,title,price FROM product WHERE status=1 AND NOT is_deleted "
        "AND category_id=1 ORDER BY created_at DESC LIMIT 20"
    ),
    "search": (
        "SELECT product_id,title FROM product WHERE status=1 AND NOT is_deleted "
        "AND (title ILIKE '%needlexyz%' OR description ILIKE '%needlexyz%') LIMIT 100"
    ),
    "buyer_history": (
        'SELECT * FROM "order" WHERE buyer_id=1000542 AND NOT is_deleted ORDER BY order_date DESC LIMIT 20'
    ),
    "seller_orders": (
        'SELECT DISTINCT o.* FROM "order" o JOIN order_detail d USING(order_id) '
        "JOIN product p USING(product_id) WHERE p.seller_id=1000001 "
        "AND NOT o.is_deleted ORDER BY o.order_date DESC LIMIT 20"
    ),
    "review_history": (
        "SELECT * FROM review WHERE product_id=1000042 AND NOT is_deleted ORDER BY created_at DESC LIMIT 20"
    ),
    "reports": "SELECT * FROM review WHERE rating=0 AND NOT is_deleted",
    "cart_lookup": "SELECT * FROM shopping_cart_item WHERE cart_id=1000042 AND product_id=1000041",
    "order_pk_pruning": 'SELECT * FROM "order" WHERE order_id=1000042 AND NOT is_deleted',
    "log_month_pruning": (
        "SELECT count(*) FROM system_log WHERE created_at >= timestamp '2026-03-01' "
        "AND created_at < timestamp '2026-04-01'"
    ),
}

SEED = """
INSERT INTO "user"(user_id,username,email,password_hash,random_key,full_name)
SELECT 1000000+g,'bench_'||g,'bench_'||g||'@example.invalid','benchmark-not-a-login',md5(g::text),'Synthetic '||g
FROM generate_series(1,1000) g;
INSERT INTO contact_info(contact_id,user_id,full_name,phone_number,address)
SELECT 1000000+g,1000000+g,'Synthetic '||g,'0000000000','Synthetic benchmark' FROM generate_series(1,1000) g;
INSERT INTO product(product_id,seller_id,category_id,title,description,price,quantity,status,created_at)
SELECT 1000000+g,1000001+(g%500),
 ((SELECT array_agg(category_id ORDER BY category_id) FROM category))[1+(g % (SELECT count(*)::int FROM category))],
 CASE WHEN g%1000=0 THEN 'needlexyz ' ELSE 'Synthetic ' END || md5(g::text),
 CASE WHEN g%2000=0 THEN 'needlexyz ' ELSE '' END || repeat(md5((g+1)::text),6),
 1000+(g%5000),100,CASE WHEN g%7=0 THEN 0 ELSE 1 END,
 timestamp '2026-01-01' + (g%365)*interval '1 day' + (g%86400)*interval '1 second'
FROM generate_series(1,50000) g;
INSERT INTO "order"(order_id,buyer_id,contact_id,payment_method_id,order_date,total_amount,final_amount,order_status)
SELECT 1000000+g,1000501+(g%500),1000501+(g%500),1,
 timestamp '2026-01-01'+(g%365)*interval '1 day'+(g%86400)*interval '1 second',1000,1000,g%5
FROM generate_series(1,100000) g;
INSERT INTO order_detail(order_id,product_id,quantity,price_at_purchase,subtotal)
SELECT 1000000+g,1000001+(g%50000),1,1000,1000 FROM generate_series(1,100000) g;
INSERT INTO review(product_id,buyer_id,rating,created_at,content)
SELECT 1000001+(g%50000),1000002+(g%999),CASE WHEN g%1000=0 THEN 0 ELSE 4 END,
 timestamp '2026-01-01'+(g%365)*interval '1 day','Synthetic review' FROM generate_series(1,100000) g;
INSERT INTO system_log(action,details,created_at)
SELECT 'BENCHMARK',repeat(md5(g::text),5),timestamp '2026-01-01'+(g%365)*interval '1 day'
FROM generate_series(1,100000) g;
INSERT INTO shopping_cart(cart_id,user_id) SELECT 1000000+g,1000000+g FROM generate_series(1,1000) g;
INSERT INTO shopping_cart_item(cart_id,product_id,quantity)
SELECT 1000001+(g%1000),1000000+g,1 FROM generate_series(1,50000) g;
SELECT setval(pg_get_serial_sequence('product','product_id'),(SELECT max(product_id) FROM product));
SELECT setval(pg_get_serial_sequence('"order"','order_id'),(SELECT max(order_id) FROM "order"));
SELECT setval(pg_get_serial_sequence('"user"','user_id'),(SELECT max(user_id) FROM "user"));
"""


def measure(connection, output: Path, phase: str) -> dict:
    result = {}
    with connection.cursor() as cursor:
        cursor.execute("ANALYZE")
        for name, query in QUERIES.items():
            # One warmup, then three measured executions; never force a planner method.
            cursor.execute(query)
            cursor.fetchall()
            runs = []
            for _ in range(3):
                cursor.execute("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + query)
                runs.append(cursor.fetchone()[0][0])
            cursor.execute("EXPLAIN (ANALYZE, BUFFERS) " + query)
            (output / f"{phase}_{name}.txt").write_text(
                query + "\n\n" + "\n".join(r[0] for r in cursor.fetchall()) + "\n"
            )
            (output / f"{phase}_{name}.json").write_text(json.dumps(runs, indent=2) + "\n")
            result[name] = {"median_execution_ms": statistics.median(r["Execution Time"] for r in runs)}
        cursor.execute(
            "SELECT sum(pg_indexes_size(oid)) FROM pg_class WHERE relnamespace='public'::regnamespace AND relkind='r'"
        )
        result["index_bytes"] = int(cursor.fetchone()[0])
        cursor.execute(
            'SELECT (SELECT count(*) FROM product),(SELECT count(*) FROM "order"),(SELECT count(*) FROM system_log)'
        )
        result["rows"] = dict(zip(("product", "order", "system_log"), cursor.fetchone(), strict=True))
    connection.commit()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not settings.DB_NAME.startswith("day4_bench_"):
        raise SystemExit("Refusing benchmark outside a new day4_bench_* database")
    with connect("postgres") as connection, connection.cursor() as cursor:
        cursor.execute("SELECT 1 FROM pg_database WHERE datname=%s", (settings.DB_NAME,))
        if cursor.fetchone():
            raise SystemExit("Benchmark database already exists; choose a new name, no automatic reset")
    args.output.mkdir(parents=True, exist_ok=True)
    ensure_database()
    load_schema()
    with connect() as connection, connection.cursor() as cursor:
        cursor.execute(SEED)
    with connect() as connection:
        before = measure(connection, args.output, "before")
    start = time.perf_counter()
    applied = run_migrations()
    migration_seconds = time.perf_counter() - start
    assert run_migrations() == [], "Second migration run must be a no-op"
    with connect() as connection:
        after = measure(connection, args.output, "after")
        with connection.cursor() as cursor:
            cursor.execute("SELECT version()")
            version = cursor.fetchone()[0]
            cursor.execute(sql.SQL("SELECT count(*) FROM users_full"))
            users = cursor.fetchone()[0]
    summary = {
        "database": settings.DB_NAME,
        "postgresql": version,
        "cache": "warmup + median of 3, same database, no forced planner",
        "generated": {"users": 1000, "products": 50000, "orders": 100000, "reviews": 100000, "logs": 100000},
        "migration_seconds": migration_seconds,
        "applied": applied,
        "users_after": users,
        "before": before,
        "after": after,
    }
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
