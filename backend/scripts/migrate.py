"""Transactional SQL migrations: session lock, checksums, exact baseline contract."""

import argparse
import hashlib
import json
import os
from pathlib import Path

import psycopg2

from app.core.config import settings

DATABASE_DIR = Path(os.getenv("DATABASE_SRC", Path(__file__).resolve().parents[2] / "database"))
LOCK_ID = 7363194004


def connect(database: str | None = None):
    args = settings.database_connect_args
    if database is not None:
        args["dbname"] = database
    return psycopg2.connect(**args)


def schema_contract(connection) -> dict:
    """Structural baseline fingerprint, without copying application data or secrets."""
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT c.relname,a.attname,format_type(a.atttypid,a.atttypmod),a.attnotnull,
                   pg_get_expr(d.adbin,d.adrelid)
            FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
            JOIN pg_attribute a ON a.attrelid=c.oid AND a.attnum>0 AND NOT a.attisdropped
            LEFT JOIN pg_attrdef d ON d.adrelid=c.oid AND d.adnum=a.attnum
            WHERE n.nspname='public' AND c.relkind IN ('r','p') AND c.relname<>'schema_migrations'
            ORDER BY c.relname,a.attnum
        """)
        columns = cursor.fetchall()
        cursor.execute("""
            SELECT c.relname,k.contype,pg_get_constraintdef(k.oid)
            FROM pg_constraint k JOIN pg_class c ON c.oid=k.conrelid
            WHERE c.relnamespace='public'::regnamespace AND c.relname<>'schema_migrations'
            ORDER BY c.relname,k.contype,pg_get_constraintdef(k.oid)
        """)
        constraints = cursor.fetchall()
        cursor.execute(
            "SELECT indexdef FROM pg_indexes WHERE schemaname='public' "
            "AND tablename<>'schema_migrations' ORDER BY indexdef"
        )
        indexes = [row[0] for row in cursor.fetchall()]
        cursor.execute("""
            SELECT c.relname,t.tgname,pg_get_triggerdef(t.oid)
            FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid
            WHERE NOT t.tgisinternal AND c.relnamespace='public'::regnamespace
            ORDER BY c.relname,t.tgname
        """)
        triggers = cursor.fetchall()
    return json.loads(
        json.dumps({"columns": columns, "constraints": constraints, "indexes": indexes, "triggers": triggers})
    )


def run_migrations(directory: Path | None = None) -> list[str]:
    directory = directory or DATABASE_DIR / "04_migrations"
    files = sorted(directory.glob("[0-9][0-9][0-9]_*.sql"))
    versions = [path.name.split("_", 1)[0] for path in files]
    if not files or len(set(versions)) != len(versions):
        raise RuntimeError("Missing migrations or duplicate migration versions")
    connection = connect()
    applied = []
    try:
        # Session lock survives individual commits and serializes startup processes.
        with connection.cursor() as cursor:
            cursor.execute("SET lock_timeout='15s'")
            cursor.execute("SET statement_timeout='15min'")
            cursor.execute("SELECT pg_advisory_lock(%s)", (LOCK_ID,))
            cursor.execute("SELECT to_regclass('public.schema_migrations')")
            exists = cursor.fetchone()[0] is not None
            if exists:
                cursor.execute("SELECT version,checksum FROM schema_migrations ORDER BY version")
                history = dict(cursor.fetchall())
            else:
                history = {}
        if not history:
            expected = json.loads((DATABASE_DIR / "baseline_v0.json").read_text())
            if schema_contract(connection) != expected:
                raise RuntimeError("Existing schema differs from baseline v0; review drift before migration")
        if list(history) != versions[: len(history)]:
            raise RuntimeError("Migration history is not a supported prefix of local versions")
        checksums = {p.name.split("_", 1)[0]: hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
        if any(checksums.get(version) != checksum for version, checksum in history.items()):
            raise RuntimeError("Applied migration checksum mismatch; do not edit migration history")
        with connection.cursor() as cursor:
            cursor.execute("""CREATE TABLE IF NOT EXISTS schema_migrations(
                version varchar(3) PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
                checksum char(64) NOT NULL)""")
        connection.commit()
        for path in files:
            version = path.name.split("_", 1)[0]
            if version in history:
                continue
            # Each SQL file and its history row form one atomic transaction.
            with connection, connection.cursor() as cursor:
                cursor.execute("SET LOCAL lock_timeout='15s'")
                cursor.execute(path.read_text())
                cursor.execute(
                    "INSERT INTO schema_migrations(version,checksum) VALUES(%s,%s)", (version, checksums[version])
                )
            applied.append(version)
    finally:
        # Closing also releases the advisory lock after failed DDL/rollback.
        connection.close()
    return applied


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--export-baseline", action="store_true", help="Print structural fingerprint; use only on pristine v0"
    )
    args = parser.parse_args()
    if args.export_baseline:
        with connect() as connection:
            print(json.dumps(schema_contract(connection), indent=2))
    else:
        print(json.dumps({"applied": run_migrations()}))


if __name__ == "__main__":
    main()
