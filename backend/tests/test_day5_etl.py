"""At-least-once/outbox invariants on dedicated PG + Mongo DBs; real MinIO unique keys."""

import json
import os
import uuid
from contextlib import closing, contextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from psycopg2.extras import Json
from pymongo.errors import AutoReconnect

from app.core.config import settings
from app.core.database import SessionLocal
from app.models import Product
from app.services.mongo import get_database
from app.services.storage import MinioStorage
from etl import errors, load
from etl.extract import SOURCES, Source
from etl.pipelines.documents import project
from etl.run import LOCK, execute
from etl.transform import QualityError, comparable, dimensions, public_text, utc, vnd
from scripts.migrate import connect


@pytest.mark.parametrize(
    "value,expected", [(Decimal("1000.0000"), 1000), (0, 0), ("9223372036854775807", 9223372036854775807)]
)
def test_vnd_exact_integer(value, expected):
    assert vnd(value) == expected


@pytest.mark.parametrize("value", [Decimal("1.25"), -1, Decimal("NaN"), "9223372036854775808"])
def test_vnd_never_rounds_invalid_source(value):
    with pytest.raises(QualityError):
        vnd(value)


def test_time_origin_is_explicit_and_utc_is_not_shifted_twice():
    naive = datetime(2026, 10, 30, 10)
    assert utc(naive, (naive, "Asia/Ho_Chi_Minh")) == datetime(2026, 10, 30, 3, tzinfo=UTC)
    assert utc(naive, (naive, "UTC")) == datetime(2026, 10, 30, 10, tzinfo=UTC)
    with pytest.raises(QualityError):
        utc(naive, None)
    with pytest.raises(QualityError):
        utc(naive, (naive - timedelta(seconds=1), "UTC"))


def test_public_text_scrubs_common_contacts_and_parses_dimensions():
    result = public_text("Contact qa@example.com 0901234567 https://host/path?token=secret")
    assert "qa@example.com" not in result and "0901234567" not in result and "secret" not in result
    assert dimensions("35x24x2 cm") == {"length": 35.0, "width": 24.0, "height": 2.0, "unit": "cm"}
    assert dimensions("unknown") is None


def query(statement, params=(), one=False):
    with closing(connect()) as connection, connection, connection.cursor() as cursor:
        cursor.execute(statement, params)
        if cursor.description:
            return cursor.fetchone() if one else cursor.fetchall()


@pytest.fixture
def etl_db():
    if os.getenv("DAY5_INTEGRATION") != "1":
        pytest.skip("Requires isolated Day 5 integration databases")
    assert settings.DB_NAME.startswith("day5_test_") and settings.MONGO_DB.startswith("day5_test_")
    database = get_database()
    for _, _, name in SOURCES.values():
        database[name].delete_many({})
    database.etl_errors.delete_many({})
    query("DELETE FROM etl_outbox; DELETE FROM etl_runs; DELETE FROM etl_state; DELETE FROM report_daily_sales")
    result = execute("full", database)
    assert result["status"] == "success", result
    return database


@contextmanager
def product():
    identifier = query(
        "INSERT INTO product(seller_id,category_id,title,price,quantity,status) VALUES(3,1,'ETL test',1,10,1) "
        "RETURNING product_id",
        one=True,
    )[0]
    try:
        yield identifier
    finally:
        query("DELETE FROM product WHERE product_id=%s", (identifier,))


@contextmanager
def order(product_ids=(1,)):
    with closing(connect()) as connection, connection, connection.cursor() as cursor:
        cursor.execute(
            'INSERT INTO "order"(buyer_id,contact_id,payment_method_id,total_amount,final_amount) '
            "VALUES(7,1,1,%s,%s) RETURNING order_id",
            (len(product_ids), len(product_ids)),
        )
        identifier = cursor.fetchone()[0]
        for product_id in product_ids:
            cursor.execute(
                "INSERT INTO order_detail(order_id,product_id,quantity,price_at_purchase,subtotal) VALUES(%s,%s,1,1,1)",
                (identifier, product_id),
            )
    try:
        yield identifier
    finally:
        query(
            'DELETE FROM order_detail WHERE order_id=%s; DELETE FROM "order" WHERE order_id=%s',
            (identifier, identifier),
        )


