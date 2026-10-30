"""CLI: full, incremental, reconcile, worker, status, retry-dead. No timestamp/MAX-ID cursor."""

import argparse
import json
import logging
import signal
import threading
import uuid
from datetime import UTC, datetime

from psycopg2.extras import Json, RealDictCursor
from pymongo.errors import PyMongoError

from app.core.config import settings
from app.core.logging import setup_logging
from app.services.mongo import get_database
from etl import errors, load, quality
from etl.extract import SOURCES, Source
from etl.pipelines import aggregate, media
from etl.pipelines.documents import project
from scripts.migrate import connect

LOCK = 7363195005
logger = logging.getLogger("etl")


def state(connection, name, value):
    with connection, connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO etl_state(name,value) VALUES(%s,%s) ON CONFLICT(name) "
            "DO UPDATE SET value=excluded.value,updated_at=clock_timestamp()",
            (name, Json(value)),
        )


def backlog(connection):
    with connection.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute("""SELECT count(*) FILTER(WHERE status<>'done') AS pending,
            count(*) FILTER(WHERE status='dead') AS dead,
            COALESCE(EXTRACT(epoch FROM clock_timestamp()-min(created_at)
                FILTER(WHERE status<>'done')),0)::float AS oldest_pending_seconds
            FROM etl_outbox""")
        result = dict(cursor.fetchone())
    connection.commit()
    return result


def failure(connection, database, event, run_id, error):
    error_code = errors.code(error)
    attempts = event["attempts"] + 1
    delay = min(900, settings.ETL_BACKOFF_SECONDS * 2 ** min(attempts - 1, 10))
    with connection, connection.cursor() as cursor:
        cursor.execute(
            """UPDATE etl_outbox SET attempts=%s,status=%s,available_at=clock_timestamp()+%s*interval '1 second',
            last_error_code=%s,last_run_id=%s WHERE event_id=%s""",
            (
                attempts,
                "dead" if attempts >= settings.ETL_MAX_ATTEMPTS else "pending",
                delay,
                error_code,
                str(run_id),
                event["event_id"],
            ),
        )
    errors.record(database, event, run_id, error_code, attempts)
    logger.warning(
        "ETL event deferred", extra={"run_id": str(run_id), "event_id": event["event_id"], "error_code": error_code}
    )


def retry_full_error(connection, database, entity, key, run_id, error):
    with connection, connection.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(
            "SELECT * FROM etl_outbox WHERE entity_type=%s AND entity_key=%s "
            "AND status<>'done' ORDER BY event_id LIMIT 1",
            (entity, Json(key)),
        )
        event = cursor.fetchone()
        if event is None:
            table, column, _ = SOURCES[entity]
            source_key = {column: key["id"]}
            if entity == "system_log":
                source_key["created_at"] = key["created_at"]
            cursor.execute(
                """INSERT INTO etl_outbox(source_table,source_key,entity_type,entity_key,operation)
                VALUES(%s,%s,%s,%s,'UPDATE') RETURNING *""",
                (table, Json(source_key), entity, Json(key)),
            )
            event = cursor.fetchone()
    failure(connection, database, event, run_id, error)


def process_batch(connection, database, run_id):
    with connection.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(
            """SELECT * FROM etl_outbox WHERE status IN ('pending','dead') AND available_at<=clock_timestamp()
            ORDER BY event_id LIMIT %s FOR UPDATE SKIP LOCKED""",
            (settings.ETL_BATCH_SIZE,),
        )
        events = [dict(row) for row in cursor.fetchall()]
    touched = []
    count = 0
    failed = 0
    attempted = 0
    with Source() as source:
        for event in events:
            attempted += 1
            entity, key = event["entity_type"], event["entity_key"]
            touched.append((entity, key))
            try:
                document = project(source, entity, key, run_id)
                load.apply(entity, key, document, database, run_id)
                errors.resolve(database, event["event_id"])
                with connection, connection.cursor() as cursor:
                    cursor.execute(
                        """UPDATE etl_outbox SET status='done',processed_at=clock_timestamp(),last_error_code=NULL,
                        last_run_id=%s WHERE event_id=%s""",
                        (str(run_id), event["event_id"]),
                    )
                count += 1
            except Exception as error:
                connection.rollback()
                failure(connection, database, event, run_id, error)
                failed += 1
                if isinstance(error, PyMongoError):
                    break
    connection.commit()
    return attempted, count, failed, touched


def sweep(source, database, run_id):
    """Mark stale ETL projections deleted, preserving Mongo-owned fields and unprojected docs."""
    changed = 0
    for entity, (_, column, collection) in SOURCES.items():
        for document in database[collection].find({"etl": {"$ne": None}, "deleted": {"$ne": True}}):
            key = {"id": document[column]}
            if entity == "system_log":
                # IDs retain the original naive composite key even after time normalization.
                key["created_at"] = document.get("etl", {}).get("source_created_at")
                if not key["created_at"]:
                    continue
            if source.get(entity, key) is None:
                load.apply(entity, key, None, database, run_id)
                changed += 1
    return changed


