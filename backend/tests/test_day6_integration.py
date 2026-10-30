"""Hybrid API contracts and failure recovery; only dedicated test databases are writable."""

import json
import os
import uuid
from contextlib import closing
from decimal import Decimal

import pytest
from fastapi import HTTPException
from pymongo.errors import AutoReconnect

from app.core.config import settings
from app.services import product_metadata, storage
from app.services.mongo import get_database
from etl.extract import SOURCES
from etl.pipelines import media_cleanup
from etl.run import execute, status
from scripts.migrate import connect


@pytest.mark.parametrize(
    "raw",
    [
        '{"$where":"x"}',
        '{"a.b":1}',
        '{"ram":{"$gt":0}}',
        "[]",
        "{}",
        '{"ram":NaN}',
        '{"ram":null}',
        '{"ram":9223372036854775808}',
    ],
)
def test_attribute_filters_reject_operators_and_invalid_values(raw):
    with pytest.raises(HTTPException) as error:
        product_metadata.parse_filters(raw)
    assert error.value.status_code == 422


def sql(statement, values=()):
    with closing(connect()) as connection, connection, connection.cursor() as cursor:
        cursor.execute(statement, values)
        return cursor.fetchall() if cursor.description else None


@pytest.fixture
def data():
    if os.getenv("DAY6_INTEGRATION") != "1":
        pytest.skip("Requires isolated Day 6 PG/Mongo/MinIO")
    assert settings.DB_NAME.startswith("day5_test_") and settings.MONGO_DB.startswith("day5_test_")
    database = get_database()
    for _, _, name in SOURCES.values():
        database[name].delete_many({})
    database.etl_errors.delete_many({})
    sql("DELETE FROM etl_outbox; DELETE FROM etl_runs; DELETE FROM etl_state; DELETE FROM report_daily_sales")
    assert execute("full", database)["status"] == "success"
    return database


def drain(database):
    for _ in range(10):
        result = execute("incremental", database)
        if not result["details"]["backlog"]["pending"]:
            return result
    raise AssertionError(result)


def test_detail_merges_only_public_mongo_metadata(client, data):
    data.product_details.update_one(
        {"product_id": 1},
        {
            "$set": {
                "attributes": {"ram_gb": 8, "ports": ["usb", "hdmi"]},
                "tags": ["used"],
                "description": "stale copy",
            }
        },
    )
    response = client.get("/api/v1/products/1")
    assert response.status_code == 200
    body = response.json()
    source = sql("SELECT price,quantity,description FROM product WHERE product_id=1")[0]
    assert Decimal(body["price"]) == source[0] and body["quantity"] == source[1]
    assert body["description"] == source[2] and body["attributes"]["ram_gb"] == 8
    assert body["tags"] == ["used"] and body["metadata_status"] == "available"
    assert body["metadata_synced_at"] is not None
    assert "_id" not in body and "etl" not in body and "bucket" not in body


def test_detail_fallback_and_filtered_search_fail_closed(client, data, monkeypatch):
    def unavailable():
        raise AutoReconnect("private exception text")

    monkeypatch.setattr(product_metadata, "get_database", unavailable)
    body = client.get("/api/v1/products/1").json()
    assert body["metadata_status"] == "unavailable" and body["attributes"] == {} and body["price"]
    response = client.get("/api/v1/products", params={"attributes": '{"ram_gb":8}'})
    assert response.status_code == 503 and "private" not in response.text
    assert client.get("/api/v1/products").status_code == 200


def test_missing_metadata_does_not_hide_product(client, data):
    data.product_details.delete_one({"product_id": 1})
    body = client.get("/api/v1/products/1").json()
    assert body["product_id"] == 1 and body["metadata_status"] == "missing" and body["attributes"] == {}


def test_attribute_search_combines_pg_visibility_filters_sort_and_pagination(client, data, login):
    rows = client.get("/api/v1/products?sort_by=price&limit=1000").json()
    ids = [row["product_id"] for row in rows]
    data.product_details.update_many({"product_id": {"$in": ids}}, {"$set": {"attributes": {"day6_match": True}}})
    filters = {"attributes": '{"day6_match":true}', "sort_by": "price", "limit": 2, "skip": 1}
    found = client.get("/api/v1/products", params=filters).json()
    assert [row["product_id"] for row in found] == ids[1:3]
    category = rows[0]["category_id"]
    expected = [row["product_id"] for row in rows if row["category_id"] == category]
    found = client.get("/api/v1/products", params={**filters, "skip": 0, "limit": 1000, "category_id": category}).json()
    assert [row["product_id"] for row in found] == expected
    seller = login("user1@gmail.com")
    me = client.get("/api/v1/auth/me", headers=seller).json()["user_id"]
    expected = [row["product_id"] for row in rows if row["seller_id"] != me]
    found = client.get("/api/v1/products", headers=seller, params={**filters, "skip": 0, "limit": 2}).json()
    assert [row["product_id"] for row in found] == expected[:2]
    assert client.get("/api/v1/products", params={"attributes": '{"day6_match":false}'}).json() == []


