"""Real PG migration invariants, transaction rollback, fragment writes and pruning."""

import os
import shutil
import uuid
from contextlib import closing
from decimal import Decimal

import psycopg2
import pytest
from psycopg2 import sql
from sqlalchemy import event, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError

from app.core.config import Settings, settings
from app.core.database import SessionLocal, engine
from app.models import SystemLog, User, UserProfile, UserSecret, UserWallet
from scripts.init_db import load_schema
from scripts.migrate import DATABASE_DIR, connect, run_migrations


def migration_copy(tmp_path):
    for path in (DATABASE_DIR / "04_migrations").glob("*.sql"):
        shutil.copy(path, tmp_path / path.name)
    return tmp_path


def test_migration_repeat_and_checksum_refusal(tmp_path):
    assert run_migrations() == []
    directory = migration_copy(tmp_path)
    with (directory / "001_indexes.sql").open("a") as target:
        target.write("\n-- tampered history\n")
    with pytest.raises(RuntimeError, match="checksum"):
        run_migrations(directory)


def test_failed_migration_rolls_back_ddl_and_history(tmp_path):
    directory = migration_copy(tmp_path)
    next_version = f"{max(int(p.name[:3]) for p in directory.glob('*.sql')) + 1:03d}"
    (directory / f"{next_version}_failure.sql").write_text("CREATE TABLE day4_must_rollback(id int); SELECT 1/0;")
    with pytest.raises(psycopg2.errors.DivisionByZero):
        run_migrations(directory)
    with connect() as connection, connection.cursor() as cursor:
        cursor.execute("SELECT to_regclass('day4_must_rollback')")
        assert cursor.fetchone()[0] is None
        cursor.execute("SELECT count(*) FROM schema_migrations WHERE version=%s", (next_version,))
        assert cursor.fetchone()[0] == 0
    assert run_migrations() == []  # failed run released its session lock


def test_baseline_drift_is_rejected(monkeypatch):
    name = "day4_drift_" + uuid.uuid4().hex[:12]
    with closing(connect("postgres")) as administration:
        administration.autocommit = True
        with administration.cursor() as cursor:
            cursor.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    try:
        monkeypatch.setattr(
            settings,
            "DATABASE_URL",
            make_url(settings.DATABASE_URL).set(database=name).render_as_string(hide_password=False),
        )
        load_schema()
        with closing(connect()) as connection, connection, connection.cursor() as cursor:
            cursor.execute('ALTER TABLE "user" ADD COLUMN unexpected text')
        with pytest.raises(RuntimeError, match="baseline v0"):
            run_migrations()
        with closing(connect()) as connection, connection, connection.cursor() as cursor:
            cursor.execute("SELECT to_regclass('schema_migrations')")
            assert cursor.fetchone()[0] is None
    finally:
        with closing(connect("postgres")) as administration:
            administration.autocommit = True
            with administration.cursor() as cursor:
                cursor.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(name)))


def test_database_url_is_canonical_and_password_is_escaped():
    config = Settings(
        _env_file=None,
        SECRET_KEY="unit",
        DATABASE_URL="postgresql://url_user:p%40ss%3Aword@pg.example:5544/url_db?sslmode=require&application_name=day4",
        DB_NAME="wrong",
        DB_USER="wrong",
    )
    assert config.DB_NAME == "url_db" and config.DB_HOST == "pg.example"
    assert config.database_connect_args["password"] == "p@ss:word"
    assert config.database_connect_args["sslmode"] == "require"
    config = Settings(
        _env_file=None, SECRET_KEY="unit", DATABASE_URL="", DB_USER="u", DB_PASSWORD="p@ss:/#", DB_NAME="target"
    )
    assert make_url(config.DATABASE_URL).password == "p@ss:/#"


def test_users_full_is_read_only_and_covers_twenty_fields():
    with engine.connect() as connection:
        columns = inspect(connection).get_columns("users_full")
        assert len(columns) == 20
        assert {c["name"] for c in columns} == {
            "user_id",
            "username",
            "email",
            "password_hash",
            "random_key",
            "full_name",
            "phone_number",
            "address",
            "balance",
            "is_active",
            "is_deleted",
            "created_at",
            "updated_at",
            "last_login",
            "email_verified",
            "email_verification_token",
            "password_reset_token",
            "password_reset_expires",
            "trust_score",
            "avatar_url",
        }
        missing = connection.execute(
            text("""SELECT count(*) FROM user_core c
            LEFT JOIN user_profile p USING(user_id) LEFT JOIN user_secret s USING(user_id)
            LEFT JOIN user_wallet w USING(user_id) WHERE p.user_id IS NULL OR s.user_id IS NULL OR w.user_id IS NULL""")
        ).scalar_one()
        assert missing == 0
    with (
        connect() as connection,
        connection.cursor() as cursor,
        pytest.raises(psycopg2.errors.ObjectNotInPrerequisiteState),
    ):
        cursor.execute("UPDATE users_full SET username='must-not-write' WHERE false")


