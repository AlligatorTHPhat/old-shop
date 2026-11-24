"""Annotation ownership, stale-image filtering, authorization and dependency failures."""

import os
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

os.environ.setdefault("SECRET_KEY", "image-metadata-unit-tests")
os.environ["DEBUG"] = "false"

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from pymongo.errors import ConnectionFailure

from app.api.v1 import products
from app.schemas.catalog import ImageMetadataInput, ProductDetailResponse
from app.schemas.documents import ProductDetails
from app.services import image_metadata
from app.services.mongo_schema import validators
from etl.load import pg_fields


@pytest.fixture
def mongo(monkeypatch):
    database = MagicMock()
    monkeypatch.setattr(image_metadata.settings, "MONGO_URI", "mongodb://test.invalid")
    monkeypatch.setattr(image_metadata, "get_database", lambda: database)
    return database.product_details


def detail():
    return ProductDetailResponse.model_validate(
        {
            "product_id": 10,
            "seller_id": 7,
            "category_id": 1,
            "title": "Camera",
            "price": 100,
            "quantity": 1,
            "status": 1,
            "view_count": 0,
            "is_deleted": False,
            "created_at": "2026-11-17T00:00:00Z",
            "product_images": [{"image_id": 21, "image_url": "/media/products/camera.png"}],
        }
    )


def test_only_current_sql_images_receive_annotations(mongo):
    mongo.find_one.return_value = {
        "image_metadata": [
            {"image_id": 21, "caption": "Mặt sau", "description": "Có vết trầy"},
            {"image_id": 99, "caption": "Deleted image"},
        ]
    }
    result = image_metadata.enrich(detail())
    assert result.image_metadata_status == "available"
    assert len(result.product_images) == 1
    assert result.product_images[0].caption == "Mặt sau"
    assert result.product_images[0].description == "Có vết trầy"


def test_metadata_outage_keeps_sql_product_and_images(mongo):
    mongo.find_one.side_effect = ConnectionFailure("offline")
    mongo.aggregate.side_effect = ConnectionFailure("offline")
    result = image_metadata.enrich(detail())
    assert result.image_metadata_status == "unavailable"
    assert result.product_images[0].image_id == 21
    assert result.product_images[0].caption is None
    with pytest.raises(HTTPException) as error:
        image_metadata.matching_image_ids("camera")
    # Separate operation must also propagate a dependency failure.
    assert error.value.status_code == 503


def test_missing_projection_is_not_upserted(mongo):
    mongo.update_one.return_value.matched_count = 0
    with pytest.raises(HTTPException) as error:
        image_metadata.replace(10, [ImageMetadataInput(image_id=21, caption="Photo")])
    assert error.value.status_code == 409
    assert "upsert" not in mongo.update_one.call_args.kwargs


def test_etl_cannot_overwrite_annotations():
    projection = ProductDetails.model_validate(
        {
            "_id": "product:10",
            "product_id": 10,
            "category_id": 1,
            "updated_at": datetime(2026, 11, 17, tzinfo=UTC),
        }
    ).model_dump(by_alias=True)
    assert projection["image_metadata"] == []
    assert "image_metadata" not in pg_fields("product_details", projection)
    assert "images" in pg_fields("product_details", projection)
    schema = validators()["product_details"]["$jsonSchema"]
    assert schema["properties"]["image_metadata"]["items"]["properties"]["caption"]["anyOf"][0]["maxLength"] == 255


@pytest.mark.parametrize(
    "payload",
    [
        {"image_id": True},
        {"image_id": -1},
        {"image_id": 21, "caption": "x" * 256},
        {"image_id": 21, "description": "x" * 4001},
        {"image_id": 21, "product_id": 10},
    ],
)
def test_invalid_annotations_rejected(payload):
    with pytest.raises(ValidationError):
        ImageMetadataInput.model_validate(payload)


def test_literal_search_and_match_cap(mongo):
    cursor = mongo.aggregate.return_value.__enter__.return_value
    cursor.__iter__.return_value = iter([{"image_id": 21}])
    assert image_metadata.matching_image_ids("a.*") == [21]
    pipeline = mongo.aggregate.call_args.args[0]
    assert pipeline[2]["$match"]["$or"][0]["image_metadata.caption"]["$regex"] == r"a\.\*"
    cursor.__iter__.return_value = iter([{"image_id": 21}] * (image_metadata.MAX_MATCHES + 1))
    with pytest.raises(HTTPException) as error:
        image_metadata.matching_image_ids("a")
    assert error.value.status_code == 422


@pytest.fixture
def client(monkeypatch):
    product = SimpleNamespace(seller_id=7, product_images=[SimpleNamespace(image_id=21)])
    query = MagicMock()
    query.filter.return_value.with_for_update.return_value.first.return_value = product
    db = MagicMock()
    db.query.return_value = query
    app = FastAPI()
    app.include_router(products.router)
    app.dependency_overrides[products.get_db] = lambda: db
    app.dependency_overrides[products.any_user] = lambda: SimpleNamespace(user_id=7, has_role=lambda *args: False)
    store = MagicMock()
    monkeypatch.setattr(image_metadata, "replace", store)
    return TestClient(app), app, store


def test_api_validates_image_membership_and_duplicates(client):
    http, _, store = client
    for body in [[{"image_id": 99}], [{"image_id": 21}, {"image_id": 21}]]:
        assert http.put("/products/10/images/metadata", json=body).status_code == 422
    store.assert_not_called()
    assert http.put("/products/10/images/metadata", json=[{"image_id": 21, "caption": " Back "}]).status_code == 200
    assert store.call_args.args[1][0].caption == "Back"


def test_api_rejects_other_seller(client):
    http, app, store = client
    app.dependency_overrides[products.any_user] = lambda: SimpleNamespace(user_id=8, has_role=lambda *args: False)
    assert http.put("/products/10/images/metadata", json=[{"image_id": 21}]).status_code == 403
    store.assert_not_called()


def test_api_requires_authentication(client):
    http, app, store = client
    del app.dependency_overrides[products.any_user]
    assert http.put("/products/10/images/metadata", json=[]).status_code == 401
    store.assert_not_called()