def test_attribute_search_never_silently_truncates(client, data, monkeypatch):
    data.product_details.update_many({}, {"$set": {"attributes": {"day6_match": True}}})
    monkeypatch.setattr(product_metadata, "MAX_MATCHES", 1)
    response = client.get("/api/v1/products", params={"attributes": '{"day6_match":true}'})
    assert response.status_code == 422


def test_admin_report_preserves_net_revenue_and_reports_freshness(client, data, admin_headers):
    report = client.get("/api/v1/admin/stats?sales_year=2025", headers=admin_headers).json()
    expected = sql('SELECT coalesce(sum(final_amount),0) FROM "order" WHERE order_status=3 AND NOT is_deleted')[0][0]
    assert Decimal(report["total_revenue"]) == expected
    sales = report["sales_report"]
    assert sales["available"] and not sales["stale"] and sales["as_of"]
    assert sales["gross_sales_vnd"] == sum(row["gross_sales_vnd"] for row in sales["daily"])
    expected = sql(
        "SELECT coalesce(sum(gross_sales_vnd),0) FROM report_daily_sales WHERE extract(year FROM report_date)=2025"
    )[0][0]
    assert sales["gross_sales_vnd"] == expected
    sql("UPDATE etl_runs SET ended_at=clock_timestamp()-interval '6 minutes' WHERE status='success'")
    assert client.get("/api/v1/admin/stats", headers=admin_headers).json()["sales_report"]["stale"]
    assert client.get("/api/v1/admin/stats").status_code == 401


def test_empty_report_is_distinct_from_no_etl(client, data, admin_headers):
    sales = client.get("/api/v1/admin/stats?sales_year=2099", headers=admin_headers).json()["sales_report"]
    assert sales["available"] and sales["gross_sales_vnd"] == 0 and sales["daily"] == []
    sql("DELETE FROM etl_runs")
    sales = client.get("/api/v1/admin/stats", headers=admin_headers).json()["sales_report"]
    assert not sales["available"] and sales["stale"] and sales["as_of"] is None


def test_product_upload_unlink_retry_and_minio_delete(client, data, login, admin_headers, png_bytes, monkeypatch):
    seller = login("user1@gmail.com")
    created = client.post(
        "/api/v1/products",
        headers=seller,
        data={"title": "Day6 image", "category_id": 1, "price": 10, "quantity": 1},
        files=[("files", ("proof.png", png_bytes, "image/png"))],
    )
    assert created.status_code == 201, created.text
    product = created.json()
    image = product["product_images"][0]
    url = image["image_url"]
    try:
        assert url.startswith(f"/media/products/{product['product_id']}/")
        assert client.get(url).content == png_bytes
        drain(data)
        endpoint = f"/api/v1/products/{product['product_id']}/images/{image['image_id']}"
        assert client.delete(endpoint, headers=login("user2@gmail.com")).status_code == 403
        assert client.delete(endpoint, headers=seller).status_code == 204
        assert sql("SELECT status FROM media_deletions WHERE url_path=%s", (url,))[0][0] == "pending"
        with monkeypatch.context() as patch:

            def unavailable(*args):
                raise HTTPException(503, "storage down")

            patch.setattr(media_cleanup, "delete_media", unavailable)
            result = drain(data)
            assert result["status"] == "partial" and result["errors"] == 1
        assert sql("SELECT attempts FROM media_deletions WHERE url_path=%s", (url,))[0][0] == 1
        assert data.product_details.find_one({"product_id": product["product_id"]})["images"] == []
        assert client.get(url).status_code == 200
        sql("UPDATE media_deletions SET available_at=clock_timestamp() WHERE url_path=%s", (url,))
        drain(data)
        assert client.get(url).status_code == 404
        assert sql("SELECT status FROM media_deletions WHERE url_path=%s", (url,))[0][0] == "done"
    finally:
        sql("DELETE FROM product WHERE product_id=%s", (product["product_id"],))
        storage.delete_media(url)