def execute(mode="incremental", database=None):
    connection = connect()
    run_id = uuid.uuid4()
    database = database if database is not None else get_database()
    details = {}
    rows_in = rows_out = error_count = 0
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_try_advisory_lock(%s)", (LOCK,))
            if not cursor.fetchone()[0]:
                raise RuntimeError("etl_worker_busy")
            cursor.execute("INSERT INTO etl_runs(run_id,mode) VALUES(%s,%s)", (str(run_id), mode))
        connection.commit()
        state(connection, "heartbeat", {"run_id": str(run_id), "mode": mode})
        if mode == "full":
            try:
                details["media"] = media.run()
            except Exception:
                # Do not mark bootstrap initialized if files could not be copied.
                raise
            with Source() as source:
                for entity in SOURCES:
                    counters = {"rows_in": 0, "rows_out": 0, "errors": 0}
                    for key in source.keys(entity):
                        counters["rows_in"] += 1
                        rows_in += 1
                        try:
                            document = project(source, entity, key, run_id)
                            load.apply(entity, key, document, database, run_id)
                            counters["rows_out"] += int(document is not None)
                            rows_out += int(document is not None)
                        except Exception as error:
                            counters["errors"] += 1
                            error_count += 1
                            retry_full_error(connection, database, entity, key, run_id, error)
                            if isinstance(error, PyMongoError):
                                raise
                    details[entity] = counters
            state(connection, "full_initialized", True)
        touched = []
        if mode in ("full", "incremental"):
            for _ in range(20 if mode == "full" else 1):
                total, done, failed, keys = process_batch(connection, database, run_id)
                rows_in += total
                rows_out += done
                error_count += failed
                touched.extend(keys)
                if total < settings.ETL_BATCH_SIZE:
                    break
        with Source() as source:
            if mode in ("full", "reconcile"):
                details["swept"] = sweep(source, database, run_id)
            try:
                details["aggregate"] = aggregate.rebuild(source, connection, run_id)
            except Exception as error:
                connection.rollback()
                error_count += 1
                details["aggregate_error"] = errors.code(error)
            details["quality"] = quality.check(
                source, database, run_id, deep=mode in ("full", "reconcile"), touched=touched
            )
        details["backlog"] = backlog(connection)
        status = (
            "success"
            if not (error_count or details["quality"]["mismatches"] or details["backlog"]["pending"])
            else "partial"
        )
        if mode in ("full", "reconcile") and status == "success":
            state(connection, "last_deep_check", datetime.now(UTC).date().isoformat())
        with connection, connection.cursor() as cursor:
            cursor.execute(
                "UPDATE etl_runs SET ended_at=clock_timestamp(),status=%s,rows_in=%s,"
                "rows_out=%s,errors=%s,details=%s WHERE run_id=%s",
                (status, rows_in, rows_out, error_count, Json(details), str(run_id)),
            )
        state(connection, "heartbeat", {"run_id": str(run_id), "status": status})
        result = {
            "run_id": str(run_id),
            "status": status,
            "mode": mode,
            "rows_in": rows_in,
            "rows_out": rows_out,
            "errors": error_count,
            "details": details,
        }
        logger.info(
            "ETL run completed",
            extra={
                "run_id": str(run_id),
                "etl_status": status,
                "rows_in": rows_in,
                "rows_out": rows_out,
                "errors": error_count,
            },
        )
        return result
    except Exception as error:
        connection.rollback()
        logger.error("ETL run failed", extra={"run_id": str(run_id), "error_code": errors.code(error)})
        try:
            with connection, connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE etl_runs SET ended_at=clock_timestamp(),status='failed',"
                    "rows_in=%s,rows_out=%s,errors=%s,details=%s WHERE run_id=%s",
                    (
                        rows_in,
                        rows_out,
                        error_count + 1,
                        Json({**details, "error_code": errors.code(error)}),
                        str(run_id),
                    ),
                )
        except Exception:
            connection.rollback()
        raise
    finally:
        connection.close()


def status():
    connection = connect()
    try:
        result = backlog(connection)
        with connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                "SELECT run_id,mode,status,started_at,ended_at,rows_in,rows_out,errors "
                "FROM etl_runs ORDER BY started_at DESC LIMIT 1"
            )
            row = cursor.fetchone()
            result["last_run"] = dict(row) if row else None
        return result
    finally:
        connection.close()


def worker():
    stop = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())
    while not stop.is_set():
        connection = connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT name,value FROM etl_state WHERE name IN ('full_initialized','last_deep_check')")
                values = dict(cursor.fetchall())
        finally:
            connection.close()
        try:
            mode = "full" if not values.get("full_initialized") else "incremental"
            execute(mode)
            if mode != "full" and values.get("last_deep_check") != datetime.now(UTC).date().isoformat():
                execute("reconcile")
        except Exception as error:
            logger.error("ETL cycle failed", extra={"error_code": errors.code(error)})
        stop.wait(settings.ETL_POLL_SECONDS)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "mode", choices=("full", "incremental", "reconcile", "worker", "status", "retry-dead", "health")
    )
    args = parser.parse_args()
    setup_logging(settings.LOG_LEVEL, settings.LOG_FORMAT)
    if args.mode == "worker":
        worker()
        return
    if args.mode == "status":
        print(json.dumps(status(), default=str))
        return
    if args.mode == "health":
        connection = connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT clock_timestamp()-updated_at < interval '5 minutes' FROM etl_state WHERE name='heartbeat'"
                )
                row = cursor.fetchone()
                if not row or not row[0]:
                    raise SystemExit(1)
        finally:
            connection.close()
        return
    if args.mode == "retry-dead":
        connection = connect()
        try:
            with connection, connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE etl_outbox SET status='pending',available_at=clock_timestamp() WHERE status='dead'"
                )
                print(json.dumps({"requeued": cursor.rowcount}))
        finally:
            connection.close()
        return
    try:
        result = execute(args.mode)
    except Exception as error:
        logger.error("ETL command failed", extra={"error_code": errors.code(error)})
        raise SystemExit(1) from None
    print(json.dumps(result, default=str))
    if result["status"] != "success":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