def drain(database):
    query("UPDATE etl_outbox SET available_at=clock_timestamp() WHERE status<>'done'")
    for _ in range(10):
        result = execute("incremental", database)
        if result["details"]["backlog"]["pending"] == 0:
            return result
    raise AssertionError(result)


def test_full_repeat_preserves_legacy_id_and_mongo_owned_metadata(etl_db):
    doc = etl_db.product_details.find_one({"product_id": 1})
    etl_db.product_details.delete_one({"_id": doc["_id"]})
    doc.update(_id="legacy_product_id", attributes={"ram_gb": 8}, tags=["authoritative"])
    etl_db.product_details.insert_one(doc)
    counts = {name: etl_db[name].count_documents({}) for _, _, name in SOURCES.values()}
    for _ in range(2):
        assert execute("full", etl_db)["status"] == "success"
    stored = etl_db.product_details.find_one({"product_id": 1})
    assert (
        stored["_id"] == "legacy_product_id"
        and stored["attributes"] == {"ram_gb": 8}
        and stored["tags"] == ["authoritative"]
    )
    assert counts == {name: etl_db[name].count_documents({}) for _, _, name in SOURCES.values()}
    assert etl_db.order_snapshots.find_one({"order_id": 5})["payments"][0]["status_code"] == 4


def test_rollback_has_no_committed_outbox_or_provenance(etl_db):
    with closing(connect()) as connection, connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO product(seller_id,category_id,title,price,quantity) VALUES(3,1,'rollback',1,1) "
            "RETURNING product_id"
        )
        identifier = cursor.fetchone()[0]
        cursor.execute(
            "SELECT count(*) FROM etl_outbox WHERE entity_type='product' AND entity_key=%s", (Json({"id": identifier}),)
        )
        assert cursor.fetchone()[0] == 1
        connection.rollback()
    assert (
        query(
            "SELECT count(*) FROM etl_outbox WHERE entity_type='product' AND entity_key=%s",
            (Json({"id": identifier}),),
            one=True,
        )[0]
        == 0
    )
    assert (
        query(
            "SELECT count(*) FROM etl_time_origin WHERE source_table='product' AND source_key=%s",
            (Json({"product_id": identifier}),),
            one=True,
        )[0]
        == 0
    )


def test_late_commit_with_lower_event_id_is_not_skipped(etl_db):
    identifiers = []
    try:
        with closing(connect()) as first, closing(connect()) as second:
            for connection, title in ((first, "late"), (second, "early")):
                with connection.cursor() as cursor:
                    cursor.execute(
                        "INSERT INTO product(seller_id,category_id,title,price,quantity) VALUES(3,1,%s,1,1) "
                        "RETURNING product_id",
                        (title,),
                    )
                    identifiers.append(cursor.fetchone()[0])
            second.commit()
            assert execute("incremental", etl_db)["status"] == "success"
            assert etl_db.product_details.find_one({"product_id": identifiers[0]}) is None
            first.commit()
        assert execute("incremental", etl_db)["status"] == "success"
        assert all(etl_db.product_details.find_one({"product_id": identifier}) for identifier in identifiers)
        assert query("SELECT count(*) FROM etl_outbox WHERE status<>'done'", one=True)[0] == 0
    finally:
        for identifier in identifiers:
            query("DELETE FROM product WHERE product_id=%s", (identifier,))


