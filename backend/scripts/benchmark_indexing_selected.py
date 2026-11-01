"""Verify the selected migration against the same prepared 001-006 benchmark DB."""

import argparse
import csv
import json
import statistics
import uuid
from contextlib import closing
from pathlib import Path

from psycopg2 import sql
from sqlalchemy import event

from app.core.config import settings
from app.core.database import SessionLocal, engine
from app.crud.product import crud_product
from scripts.benchmark_indexing_v2 import (
    QUERIES,
    WRITES,
    dump,
    inventory,
    nodes,
    read_measure,
    write_measure,
)
from scripts.migrate import DATABASE_DIR, connect, run_migrations
from scripts.verify_day4 import snapshot
from scripts.verify_indexing_v2 import SPECS


def verify_retained(before, after):
    def definitions(path):
        with path.open() as source:
            return {
                row["index"]: {
                    key: value for key, value in row.items() if key != "bytes"
                }
                for row in csv.DictReader(source)
            }

    original, current = definitions(before), definitions(after)
    assert all(current.get(name) == definition for name, definition in original.items())
    added = set(current) - set(original)
    assert set(SPECS) <= added and len(added) == 13
    assert all(
        current[name]["table"] in {"order_h0", "order_h1", "order_h2", "order_h3"}
        for name in added - set(SPECS)
    )
    return {
        "result": "PASS",
        "old_indexes_preserved": len(original),
        "new_index_relations": sorted(added),
    }


def approved_write_pair(destination):
    """Compare approved-product writes on a disposable clone; leave source/history intact."""
    name = "indexing_v2_write_" + uuid.uuid4().hex[:12]
    sampled_digest = """SELECT md5(concat_ws('|',
        (SELECT row_to_json(p)::text FROM product p WHERE product_id=1000043),
        (SELECT row_to_json(r)::text FROM etl_runs r WHERE run_id=md5('index-run-5')::uuid),
        (SELECT row_to_json(e)::text FROM etl_outbox e WHERE event_id=199998)))"""
    with closing(connect("postgres")) as admin:
        admin.autocommit = True
        with admin.cursor() as cursor:
            cursor.execute(
                sql.SQL("CREATE DATABASE {} TEMPLATE {}").format(
                    sql.Identifier(name), sql.Identifier(settings.DB_NAME)
                )
            )
        try:
            with closing(connect(name)) as connection:
                connection.autocommit = True
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT version,checksum FROM schema_migrations ORDER BY version"
                    )
                    history = cursor.fetchall()
                    assert [row[0] for row in history] == [
                        "001",
                        "002",
                        "003",
                        "004",
                        "005",
                        "006",
                        "007",
                    ]
                    cursor.execute(
                        "SELECT status,is_deleted FROM product WHERE product_id=1000043"
                    )
                    assert cursor.fetchone() == (1, False), (
                        "Expected an approved, visible fixture product"
                    )
                    cursor.execute(sampled_digest)
                    original_row = cursor.fetchone()[0]
                    for index in SPECS:
                        cursor.execute(
                            sql.SQL("DROP INDEX {}.{}").format(
                                sql.Identifier("public"), sql.Identifier(index)
                            )
                        )
                    cursor.execute("VACUUM ANALYZE")
                WRITES.clear()
                WRITES.update(
                    {
                        "view_count_approved": "UPDATE product SET view_count=view_count+1 WHERE product_id=1000043",
                        "reserve_approved": "UPDATE product SET quantity=quantity-1 WHERE product_id=1000043",
                        "description_approved": "UPDATE product SET description=description||' measured' WHERE product_id=1000043",
                        "run_finish": "UPDATE etl_runs SET status='success',details=details||'{\"aggregate\":{\"groups\":1}}'::jsonb,ended_at=clock_timestamp() WHERE run_id=md5('index-run-5')::uuid",
                        "event_retry": "UPDATE etl_outbox SET status='pending',attempts=attempts+1,available_at=clock_timestamp()+interval '60 seconds' WHERE event_id=199998",
                    }
                )
                before = destination / "before"
                before.mkdir()
                baseline = write_measure(connection, before, 100)
                inventory(connection, before / "inventory.csv")
                with connection.cursor() as cursor:
                    # Experimental DDL on the clone only. Never edit migration history.
                    cursor.execute(
                        (DATABASE_DIR / "04_migrations/007_indexing_v2.sql").read_text()
                    )
                    cursor.execute("VACUUM ANALYZE")
                after = destination / "after"
                after.mkdir()
                selected = write_measure(connection, after, 100)
                inventory(connection, after / "inventory.csv")
                retained = verify_retained(
                    before / "inventory.csv", after / "inventory.csv"
                )
                # Repeat in reverse order to expose drift/cache/order bias (A-B-B-A).
                with connection.cursor() as cursor:
                    cursor.execute("VACUUM ANALYZE")
                after_repeat = destination / "after_repeat"
                after_repeat.mkdir()
                selected_repeat = write_measure(connection, after_repeat, 100)
                with connection.cursor() as cursor:
                    for index in SPECS:
                        cursor.execute(
                            sql.SQL("DROP INDEX {}.{}").format(
                                sql.Identifier("public"), sql.Identifier(index)
                            )
                        )
                    cursor.execute("VACUUM ANALYZE")
                before_repeat = destination / "before_repeat"
                before_repeat.mkdir()
                baseline_repeat = write_measure(connection, before_repeat, 100)

                def combined(first, second):
                    result = {}
                    for operation in WRITES:
                        samples = []
                        for folder in (first, second):
                            samples.extend(
                                json.loads(
                                    (folder / f"write_{operation}.json").read_text()
                                )["samples"]
                            )
                        times = sorted(sample["execution_ms"] for sample in samples)
                        result[operation] = {
                            "median_ms": statistics.median(times),
                            "p95_ms": times[int(0.95 * (len(times) - 1))],
                            "samples": len(times),
                            "wal_bytes": statistics.median(
                                sample["wal_bytes"] for sample in samples
                            ),
                        }
                    return result

                with connection.cursor() as cursor:
                    cursor.execute(sampled_digest)
                    assert cursor.fetchone()[0] == original_row
                    cursor.execute(
                        "SELECT version,checksum FROM schema_migrations ORDER BY version"
                    )
                    assert cursor.fetchall() == history
                dump(
                    destination / "summary.json",
                    {
                        "before_writes": combined(before, before_repeat),
                        "after_writes": combined(after, after_repeat),
                        "stage_order": [
                            "before",
                            "after",
                            "after_repeat",
                            "before_repeat",
                        ],
                        "stages": {
                            "before": baseline,
                            "after": selected,
                            "after_repeat": selected_repeat,
                            "before_repeat": baseline_repeat,
                        },
                        "product_status": 1,
                        "product_is_deleted": False,
                        "samples_per_configuration": 200,
                        "sampled_rows_unchanged": True,
                        "clone_history_unchanged": True,
                        "source_database_untouched": True,
                        "clone_dropped_on_exit": True,
                        "index_retention": retained,
                    },
                )
        finally:
            with admin.cursor() as cursor:
                cursor.execute(
                    sql.SQL("DROP DATABASE {} WITH (FORCE)").format(
                        sql.Identifier(name)
                    )
                )