def test_fragment_writes_are_atomic_and_auth_does_not_load_secrets_by_default():
    token = uuid.uuid4().hex[:15]
    with SessionLocal() as session:
        user = User(
            username="d4_" + token,
            email=token + "@example.invalid",
            password_hash="test-hash",
            random_key=uuid.uuid4().hex,
            full_name="Fragment Test",
        )
        session.add(user)
        session.flush()
        identifier = user.user_id
        for cls in (UserProfile, UserSecret, UserWallet):
            assert session.get(cls, identifier) is not None
        user.full_name = "Changed"
        user.balance = Decimal("123.4500")
        session.flush()
        assert session.execute(
            text("SELECT balance FROM user_wallet WHERE user_id=:id"), {"id": identifier}
        ).scalar_one() == Decimal("123.4500")
        session.rollback()
        assert session.get(User, identifier) is None
        for cls in (UserProfile, UserSecret, UserWallet):
            assert session.get(cls, identifier) is None
    statements = []

    def record(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", record)
    try:
        with SessionLocal() as session:
            session.query(User).filter(User.email == "admin@oldshop.com").first()
        assert statements and all(
            "user_secret" not in statement and "user_wallet" not in statement for statement in statements
        )
    finally:
        event.remove(engine, "before_cursor_execute", record)


def test_fragment_constraint_failure_rolls_back_core():
    token = uuid.uuid4().hex[:15]
    with SessionLocal() as session:
        user = User(
            username=token,
            email=token + "@example.invalid",
            password_hash="hash",
            random_key=uuid.uuid4().hex,
            full_name=None,
        )
        session.add(user)
        with pytest.raises(IntegrityError):
            session.flush()
        session.rollback()
        assert session.query(User).filter(User.username == token).first() is None


def test_log_identity_month_routing_and_overflow():
    from datetime import datetime

    assert [col.name for col in inspect(SystemLog).primary_key] == ["log_id", "created_at"]
    with SessionLocal() as session:
        records = [
            SystemLog(action="DAY4_TEST", created_at=datetime(2026, 10, 1)),
            SystemLog(action="DAY4_TEST", created_at=datetime(2200, 1, 1)),
        ]
        session.add_all(records)
        session.flush()
        assert all(record.log_id for record in records)
        assert session.get(SystemLog, (records[0].log_id, records[0].created_at)) is records[0]
        routes = (
            session.execute(
                text("SELECT tableoid::regclass::text FROM system_log WHERE action='DAY4_TEST' ORDER BY created_at")
            )
            .scalars()
            .all()
        )
        assert routes == ["system_log_202610", "system_log_default"]
        session.rollback()


def test_partition_pruning_and_inbound_foreign_keys():
    with engine.connect() as connection:
        plan = connection.execute(text('EXPLAIN (FORMAT JSON) SELECT * FROM "order" WHERE order_id=1')).scalar_one()[0][
            "Plan"
        ]

        def relations(node):
            return ([node["Relation Name"]] if "Relation Name" in node else []) + [
                r for child in node.get("Plans", []) for r in relations(child)
            ]

        assert len([name for name in relations(plan) if name.startswith("order_h")]) == 1
        keys = connection.execute(
            text("""SELECT conrelid::regclass::text,confrelid::regclass::text,confdeltype
            FROM pg_constraint WHERE contype='f' AND confrelid='public.\"order\"'::regclass""")
        ).all()
        assert ("transaction", '"order"', "c") in keys
        assert any(key[0] == "order_detail" for key in keys)
        assert (
            connection.execute(
                text("SELECT count(*) FROM pg_constraint WHERE contype='f' AND confrelid='user_core'::regclass")
            ).scalar_one()
            >= 14
        )


def test_sql_user_helpers_work_after_split():
    token = uuid.uuid4().hex[:15]
    with connect() as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT create_user_with_hash(%s,%s,'password123','SQL User')", (token, token + "@example.invalid")
        )
        identifier = cursor.fetchone()[0]
        cursor.execute("INSERT INTO user_role(user_id,role_id) VALUES(%s,3)", (identifier,))
        cursor.execute("SELECT user_id FROM authenticate_user(%s,'password123')", (token,))
        assert cursor.fetchone()[0] == identifier
        cursor.execute("SELECT log_user_login(%s)", (identifier,))
        cursor.execute("SELECT log_id,log_time FROM get_audit_trail('user',%s)", (identifier,))
        assert all(log_id and created_at for log_id, created_at in cursor.fetchall())
        connection.rollback()


def test_password_reset_and_profile_wallet_updates_after_split():
    from app.core.security import hash_password, verify_password
    from app.crud.user import crud_user

    token = uuid.uuid4().hex[:15]
    with SessionLocal() as session:
        user = User(
            username=token,
            email=token + "@example.invalid",
            password_hash=hash_password("before123"),
            random_key=uuid.uuid4().hex,
            full_name="Reset test",
        )
        session.add(user)
        session.commit()
        identifier = user.user_id
        try:
            otp = crud_user.request_otp_reset(session, user.email)
            assert otp and len(otp) == 6
            assert not crud_user.verify_otp_and_reset(session, user.email, "wrong", "after123")
            assert crud_user.verify_otp_and_reset(session, user.email, otp, "after123")
            session.refresh(user)
            assert verify_password("after123", user.password_hash)
            assert user.password_reset_token is None
            user.full_name = "Changed profile"
            user.balance = Decimal("42.0000")
            session.commit()
            with session.bind.connect() as connection:
                row = connection.execute(
                    text("SELECT full_name,balance FROM users_full WHERE user_id=:id"), {"id": identifier}
                ).one()
                assert row.full_name == "Changed profile" and row.balance == Decimal("42.0000")
        finally:
            session.delete(user)
            session.commit()