def test_crash_after_mongo_write_replays_without_duplication(etl_db, monkeypatch):
    with product() as identifier:
        original = errors.resolve

        def fail_ack(*args):
            raise RuntimeError("simulated crash before PG ACK")

        monkeypatch.setattr(errors, "resolve", fail_ack)
        result = execute("incremental", etl_db)
        assert result["status"] == "partial"
        assert etl_db.product_details.count_documents({"product_id": identifier}) == 1
        assert query("SELECT count(*) FROM etl_outbox WHERE status<>'done'", one=True)[0] > 0
        monkeypatch.setattr(errors, "resolve", original)
        assert drain(etl_db)["status"] == "success"
        assert etl_db.product_details.count_documents({"product_id": identifier}) == 1


def test_mongo_failure_keeps_event_and_recovers_from_dead_letter(etl_db, monkeypatch):
    with product() as identifier:
        original = load.apply

        def unavailable(*args, **kwargs):
            raise AutoReconnect("secret must never enter error records")

        monkeypatch.setattr(load, "apply", unavailable)
        monkeypatch.setattr(settings, "ETL_MAX_ATTEMPTS", 1)
        result = execute("incremental", etl_db)
        assert result["details"]["backlog"]["dead"] == 1
        error = etl_db.etl_errors.find_one({"resolved": False})
        assert error["code"] == "mongo_unavailable_or_write_rejected" and "secret" not in json.dumps(error, default=str)
        monkeypatch.setattr(load, "apply", original)
        assert drain(etl_db)["status"] == "success"
        assert etl_db.product_details.find_one({"product_id": identifier})
        assert etl_db.etl_errors.find_one({"_id": error["_id"]})["resolved"] is True


def test_order_child_reparent_refreshes_old_and_new_aggregate(etl_db):
    with order((1, 6)) as first, order((1,)) as second:
        drain(etl_db)
        query(
            """UPDATE order_detail SET order_id=%s WHERE order_id=%s AND product_id=6;
            UPDATE "order" SET total_amount=1,final_amount=1 WHERE order_id=%s;
            UPDATE "order" SET total_amount=2,final_amount=2 WHERE order_id=%s""",
            (second, first, first, second),
        )
        assert drain(etl_db)["status"] == "success"
        assert len(etl_db.order_snapshots.find_one({"order_id": first})["items"]) == 1
        assert len(etl_db.order_snapshots.find_one({"order_id": second})["items"]) == 2
        transaction = query(
            "INSERT INTO transaction(order_id,user_id,payment_method_id,amount) VALUES(%s,7,1,1) RETURNING "
            "transaction_id",
            (first,),
            one=True,
        )[0]
        drain(etl_db)
        query("UPDATE transaction SET order_id=%s WHERE transaction_id=%s", (second, transaction))
        assert drain(etl_db)["status"] == "success"
        assert not etl_db.order_snapshots.find_one({"order_id": first})["payments"]
        assert etl_db.order_snapshots.find_one({"order_id": second})["payments"][0]["transaction_id"] == transaction


def test_image_reparent_uses_actual_fk_and_preserves_object_key(etl_db, png_bytes):
    with product() as first, product() as second:
        path = f"products/{first}/{uuid.uuid4().hex}.png"
        storage = MinioStorage()
        storage.put(path, png_bytes)
        identifier = query(
            "INSERT INTO product_image(product_id,image_url,content_type,size_bytes) "
            "VALUES(%s,%s,'image/png',%s) RETURNING image_id",
            (first, "/media/" + path, len(png_bytes)),
            one=True,
        )[0]
        try:
            drain(etl_db)
            query("UPDATE product_image SET product_id=%s WHERE image_id=%s", (second, identifier))
            assert drain(etl_db)["status"] == "success"
            assert etl_db.product_details.find_one({"product_id": first})["images"] == []
            assert etl_db.product_details.find_one({"product_id": second})["images"][0]["key"] == path
            assert execute("full", etl_db)["status"] == "success"  # no local copy required for genuine S3 uploads
        finally:
            query("DELETE FROM product_image WHERE image_id=%s", (identifier,))
            storage.delete(path)


