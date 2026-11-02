"""Moderator queue completeness, ordering and search on a disposable PostgreSQL."""

import uuid
from datetime import datetime

import pytest

from app.core.database import SessionLocal
from app.models import Category, Product, User

ENDPOINT = "/api/v1/products/moderation/page"


@pytest.fixture
def listings():
    identifiers = []

    def create(**values):
        data = dict(seller_id=3, category_id=1, title="Queue test", price=1000, quantity=1, status=0)
        data.update(values)
        with SessionLocal() as db:
            product = Product(**data)
            db.add(product)
            db.commit()
            identifiers.append(product.product_id)
            return product.product_id

    yield create
    with SessionLocal() as db:
        db.query(Product).filter(Product.product_id.in_(identifiers)).delete(synchronize_session=False)
        db.commit()


@pytest.mark.parametrize("status", [0, 1, 2])
def test_all_pages_cover_database_without_duplicates(client, mod_headers, status):
    with SessionLocal() as db:
        expected = {
            row.product_id
            for row in db.query(Product.product_id).filter(Product.status == status, Product.is_deleted.is_(False))
        }
    if status == 0:
        assert len(expected) > 100
    seen = []
    skip = 0
    while True:
        response = client.get(ENDPOINT, headers=mod_headers, params={"status": status, "skip": skip, "limit": 31})
        assert response.status_code == 200, response.text
        page = response.json()
        assert page["total"] == len(expected)
        assert page["skip"] == skip and page["limit"] == 31
        assert all(p["status"] == status and not p["is_deleted"] for p in page["items"])
        seen.extend(p["product_id"] for p in page["items"])
        if skip + 31 >= page["total"]:
            break
        skip += 31
    assert len(seen) == len(set(seen))
    assert set(seen) == expected


def test_new_submission_is_first_with_image_and_names(client, login, mod_headers, png_bytes):
    title = f"New listing {uuid.uuid4().hex}"
    created = client.post(
        "/api/v1/products",
        headers=login("user1@gmail.com"),
        data={"title": title, "category_id": "1", "price": "1000", "quantity": "1"},
        files={"files": ("photo.png", png_bytes, "image/png")},
    )
    assert created.status_code == 201, created.text
    identifier = created.json()["product_id"]
    first = client.get(ENDPOINT, headers=mod_headers, params={"status": 0, "limit": 5}).json()
    assert first["items"][0]["product_id"] == identifier
    product = first["items"][0]
    assert product["seller_name"] and product["category_name"]
    assert product["product_images"][0]["is_primary"] is True
    approved = client.post(f"/api/v1/products/{identifier}/status", headers=mod_headers, json={"new_status": 1})
    assert approved.status_code == 200
    assert client.get(ENDPOINT, headers=mod_headers, params={"status": 0, "search": title}).json()["total"] == 0
    assert client.get(ENDPOINT, headers=mod_headers, params={"status": 1, "search": title}).json()["total"] == 1
    rejected = client.post(
        f"/api/v1/products/{identifier}/status",
        headers=mod_headers,
        json={"new_status": 2, "reject_reason": "Ảnh sản phẩm chưa phù hợp"},
    )
    assert rejected.status_code == 200
    assert client.get(ENDPOINT, headers=mod_headers, params={"status": 1, "search": title}).json()["total"] == 0
    assert client.get(ENDPOINT, headers=mod_headers, params={"status": 2, "search": title}).json()["total"] == 1


def test_equal_timestamps_have_stable_id_order(client, mod_headers, listings):
    marker = uuid.uuid4().hex
    identifiers = [listings(title=marker, created_at=datetime(2099, 1, 1)) for _ in range(3)]
    first = client.get(ENDPOINT, headers=mod_headers, params={"status": 0, "search": marker, "limit": 2}).json()
    second = client.get(
        ENDPOINT, headers=mod_headers, params={"status": 0, "search": marker, "limit": 2, "skip": 2}
    ).json()
    assert first["total"] == second["total"] == 3
    assert [p["product_id"] for p in first["items"] + second["items"]] == sorted(identifiers, reverse=True)


def test_search_and_total_cover_queue_and_exclude_deleted(client, mod_headers, listings):
    marker = uuid.uuid4().hex
    wanted = [listings(title=f"{marker} one"), listings(title=f"{marker} two")]
    listings(title=marker, is_deleted=True)
    listings(title=marker, status=1)
    page = client.get(ENDPOINT, headers=mod_headers, params={"status": 0, "search": f"  {marker}  ", "limit": 1}).json()
    assert page["total"] == 2 and len(page["items"]) == 1
    second = client.get(
        ENDPOINT, headers=mod_headers, params={"status": 0, "search": marker, "limit": 1, "skip": 1}
    ).json()
    assert {p["product_id"] for p in page["items"] + second["items"]} == set(wanted)
    beyond = client.get(ENDPOINT, headers=mod_headers, params={"status": 0, "search": marker, "skip": 100}).json()
    assert beyond["total"] == 2 and beyond["items"] == []


def test_seller_and_category_search_work_without_user_list(client, mod_headers, listings):
    identifier = listings()
    with SessionLocal() as db:
        seller = db.get(User, 3).username
        category = db.get(Category, 1).name
    for term in (seller, category):
        response = client.get(ENDPOINT, headers=mod_headers, params={"status": 0, "search": term, "limit": 1000})
        assert response.status_code == 200
        assert identifier in {p["product_id"] for p in response.json()["items"]}


def test_search_treats_percent_and_underscore_literally(client, mod_headers, listings):
    marker = uuid.uuid4().hex
    identifier = listings(title=f"{marker}%_exact")
    listings(title=f"{marker}ABexact")
    page = client.get(ENDPOINT, headers=mod_headers, params={"status": 0, "search": f"{marker}%_"}).json()
    assert page["total"] == 1 and page["items"][0]["product_id"] == identifier


@pytest.mark.parametrize(
    "params",
    [
        {"status": -1},
        {"status": 3},
        {"status": 0, "skip": -1},
        {"status": 0, "limit": 0},
        {"status": 0, "limit": 1001},
        {"status": 0, "search": "x" * 201},
    ],
)
def test_parameters_are_validated(client, mod_headers, params):
    assert client.get(ENDPOINT, headers=mod_headers, params=params).status_code == 422


def test_role_checks_and_legacy_array_response(client, mod_headers, login):
    assert client.get(ENDPOINT, params={"status": 0}).status_code == 401
    assert client.get(ENDPOINT, headers=login("user1@gmail.com"), params={"status": 0}).status_code == 403
    legacy = client.get("/api/v1/products/moderation/list", headers=mod_headers, params={"status": 0})
    assert legacy.status_code == 200 and isinstance(legacy.json(), list)
