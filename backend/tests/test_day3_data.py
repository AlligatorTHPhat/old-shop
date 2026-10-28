"""Document/storage regressions; real Mongo/MinIO tests opt in with DAY3_INTEGRATION=1."""

import asyncio
import io
import os
import uuid
from datetime import UTC, datetime

import pytest
from fastapi import HTTPException, UploadFile
from pydantic import ValidationError
from pymongo.errors import DuplicateKeyError, WriteError
from starlette.datastructures import Headers

from app.core.config import settings
from app.core.exceptions import BadRequestError
from app.schemas.documents import ProductDetails, ReviewDocument
from app.services import storage
from app.services.mongo import get_database
from app.services.mongo_schema import validators


def product_document(identifier=1):
    return ProductDetails(
        _id=f"p_{identifier}",
        product_id=identifier,
        category_id=1,
        attributes={"ram_gb": 8},
        updated_at=datetime.now(UTC),
    )


def test_document_rejects_naive_time_and_unexpected_pii():
    payload = product_document().model_dump(by_alias=True)
    with pytest.raises(ValidationError):
        ProductDetails.model_validate({**payload, "updated_at": datetime(2026, 1, 1)})
    with pytest.raises(ValidationError):
        ProductDetails.model_validate({**payload, "password_hash": "never-copy"})


def test_review_report_rating_consistency():
    payload = {
        "_id": "r_1",
        "review_id": 1,
        "product_id": 1,
        "buyer_id": 2,
        "type": "report",
        "rating": 0,
        "created_at": datetime.now(UTC),
    }
    assert ReviewDocument.model_validate(payload).type == "report"
    with pytest.raises(ValidationError):
        ReviewDocument.model_validate({**payload, "rating": 5})


def test_bson_schema_uses_real_dates_and_composite_log_key():
    schemas = validators()
    assert len(schemas) == 6
    assert schemas["product_details"]["$jsonSchema"]["properties"]["updated_at"]["bsonType"] == "date"
    assert schemas["product_details"]["$jsonSchema"]["additionalProperties"] is False
    assert schemas["reviews"]["$jsonSchema"]["oneOf"]


@pytest.mark.parametrize(
    "path",
    [
        "../secret.png",
        "products/../secret.png",
        "products//a.png",
        "products/../../secret.png",
        "attachments/proof.png",
        "users/a.html",
    ],
)
def test_media_rejects_unsafe_or_private_paths(path):
    with pytest.raises(HTTPException) as error:
        storage.validate_path(path)
    assert error.value.status_code == 404


def test_local_storage_rejects_symlink_escape(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "MEDIA_DIR", tmp_path / "media")
    (settings.MEDIA_DIR / "products").mkdir(parents=True)
    (settings.MEDIA_DIR / "products/link").symlink_to(tmp_path)
    with pytest.raises(HTTPException):
        storage.LocalStorage().put("products/link/secret.png", b"image")


def test_local_upload_is_unique_bounded_and_compatible(tmp_path, monkeypatch, png_bytes):
    monkeypatch.setattr(settings, "MEDIA_DIR", tmp_path)
    monkeypatch.setattr(settings, "STORAGE_BACKEND", "local")

    def upload(data):
        return UploadFile(io.BytesIO(data), filename="avatar.png", headers=Headers({"content-type": "image/png"}))

    first = asyncio.run(storage.save_image(upload(png_bytes), "users", "user_3_4"))
    second = asyncio.run(storage.save_image(upload(png_bytes), "users", "user_3_4"))
    assert first != second
    assert first.startswith("/media/users/user_3_4_")
    monkeypatch.setattr(settings, "MAX_UPLOAD_BYTES", 4)
    with pytest.raises(BadRequestError):
        asyncio.run(storage.save_image(upload(png_bytes), "users", "user_3_4"))


def test_minio_stream_releases_connection_even_on_iteration_error(monkeypatch):
    class BrokenResponse:
        headers = {"Content-Length": "10"}
        closed = False
        released = False

        def stream(self, size):
            yield b"start"
            raise OSError("interrupted")

        def close(self):
            self.closed = True

        def release_conn(self):
            self.released = True

    result = BrokenResponse()

    class Client:
        def get_object(self, *args):
            return result

    monkeypatch.setattr(storage, "minio_client", Client)
    response = storage.MinioStorage().response("products/1/example.png")

    async def consume():
        async for _ in response.body_iterator:
            pass

    with pytest.raises(OSError):
        asyncio.run(consume())
    assert result.closed and result.released


def test_readiness_reports_optional_store_failure(client, monkeypatch):
    monkeypatch.setattr(settings, "MONGO_URI", "mongodb://unused")
    monkeypatch.setattr(settings, "STORAGE_BACKEND", "minio")
    monkeypatch.setattr("app.main.ping_database", lambda: True)
    monkeypatch.setattr("app.main.ping_mongo", lambda: False)
    monkeypatch.setattr("app.main.ping_minio", lambda: True)
    response = client.get("/health/ready")
    assert response.status_code == 503 and response.json()["mongo"] == "down"
    assert client.get("/health").status_code == 200


integration = pytest.mark.skipif(os.getenv("DAY3_INTEGRATION") != "1", reason="Requires initialized Mongo/MinIO")