def test_product_current_dimensions_fanout_leaves_purchase_price_unchanged(etl_db):
    previous = query("SELECT title FROM product WHERE product_id=1", one=True)[0]
    try:
        query("UPDATE product SET title='New current title' WHERE product_id=1")
        assert drain(etl_db)["status"] == "success"
        item = etl_db.order_snapshots.find_one({"order_id": 1})["items"][0]
        assert item["title_current"] == "New current title" and item["price_at_purchase_vnd"] == 150000
    finally:
        query("UPDATE product SET title=%s WHERE product_id=1", (previous,))


def test_voucher_current_metadata_fanout_does_not_reprice_history(etl_db):
    identifier = query(
        "INSERT INTO voucher(code,discount_type,discount_value,valid_from,valid_to) "
        "VALUES(%s,0,1,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP+interval '1 day') RETURNING voucher_id",
        ("ETL" + uuid.uuid4().hex[:15],),
        one=True,
    )[0]
    try:
        with order() as order_id:
            query('UPDATE "order" SET voucher_id=%s WHERE order_id=%s', (identifier, order_id))
            drain(etl_db)
            query("UPDATE voucher SET discount_value=2 WHERE voucher_id=%s", (identifier,))
            assert drain(etl_db)["status"] == "success"
            doc = etl_db.order_snapshots.find_one({"order_id": order_id})
            assert doc["voucher_current"]["discount_value_current"] == "2.00" and doc["final_amount_vnd"] == 1
    finally:
        query("DELETE FROM voucher WHERE voucher_id=%s", (identifier,))


def test_soft_and_hard_delete_preserve_authoritative_attributes(etl_db):
    with product() as identifier:
        drain(etl_db)
        etl_db.product_details.update_one(
            {"product_id": identifier}, {"$set": {"attributes": {"custom": "keep"}, "tags": ["keep"]}}
        )
        query("UPDATE product SET is_deleted=true WHERE product_id=%s", (identifier,))
        assert drain(etl_db)["status"] == "success"
        query("DELETE FROM product WHERE product_id=%s", (identifier,))
        assert drain(etl_db)["status"] == "success"
        doc = etl_db.product_details.find_one({"product_id": identifier})
        assert doc["deleted"] and doc["attributes"] == {"custom": "keep"} and doc["tags"] == ["keep"]
        assert execute("full", etl_db)["status"] == "success"
        assert etl_db.product_details.find_one({"product_id": identifier})["attributes"] == {"custom": "keep"}


def test_composite_logs_retention_and_pii_allowlists(etl_db):
    identifier = uuid.uuid4().int % 10**12 + 10**12
    dates = query(
        "SELECT CURRENT_TIMESTAMP::timestamp,(CURRENT_TIMESTAMP+interval '1 "
        "day')::timestamp,(CURRENT_TIMESTAMP-interval '120 days')::timestamp",
        one=True,
    )
    try:
        for date in dates:
            query(
                "INSERT INTO system_log(log_id,action,details,ip_address,created_at) "
                "VALUES(%s,'ETL_TEST','private@example.com token=secret','10.0.0.1',%s)",
                (identifier, date),
            )
        assert drain(etl_db)["status"] == "success"
        documents = list(etl_db.system_logs.find({"log_id": identifier}))
        assert len(documents) == 2 and len({doc["_id"] for doc in documents}) == 2
        assert all(
            "secret" not in json.dumps(doc, default=str) and "10.0.0.1" not in json.dumps(doc, default=str)
            for doc in documents
        )
        query("DELETE FROM system_log WHERE log_id=%s AND created_at=%s", (identifier, dates[0]))
        assert drain(etl_db)["status"] == "success"
        assert etl_db.system_logs.count_documents({"log_id": identifier}) == 1
        assert query("SELECT count(*) FROM system_log WHERE log_id=%s", (identifier,), one=True)[0] == 2
    finally:
        query("DELETE FROM system_log WHERE log_id=%s", (identifier,))
    feedback = query(
        "INSERT INTO system_feedback(guest_email,subject,content) VALUES('private@example.com','My "
        "address','password=secret phone 0901234567') RETURNING feedback_id",
        one=True,
    )[0]
    try:
        drain(etl_db)
        doc = etl_db.contact_messages.find_one({"feedback_id": feedback})
        assert "secret" not in json.dumps(doc, default=str) and "private@example.com" not in json.dumps(
            doc, default=str
        )
        etl_db.contact_messages.update_one(
            {"feedback_id": feedback}, {"$set": {"attachments": [{"bucket": "attachments", "key": "proof/test.png"}]}}
        )
        query("UPDATE system_feedback SET status=1 WHERE feedback_id=%s", (feedback,))
        assert drain(etl_db)["status"] == "success"
        assert etl_db.contact_messages.find_one({"feedback_id": feedback})["attachments"][0]["key"] == "proof/test.png"
    finally:
        query("DELETE FROM system_feedback WHERE feedback_id=%s", (feedback,))


