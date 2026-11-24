"""Real PostgreSQL A/B, MongoDB and Neo4j tests; run ONLY in the isolated bucket stack."""

import uuid
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.buckets import catalogue, commerce, projection
from app.buckets.db import execute, one, product_route, transaction
from app.core.config import settings
from app.main import app
from app.schemas.catalog import ImageMetadataInput
from app.services import image_metadata
from app.services.allocation import bucket_for_seller
from app.services.mongo import get_database
from seeding.generate import generate

pytestmark = pytest.mark.skipif(not settings.BUCKET_MODE, reason="Requires the isolated bucket stack")


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as value:
        yield value


def uid(logical):
    with transaction() as core:
        return one(
            core,
            "SELECT global_id FROM seed_entities WHERE entity='user' AND logical_key=%s AND dataset_id=%s",
            (str(logical), settings.BUCKET_DATASET),
        )["global_id"]


def login(client, logical):
    result = client.post(
        "/api/v1/auth/login", data={"username": f"bucket{logical}@example.com", "password": "BucketDemo123!"}
    )
    assert result.status_code == 200, result.text
    return {"Authorization": f"Bearer {result.json()['access_token']}"}


def test_hash_contract_vectors():
    assert {identifier: bucket_for_seller(identifier) for identifier in (3, 8, 12, 101, 202)} == {
        3: 197,
        8: 94,
        12: 2,
        101: 37,
        202: 75,
    }
    for invalid in (True, 0, -1, "3"):
        with pytest.raises(ValueError):
            bucket_for_seller(invalid)


def test_global_api_and_identity(client):
    response = client.get("/api/v1/products", params={"limit": 1000})
    assert response.status_code == 200, response.text
    products = response.json()
    assert len({product["product_id"] for product in products}) == len(products)
    assert len(products) > 800
    assert client.get(f"/api/v1/products/{products[0]['product_id']}").status_code == 200
    assert client.get("/api/v1/products/seller/my-products", headers=login(client, 3)).status_code == 200


def test_graph_returns_matching_image_not_every_image(client):
    response = client.get("/api/v1/images/search", params={"q": "alphaonly"})
    assert response.status_code == 200, response.text
    assert len(response.json()["items"]) == 1
    row = response.json()["items"][0]
    assert "alphaonly" in row["description"]
    assert client.get(f"/api/v1/products/{row['product_id']}").status_code == 200
    assert client.get("/api/v1/images/search", params={"q": "alphaonly", "cursor": "tampered"}).status_code == 422


def test_seed_is_deterministic_and_business_valid():
    first, second = generate("demo-v2"), generate("demo-v2")
    assert first == second
    products = {row["product_id"]: row for row in first["products"]}
    orders = {row["order_id"]: row for row in first["orders"]}
    for item in first["order_details"]:
        assert products[item["product_id"]]["seller_id"] != orders[item["order_id"]]["buyer_id"]
    for product in products.values():
        sold = sum(
            line["quantity"]
            for line in first["order_details"]
            if line["product_id"] == product["product_id"] and orders[line["order_id"]]["order_status"] != 4
        )
        assert product["quantity"] + sold == product["initial_quantity"]


@pytest.fixture
def fresh_product():
    product = catalogue.create(
        uid(3),
        dict(
            category_id=1,
            title="Bucket integration item",
            description="Test fixture",
            price=Decimal("100000"),
            quantity=5,
            status=1,
        ),
        str(uuid.uuid4()),
    )
    yield product
    catalogue.update(product["product_id"], {"is_deleted": True})


def test_stock_retry_and_concurrency(fresh_product):
    pid = fresh_product["product_id"]
    reservation, operation = str(uuid.uuid4()), str(uuid.uuid4())
    commerce.stock(reservation, pid, uid(4), 2, "hold", operation)
    commerce.stock(reservation, pid, uid(4), 2, "hold", operation)
    assert catalogue.get(pid, public=False)["quantity"] == 3

    def reserve(_):
        try:
            commerce.stock(str(uuid.uuid4()), pid, uid(5), 2, "hold", str(uuid.uuid4()))
            return True
        except HTTPException:
            return False

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sum(executor.map(reserve, range(2))) == 1
    assert catalogue.get(pid, public=False)["quantity"] == 1