def test_partitioned_order_still_blocks_self_buying_and_invalid_fk():
    with connect() as connection, connection.cursor() as cursor:
        cursor.execute("SELECT product_id,seller_id FROM product ORDER BY product_id LIMIT 1")
        product_id, seller_id = cursor.fetchone()
        cursor.execute(
            """INSERT INTO "order"(buyer_id,contact_id,payment_method_id,total_amount,final_amount)
                          VALUES(%s,1,1,1000,1000) RETURNING order_id""",
            (seller_id,),
        )
        order_id = cursor.fetchone()[0]
        cursor.execute("SAVEPOINT self_buy")
        with pytest.raises(psycopg2.errors.RaiseException, match="Sellers cannot buy"):
            cursor.execute(
                "INSERT INTO order_detail(order_id,product_id,quantity,price_at_purchase,subtotal) "
                "VALUES(%s,%s,1,1000,1000)",
                (order_id, product_id),
            )
        cursor.execute("ROLLBACK TO SAVEPOINT self_buy")
        cursor.execute("SELECT count(*) FROM system_log WHERE action='SELF_BUY_BLOCKED' AND resource_id IS NOT NULL")
        assert cursor.fetchone()[0] == 0  # trigger logging shares the failed transaction
        cursor.execute("SAVEPOINT invalid_fk")
        with pytest.raises(psycopg2.errors.ForeignKeyViolation):
            cursor.execute('UPDATE "order" SET buyer_id=-1 WHERE order_id=%s', (order_id,))
        cursor.execute("ROLLBACK TO SAVEPOINT invalid_fk")
        connection.rollback()


def test_cart_uniqueness_enforced_by_database():
    with connect() as connection, connection.cursor() as cursor:
        cursor.execute("SELECT cart_id,product_id FROM shopping_cart_item LIMIT 1")
        pair = cursor.fetchone()
        if pair is None:
            cursor.execute("SELECT cart_id FROM shopping_cart LIMIT 1")
            cart = cursor.fetchone()[0]
            cursor.execute("SELECT product_id FROM product LIMIT 1")
            pair = (cart, cursor.fetchone()[0])
            cursor.execute("INSERT INTO shopping_cart_item(cart_id,product_id,quantity) VALUES(%s,%s,1)", pair)
        with pytest.raises(psycopg2.errors.UniqueViolation):
            cursor.execute("INSERT INTO shopping_cart_item(cart_id,product_id,quantity) VALUES(%s,%s,1)", pair)
        connection.rollback()


@pytest.mark.skipif(os.getenv("DAY3_INTEGRATION") != "1", reason="Requires MinIO")
def test_minio_product_upload_persists_metadata(client, login, png_bytes, monkeypatch):
    from app.services.storage import delete_media

    monkeypatch.setattr(settings, "STORAGE_BACKEND", "minio")
    response = client.post(
        "/api/v1/products",
        headers=login("user1@gmail.com"),
        data={"category_id": "1", "title": "Day4 metadata", "price": "1000", "quantity": "1"},
        files=[("files", ("demo.png", png_bytes, "image/png"))],
    )
    assert response.status_code == 201, response.text
    url = response.json()["product_images"][0]["image_url"]
    try:
        with engine.connect() as connection:
            row = connection.execute(
                text("SELECT content_type,size_bytes FROM product_image WHERE image_url=:url"), {"url": url}
            ).one()
            assert row.content_type == "image/png" and row.size_bytes == len(png_bytes)
        assert client.get(url).content == png_bytes
    finally:
        delete_media(url)


def test_month_partition_maintenance_preserves_overflow():
    from datetime import datetime

    from scripts.maintain_log_partitions import ensure_month

    date = datetime(2300 + uuid.uuid4().int % 500, 4, 1)
    partition = "system_log_" + date.strftime("%Y%m")
    with connect() as connection, connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO system_log(action,created_at) VALUES('DAY4_MAINTENANCE',%s) RETURNING log_id", (date,)
        )
        identifier = cursor.fetchone()[0]
    try:
        result = ensure_month(date)
        assert result == {"partition": partition, "created": True, "moved": 1}
        assert ensure_month(date)["created"] is False
        with connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT tableoid::regclass::text FROM system_log WHERE log_id=%s AND created_at=%s", (identifier, date)
            )
            assert cursor.fetchone()[0] == partition
    finally:
        with connect() as connection, connection.cursor() as cursor:
            cursor.execute("DELETE FROM system_log WHERE log_id=%s AND created_at=%s", (identifier, date))
            cursor.execute(sql.SQL("DROP TABLE IF EXISTS {}").format(sql.Identifier(partition)))