@integration
def test_real_mongo_validator_unique_index_and_partial_updates():
    collection = get_database()["product_details"]
    identifier = uuid.uuid4().int % 10**12 + 10**12
    payload = product_document(identifier).model_dump(by_alias=True, exclude_none=True)
    try:
        collection.insert_one(payload)
        assert collection.find_one({"_id": payload["_id"]})["attributes"]["ram_gb"] == 8
        collection.update_one({"_id": payload["_id"]}, {"$set": {"description": "PG-owned projection"}})
        assert collection.find_one({"_id": payload["_id"]})["attributes"] == {"ram_gb": 8}
        with pytest.raises(WriteError) as error:
            collection.insert_one({**payload, "_id": "invalid_" + payload["_id"], "product_id": "wrong"})
        assert error.value.code == 121
        with pytest.raises(DuplicateKeyError):
            collection.insert_one({**payload, "_id": "duplicate_" + payload["_id"]})
    finally:
        collection.delete_many(
            {"_id": {"$in": [payload["_id"], "invalid_" + payload["_id"], "duplicate_" + payload["_id"]]}}
        )


@integration
def test_real_mongo_rejects_inconsistent_report():
    collection = get_database()["reviews"]
    identifier = uuid.uuid4().int % 10**12 + 10**12
    payload = {
        "_id": f"r_{identifier}",
        "review_id": identifier,
        "product_id": 1,
        "buyer_id": 2,
        "type": "report",
        "rating": 5,
        "created_at": datetime.now(UTC),
    }
    try:
        with pytest.raises(WriteError) as error:
            collection.insert_one(payload)
        assert error.value.code == 121
    finally:
        collection.delete_one({"_id": payload["_id"]})


@integration
def test_real_minio_roundtrip_and_private_attachment_route(client, png_bytes):
    path = f"products/999999/{uuid.uuid4().hex}.png"
    backend = storage.MinioStorage()
    try:
        backend.put(path, png_bytes)
        response = backend.response(path)

        async def consume():
            return b"".join([chunk async for chunk in response.body_iterator])

        assert asyncio.run(consume()) == png_bytes
        head = backend.response(path, head=True)
        assert int(head.headers["content-length"]) == len(png_bytes)
        assert client.get("/media/attachments/private.png").status_code == 404
    finally:
        backend.delete(path)
    with pytest.raises(HTTPException) as error:
        backend.response(path)
    assert error.value.status_code == 404


@integration
def test_real_minio_upload_route(client, png_bytes, monkeypatch):
    monkeypatch.setattr(settings, "STORAGE_BACKEND", "minio")
    upload = UploadFile(io.BytesIO(png_bytes), filename="demo.png", headers=Headers({"content-type": "image/png"}))
    url = asyncio.run(storage.save_image(upload, "products", "prod_999999_0"))
    try:
        assert url.startswith("/media/products/999999/")
        assert client.get(url).content == png_bytes
        assert client.head(url).status_code == 200
        assert int(client.head(url).headers["content-length"]) == len(png_bytes)
    finally:
        storage.delete_media(url)


@integration
@pytest.mark.parametrize("collection_name", list(validators()))
def test_real_all_collection_contracts(collection_name):

    from app.schemas.documents import DOCUMENT_MODELS

    identifier = uuid.uuid4().int % 10**12 + 10**12
    now = datetime.now(UTC)
    common = {"_id": f"day3_{uuid.uuid4().hex}", "created_at": now}
    payloads = {
        "product_details": {"product_id": identifier, "category_id": 1, "updated_at": now},
        "reviews": {"review_id": identifier, "product_id": 1, "buyer_id": 2, "type": "review", "rating": 4},
        "order_snapshots": {
            "order_id": identifier,
            "buyer": {"id": 2},
            "items": [{"product_id": 1, "quantity": 1, "price_at_purchase_vnd": 1, "subtotal_vnd": 1}],
            "total_amount_vnd": 1,
            "shipping_fee_vnd": 0,
            "discount_amount_vnd": 0,
            "final_amount_vnd": 1,
            "order_status": 0,
            "order_date": now,
            "etl": {"synced_at": now},
        },
        "system_logs": {"log_id": identifier, "action": "day3.test"},
        "violation_logs": {"log_id": identifier, "target_user_id": 2, "reason": "test", "action_taken": "warning"},
        "contact_messages": {"feedback_id": identifier, "subject": "test", "content": "test", "status": 0},
    }
    if collection_name in ("product_details", "order_snapshots"):
        common.pop("created_at")
    payload = DOCUMENT_MODELS[collection_name].model_validate({**common, **payloads[collection_name]})
    document = payload.model_dump(by_alias=True, exclude_none=True)
    collection = get_database()[collection_name]
    try:
        collection.insert_one(document)
        assert collection.find_one({"_id": document["_id"]}) is not None
        with pytest.raises(WriteError) as error:
            collection.update_one({"_id": document["_id"]}, {"$set": {"unexpected_email": "private@example.invalid"}})
        assert error.value.code == 121
    finally:
        collection.delete_one({"_id": document["_id"]})


@integration
def test_real_avatar_api_uses_minio(client, admin_headers, png_bytes, monkeypatch):
    monkeypatch.setattr(settings, "STORAGE_BACKEND", "minio")
    response = client.post(
        "/api/v1/users/me/avatar",
        headers=admin_headers,
        files={"file": ("avatar.png", png_bytes, "image/png")},
    )
    assert response.status_code == 200, response.text
    url = response.json()["avatar_url"]
    try:
        assert "/avatar-" in url
        assert client.get(url).content == png_bytes
        assert client.head(url).status_code == 200
    finally:
        storage.delete_media(url)