def test_cart_checkout_cancel_retry(client, fresh_product):
    headers = {**login(client, 4), "Idempotency-Key": str(uuid.uuid4())}
    body = {"product_id": fresh_product["product_id"], "quantity": 2}
    first = client.post("/api/v1/cart/items", json=body, headers=headers)
    assert first.status_code == 201, first.text
    assert client.post("/api/v1/cart/items", json=body, headers=headers).status_code == 201
    assert catalogue.get(body["product_id"], public=False)["quantity"] == 3
    order_headers = {**headers, "Idempotency-Key": str(uuid.uuid4())}
    request = {"contact_id": uid(4), "payment_method_id": 1, "shipping_fee": 30000, "order_items": [body]}
    response = client.post("/api/v1/orders", json=request, headers=order_headers)
    assert response.status_code == 201, response.text
    oid = response.json()["order_id"]
    assert client.post("/api/v1/orders", json=request, headers=order_headers).json()["order_id"] == oid
    assert catalogue.get(body["product_id"], public=False)["quantity"] == 3
    response = client.put(f"/api/v1/orders/{oid}", json={"order_status": 4}, headers=headers)
    assert response.status_code == 200, response.text
    assert catalogue.get(body["product_id"], public=False)["quantity"] == 5
    assert client.put(f"/api/v1/orders/{oid}", json={"order_status": 4}, headers=headers).status_code == 200
    assert catalogue.get(body["product_id"], public=False)["quantity"] == 5


def test_wrong_site_and_stale_epoch_are_fenced(fresh_product):
    route = product_route(fresh_product["product_id"])
    with pytest.raises(HTTPException), transaction(route.site_id) as site:
        execute(site, "SET LOCAL oldshop.ownership_epoch='99999'")
        execute(site, "UPDATE product SET quantity=quantity+1 WHERE product_id=%s", (fresh_product["product_id"],))


def test_metadata_user_edits_survive_sql_projection(client):
    with transaction() as core:
        pid = one(
            core,
            "SELECT global_id FROM seed_entities WHERE entity='product' AND logical_key='5' AND dataset_id=%s",
            (settings.BUCKET_DATASET,),
        )["global_id"]
    product = catalogue.get(pid, public=False)
    image_id = product["product_images"][0]["image_id"]
    collection = get_database().product_details
    original = collection.find_one({"product_id": pid})["image_metadata"]
    body = [{"image_id": image_id, "caption": "Ghi chú riêng Ω", "description": "Mô tả kiểm tra đồng bộ đồ thị"}]
    with transaction() as core:
        seller = one(
            core, "SELECT logical_key FROM seed_entities WHERE entity='user' AND global_id=%s", (product["seller_id"],)
        )["logical_key"]
    response = client.put(f"/api/v1/products/{pid}/images/metadata", json=body, headers=login(client, seller))
    assert response.status_code == 200, response.text
    projection.mongo_product(catalogue.get(pid, public=False))
    assert collection.find_one({"product_id": pid})["image_metadata"][0]["caption"] == "Ghi chú riêng Ω"
    assert projection.metadata_pending() >= 1
    assert client.get("/api/v1/images/search", params={"q": "ghi chu rieng"}).json()["items"][0]["image_id"] == image_id
    # SQL visibility is checked even before graph catches up.
    catalogue.update(pid, {"status": 0})
    assert client.get("/api/v1/images/search", params={"q": "ghi chu rieng"}).json()["items"] == []
    catalogue.update(pid, {"status": 1})
    image_metadata.replace(pid, [ImageMetadataInput.model_validate(item) for item in original])
    projection.metadata_pending()