def test_fractional_money_is_quarantined_and_replayed_after_correction(etl_db, monkeypatch):
    monkeypatch.setattr(settings, "ETL_MAX_ATTEMPTS", 1)
    with order() as identifier:
        query(
            """UPDATE order_detail SET price_at_purchase=1.25,subtotal=1.25 WHERE order_id=%s;
            UPDATE "order" SET total_amount=1.25,final_amount=1.25 WHERE order_id=%s""",
            (identifier, identifier),
        )
        result = execute("incremental", etl_db)
        assert result["status"] == "partial" and etl_db.etl_errors.count_documents({"resolved": False}) > 0
        assert etl_db.order_snapshots.find_one({"order_id": identifier}) is None
        query(
            """UPDATE order_detail SET price_at_purchase=2,subtotal=2 WHERE order_id=%s;
            UPDATE "order" SET total_amount=2,final_amount=2 WHERE order_id=%s""",
            (identifier, identifier),
        )
        assert drain(etl_db)["status"] == "success"
        assert etl_db.order_snapshots.find_one({"order_id": identifier})["final_amount_vnd"] == 2


def test_backend_utc_and_legacy_vietnamese_timestamp_provenance(etl_db):
    with Source() as source:
        row = source.get("product", {"id": 1})
        doc = project(source, "product", {"id": 1}, uuid.uuid4())
        expected = utc(
            row["updated_at"] or row["created_at"],
            source.origins("product", row["_source_key"])["updated_at" if row["updated_at"] else "created_at"],
        )
        assert comparable(doc["updated_at"]) == comparable(expected)
    with SessionLocal() as session:
        obj = Product(seller_id=3, category_id=1, title="ORM UTC", price=1, quantity=1, status=1)
        session.add(obj)
        session.commit()
        identifier = obj.product_id
        created = obj.created_at
    try:
        assert (
            query(
                "SELECT source_zone FROM etl_time_origin WHERE source_table='product' AND source_key=%s AND "
                "field_name='created_at'",
                (Json({"product_id": identifier}),),
                one=True,
            )[0]
            == "UTC"
        )
        assert drain(etl_db)["status"] == "success"
        assert comparable(etl_db.product_details.find_one({"product_id": identifier})["updated_at"]) == comparable(
            created.replace(tzinfo=UTC)
        )
    finally:
        query("DELETE FROM product WHERE product_id=%s", (identifier,))


def test_reconcile_detects_field_corruption_full_repairs_without_losing_tags(etl_db):
    etl_db.product_details.update_one({"product_id": 1}, {"$set": {"description": "corrupt", "tags": ["keep"]}})
    result = execute("reconcile", etl_db)
    assert (
        result["status"] == "partial"
        and result["details"]["quality"]["collections"]["product_details"]["field_mismatches"] == 1
    )
    assert execute("full", etl_db)["status"] == "success"
    assert etl_db.product_details.find_one({"product_id": 1})["tags"] == ["keep"]


def test_single_worker_lock_prevents_overlapping_full_load(etl_db):
    with closing(connect()) as owner, owner.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_lock(%s)", (LOCK,))
        owner.commit()
        with pytest.raises(RuntimeError, match="etl_worker_busy"):
            execute("full", etl_db)