def orm_measure(connection, destination):
    statements = []

    def capture(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append((statement, parameters))

    event.listen(engine, "before_cursor_execute", capture)
    try:
        with SessionLocal() as session:
            products = crud_product.catalogue(
                session, category_id=None, skip=0, limit=100
            )
            ids = [p.product_id for p in products]
            assert len(ids) == 100
    finally:
        event.remove(engine, "before_cursor_execute", capture)
    results = []
    for statement, parameters in statements:
        with connection.cursor() as cursor:
            cursor.execute(
                "EXPLAIN (ANALYZE,BUFFERS,FORMAT JSON) " + statement, parameters
            )
            results.append(cursor.fetchone()[0][0])
    dump(
        destination / "orm_catalogue.json",
        {
            "statements": [{"sql": s, "parameters": p} for s, p in statements],
            "plans": results,
            "product_ids": ids,
        },
    )
    return {
        "ids": ids,
        "execution_ms": sum(p["Execution Time"] for p in results),
        "indexes": sorted(
            {
                n["Index Name"]
                for p in results
                for n in nodes(p["Plan"])
                if "Index Name" in n
            }
        ),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--approved-write-clone",
        action="store_true",
        help="Only measure approved product writes on a disposable clone of a post-007 fixture",
    )
    args = parser.parse_args()
    if not settings.DB_NAME.startswith("indexing_v2_"):
        raise SystemExit("Only a prepared indexing_v2_* benchmark database is allowed")
    args.output.mkdir(parents=True, exist_ok=False)
    if args.approved_write_clone:
        approved_write_pair(args.output)
        return
    WRITES.update(
        {
            "order_insert": 'INSERT INTO "order"(buyer_id,contact_id,payment_method_id,total_amount,final_amount) VALUES(7,7,1,1000,1000)',
            "role_insert": "INSERT INTO user_role(user_id,role_id) VALUES(2000042,1)",
        }
    )
    QUERIES["Q17_voucher_missing"] = (
        'SELECT order_id FROM "order" WHERE voucher_id=4 ORDER BY order_id'
    )
    connection = connect()
    connection.autocommit = True
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT version FROM schema_migrations ORDER BY version")
            assert [r[0] for r in cursor.fetchall()] == [
                "001",
                "002",
                "003",
                "004",
                "005",
                "006",
            ]
            cursor.execute("VACUUM ANALYZE")
        source = snapshot()
        before = args.output / "before"
        before.mkdir()
        before_results = {
            k: read_measure(connection, k, q, before, 5) for k, q in QUERIES.items()
        }
        before_orm = orm_measure(connection, before)
        before_writes = write_measure(connection, before, 100)
        before_bytes = inventory(connection, before / "inventory.csv")
        applied = run_migrations()
        assert applied == ["007"]
        assert run_migrations() == []
        assert snapshot() == source, "Upgrade changed source rows"
        with connection.cursor() as cursor:
            cursor.execute("VACUUM ANALYZE")
        after = args.output / "after"
        after.mkdir()
        after_results = {
            k: read_measure(connection, k, q, after, 5) for k, q in QUERIES.items()
        }
        after_orm = orm_measure(connection, after)
        after_writes = write_measure(connection, after, 100)
        after_bytes = inventory(connection, after / "inventory.csv")
        dump(
            args.output / "index_retention.json",
            verify_retained(before / "inventory.csv", after / "inventory.csv"),
        )
        for key in QUERIES:
            assert (
                before_results[key]["result_sha256"]
                == after_results[key]["result_sha256"]
            ), key
        assert before_orm["ids"] == after_orm["ids"]
        dump(
            args.output / "summary.json",
            {
                "applied": applied,
                "replay_noop": True,
                "source_digest_unchanged": True,
                "before": before_results,
                "after": after_results,
                "before_writes": before_writes,
                "after_writes": after_writes,
                "orm_before": before_orm,
                "orm_after": after_orm,
                "before_index_bytes": before_bytes,
                "after_index_bytes": after_bytes,
            },
        )
        print(
            json.dumps(
                {
                    "applied": applied,
                    "queries_equal": len(QUERIES),
                    "orm_ids_equal": True,
                    "source_unchanged": True,
                }
            ),
            flush=True,
        )
    finally:
        connection.close()


if __name__ == "__main__":
    main()