def test_avatar_replacement_collects_old_upload_after_commit(client, data, login, png_bytes):
    headers = login("user1@gmail.com")
    user = client.get("/api/v1/auth/me", headers=headers).json()
    original = user["avatar_url"]
    urls = []
    try:
        for _ in range(2):
            response = client.post(
                "/api/v1/users/me/avatar", headers=headers, files={"file": ("avatar.png", png_bytes, "image/png")}
            )
            assert response.status_code == 200, response.text
            urls.append(response.json()["avatar_url"])
        assert urls[0] != urls[1] and client.get(urls[0]).status_code == 200
        drain(data)
        assert client.get(urls[0]).status_code == 404 and client.get(urls[1]).content == png_bytes
    finally:
        sql("UPDATE user_profile SET avatar_url=%s WHERE user_id=%s", (original, user["user_id"]))
        for url in urls:
            storage.delete_media(url)


def test_violation_commits_through_outbox_without_copying_reason_pii(client, data, mod_headers):
    # user5 is an active seed seller; restore activation through the same API.
    user_id = sql("SELECT user_id FROM user_core WHERE email='user5@gmail.com'")[0][0]
    reason = "private@example.com token=never-copy"
    response = client.post(f"/api/v1/moderator/users/{user_id}/ban", headers=mod_headers, json={"reason": reason})
    assert response.status_code == 200, response.text
    try:
        drain(data)
        row = data.violation_logs.find_one({"target_user_id": user_id}, sort=[("created_at", -1)])
        assert row and "never-copy" not in json.dumps(row, default=str)
        assert "private@example.com" not in json.dumps(row, default=str)
    finally:
        assert (
            client.post(
                f"/api/v1/moderator/users/{user_id}/unban", headers=mod_headers, json={"reason": "restore test user"}
            ).status_code
            == 200
        )


def test_failed_cleanup_transaction_does_not_enqueue(data):
    with closing(connect()) as connection, connection.cursor() as cursor:
        url = f"/media/products/9999/{uuid.uuid4().hex}.png"
        cursor.execute("INSERT INTO product_image(product_id,image_url) VALUES(1,%s) RETURNING image_id", (url,))
        image_id = cursor.fetchone()[0]
        cursor.execute("DELETE FROM product_image WHERE image_id=%s", (image_id,))
        connection.rollback()
    assert sql("SELECT count(*) FROM media_deletions WHERE url_path=%s", (url,))[0][0] == 0


def test_shared_object_is_retained_until_last_pg_reference_is_unlinked(data, png_bytes):
    url = f"/media/products/9999/{uuid.uuid4().hex}.png"
    storage.get_storage().put(url.removeprefix("/media/"), png_bytes)
    ids = []
    try:
        for product_id in (1, 2):
            ids.append(
                sql(
                    "INSERT INTO product_image(product_id,image_url,content_type,size_bytes) "
                    "VALUES(%s,%s,'image/png',%s) RETURNING image_id",
                    (product_id, url, len(png_bytes)),
                )[0][0]
            )
        drain(data)
        sql("DELETE FROM product_image WHERE image_id=%s", (ids[0],))
        drain(data)
        assert storage.image_metadata(url)["size_bytes"] == len(png_bytes)
        assert sql("SELECT status FROM media_deletions WHERE url_path=%s", (url,))[0][0] == "pending"
        sql("DELETE FROM product_image WHERE image_id=%s", (ids[1],))
        drain(data)
        assert sql("SELECT status FROM media_deletions WHERE url_path=%s", (url,))[0][0] == "done"
    finally:
        for identifier in ids:
            sql("DELETE FROM product_image WHERE image_id=%s", (identifier,))
        storage.delete_media(url)


def test_readiness_alias_and_core_survive_minio_failure(client, data, monkeypatch):
    monkeypatch.setattr("app.main.ping_minio", lambda: False)
    assert client.get("/ready").status_code == 503
    assert client.get("/health").status_code == 200
    assert client.get("/api/v1/products").status_code == 200
    assert client.get("/api/v1/products/1").status_code == 200


def test_status_reports_numeric_media_cleanup_counts(data):
    before = status()["media_cleanup"]
    url = f"/media/products/9999/{uuid.uuid4().hex}.png"
    sql("INSERT INTO media_deletions(url_path,last_error_code) VALUES(%s,'test_unavailable')", (url,))
    try:
        report = status()
        assert report["media_cleanup"] == {"pending": before["pending"] + 1, "failed": before["failed"] + 1}
        assert report["last_run"]["status"] == "success"
    finally:
        sql("DELETE FROM media_deletions WHERE url_path=%s", (url,))