def test_daily_gross_sales_rebuild_is_idempotent_and_tracks_status(etl_db):
    assert query("SELECT sum(gross_sales_vnd) FROM report_daily_sales", one=True)[0] == 13100000
    with order() as identifier:
        query(
            """UPDATE "order" SET order_status=3,order_date='2030-01-01 00:30:00'
                 WHERE order_id=%s""",
            (identifier,),
        )
        assert drain(etl_db)["status"] == "success"
        assert (
            query(
                "SELECT gross_sales_vnd FROM report_daily_sales WHERE report_date='2030-01-01' AND seller_id=3 "
                "AND category_id=1",
                one=True,
            )[0]
            == 1
        )
        query('UPDATE "order" SET order_status=4 WHERE order_id=%s', (identifier,))
        assert drain(etl_db)["status"] == "success"
        assert query("SELECT sum(gross_sales_vnd) FROM report_daily_sales", one=True)[0] == 13100000
        assert execute("full", etl_db)["status"] == "success"
        assert query("SELECT sum(gross_sales_vnd) FROM report_daily_sales", one=True)[0] == 13100000


def test_local_upload_is_copied_to_minio_before_event_ack(etl_db, png_bytes, monkeypatch):
    from app.services.storage import LocalStorage, bucket_for, local_path, minio_client

    monkeypatch.setattr(settings, "STORAGE_BACKEND", "local")
    with product() as identifier:
        key = f"products/{identifier}/{uuid.uuid4().hex}.png"
        LocalStorage().put(key, png_bytes)
        image = query(
            "INSERT INTO product_image(product_id,image_url,content_type,size_bytes) "
            "VALUES(%s,%s,'image/png',%s) RETURNING image_id",
            (identifier, "/media/" + key, len(png_bytes)),
            one=True,
        )[0]
        try:
            assert drain(etl_db)["status"] == "success"
            assert minio_client().stat_object(bucket_for(key), key).size == len(png_bytes)
            assert etl_db.product_details.find_one({"product_id": identifier})["images"][0]["key"] == key
        finally:
            query("DELETE FROM product_image WHERE image_id=%s", (image,))
            MinioStorage().delete(key)
            local_path(key).unlink(missing_ok=True)


def test_failed_quality_run_retains_ack_and_actual_progress_counts(etl_db, monkeypatch):
    from etl import quality

    with product() as identifier:
        original = quality.check

        def unavailable(*args, **kwargs):
            raise AutoReconnect("simulated reconciliation outage")

        monkeypatch.setattr(quality, "check", unavailable)
        with pytest.raises(AutoReconnect):
            execute("incremental", etl_db)
        status, rows_in, rows_out, error_count = query(
            "SELECT status,rows_in,rows_out,errors FROM etl_runs ORDER BY started_at DESC LIMIT 1", one=True
        )
        assert status == "failed" and rows_in >= 1 and rows_out >= 1 and error_count >= 1
        assert etl_db.product_details.count_documents({"product_id": identifier}) == 1
        assert query("SELECT count(*) FROM etl_outbox WHERE status<>'done'", one=True)[0] == 0
        monkeypatch.setattr(quality, "check", original)
        assert execute("incremental", etl_db)["status"] == "success"


def test_nullable_money_is_quarantined_instead_of_assumed_zero(etl_db):
    with order() as identifier:
        query('UPDATE "order" SET shipping_fee=NULL WHERE order_id=%s', (identifier,))
        result = execute("incremental", etl_db)
        assert result["status"] == "partial"
        assert etl_db.order_snapshots.find_one({"order_id": identifier}) is None
        assert etl_db.etl_errors.find_one({"code": "invalid_money", "resolved": False})
        query('UPDATE "order" SET shipping_fee=0 WHERE order_id=%s', (identifier,))
        assert drain(etl_db)["status"] == "success"
