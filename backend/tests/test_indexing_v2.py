"""Upgrade invariants for indexing v2 on a disposable baseline database."""

import hashlib
import json
import uuid
from contextlib import closing

from psycopg2 import sql
from sqlalchemy.engine import make_url

from app.core.config import settings
from scripts.init_db import load_schema
from scripts.migrate import DATABASE_DIR, connect, run_migrations
from scripts.verify_indexing_v2 import verify


def snapshot():
    """Compare source values and constraints, never expose hashes/tokens in output."""
    with closing(connect()) as connection, connection.cursor() as cursor:
        cursor.execute("""SELECT relname FROM pg_class WHERE relnamespace='public'::regnamespace
            AND relkind IN ('r','p') AND NOT relispartition AND relname<>'schema_migrations' ORDER BY relname""")
        tables = [r[0] for r in cursor.fetchall()]
        values = {}
        for table in tables:
            cursor.execute(
                sql.SQL(
                    "SELECT count(*),md5(coalesce(string_agg(to_jsonb(t)::text,E'\\n' ORDER BY to_jsonb(t)::text),'')) FROM {} t"
                ).format(sql.Identifier(table))
            )
            values[table] = cursor.fetchone()
        cursor.execute("""SELECT conrelid::regclass::text,conname,pg_get_constraintdef(oid)
            FROM pg_constraint WHERE connamespace='public'::regnamespace
            AND conrelid<>'schema_migrations'::regclass ORDER BY 1,2""")
        constraints = cursor.fetchall()
        cursor.execute("""SELECT t.relname,c.conname,pg_get_constraintdef(c.oid)
            FROM pg_constraint c JOIN pg_class t ON t.oid=c.conrelid
            WHERE t.relnamespace='public'::regnamespace AND c.contype IN ('p','u') ORDER BY 1,2""")
        unique = cursor.fetchall()
    digest = hashlib.sha256(
        json.dumps([values, constraints, unique], default=str).encode()
    ).hexdigest()
    return digest


def test_upgrade_from_006_preserves_rows_constraints_and_pending_work(
    tmp_path, monkeypatch
):
    name = "indexing_v2_upgrade_" + uuid.uuid4().hex[:12]
    with closing(connect("postgres")) as administration:
        administration.autocommit = True
        with administration.cursor() as cursor:
            cursor.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    try:
        monkeypatch.setattr(
            settings,
            "DATABASE_URL",
            make_url(settings.DATABASE_URL)
            .set(database=name)
            .render_as_string(hide_password=False),
        )
        load_schema()
        baseline = tmp_path / "baseline"
        baseline.mkdir()
        originals = {}
        for path in (DATABASE_DIR / "04_migrations").glob("*.sql"):
            if path.name[:3].isdigit() and int(path.name[:3]) <= 6:
                originals[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
                (baseline / path.name).write_bytes(path.read_bytes())
        assert run_migrations(baseline) == ["001", "002", "003", "004", "005", "006"]
        with (
            closing(connect()) as connection,
            connection,
            connection.cursor() as cursor,
        ):
            # Shared seed URLs and repeated OTPs are legal data, including after upgrade.
            cursor.execute(
                "INSERT INTO product_image(product_id,image_url) SELECT 1,image_url FROM product_image WHERE product_id=2 LIMIT 1"
            )
            cursor.execute(
                "UPDATE user_secret SET password_reset_token='123456' WHERE user_id IN (3,4)"
            )
            cursor.execute("""INSERT INTO etl_outbox(source_table,source_key,entity_type,entity_key,operation,status,available_at)
                SELECT 'indexing_upgrade',jsonb_build_object('product_id',1),'product',jsonb_build_object('id',1),
                'UPDATE',s,t FROM (VALUES ('pending',timestamptz '2020-01-01'),
                ('dead',timestamptz '2020-01-01'),('pending',timestamptz '2100-01-01'),
                ('done',timestamptz '2020-01-01')) v(s,t)""")
        before = snapshot()
        assert run_migrations() == ["007"]
        assert snapshot() == before
        assert verify()["result"] == "PASS"
        assert run_migrations() == []
        for filename, checksum in originals.items():
            assert (
                hashlib.sha256(
                    (DATABASE_DIR / "04_migrations" / filename).read_bytes()
                ).hexdigest()
                == checksum
            )
        with (
            closing(connect()) as first,
            closing(connect()) as second,
            first.cursor() as a,
            second.cursor() as b,
        ):
            statement = """SELECT event_id FROM etl_outbox WHERE source_table='indexing_upgrade'
                AND status IN ('pending','dead') AND available_at<=clock_timestamp()
                ORDER BY event_id LIMIT 100 FOR UPDATE SKIP LOCKED"""
            a.execute(statement)
            assert len(a.fetchall()) == 2
            b.execute(statement)
            assert b.fetchall() == []
            first.rollback()
            b.execute(statement)
            assert len(b.fetchall()) == 2
        with closing(connect()) as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT count(*) FROM pg_index WHERE indrelid IN (SELECT oid FROM pg_class WHERE relnamespace='public'::regnamespace) AND NOT indisvalid"
            )
            assert cursor.fetchone()[0] == 0
    finally:
        with closing(connect("postgres")) as administration:
            administration.autocommit = True
            with administration.cursor() as cursor:
                cursor.execute(
                    sql.SQL("DROP DATABASE {} WITH (FORCE)").format(
                        sql.Identifier(name)
                    )
                )
