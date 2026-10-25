import io

import pytest


@pytest.fixture(scope="module")
def seller(login):
    return login("user1@gmail.com")


def test_public_listing_only_shows_approved(client):
    products = client.get("/api/v1/products").json()
    assert products
    assert all(p["status"] == 1 and p["is_approved"] for p in products)


def test_seller_does_not_see_own_listings(client, seller):
    me = client.get("/api/v1/auth/me", headers=seller).json()
    products = client.get("/api/v1/products", headers=seller).json()
    assert all(p["seller_id"] != me["user_id"] for p in products)


def test_create_product_then_moderate(client, seller, mod_headers, png_bytes):
    """Người bán đăng tin (multipart) -> chờ duyệt -> moderator duyệt."""
    response = client.post(
        "/api/v1/products",
        headers=seller,
        data={"category_id": "1", "title": "Máy ảnh film cũ", "price": "1500000", "quantity": "1"},
        files=[("files", ("camera.png", io.BytesIO(png_bytes), "image/png"))],
    )
    assert response.status_code == 201, response.text
    product = response.json()
    assert product["status"] == 0
    assert product["product_images"][0]["image_url"].startswith(f"/media/products/prod_{product['product_id']}_1_")

    pending_ids = [p["product_id"] for p in client.get("/api/v1/products/pending/all", headers=mod_headers).json()]
    assert product["product_id"] in pending_ids

    approved = client.post(f"/api/v1/products/{product['product_id']}/approve", headers=mod_headers)
    assert approved.status_code == 200
    assert approved.json()["status"] == 1


def test_create_product_rejects_non_image(client, seller):
    response = client.post(
        "/api/v1/products",
        headers=seller,
        data={"category_id": "1", "title": "x", "price": "1000", "quantity": "1"},
        files=[("files", ("notes.txt", io.BytesIO(b"hello"), "text/plain"))],
    )
    assert response.status_code == 400


def test_reject_requires_reason(client, mod_headers):
    assert client.post("/api/v1/products/1/reject?reject_reason=Short", headers=mod_headers).status_code == 422


def test_view_count_increments(client):
    before = client.get("/api/v1/products/1").json()["view_count"]
    client.get("/api/v1/products/1")
    assert client.get("/api/v1/products/1").json()["view_count"] == before + 2
