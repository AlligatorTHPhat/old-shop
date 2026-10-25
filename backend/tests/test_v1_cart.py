import pytest


@pytest.fixture(scope="module")
def buyer(login):
    return login("user1@gmail.com")


def test_get_cart(client, buyer):
    response = client.get("/api/v1/cart", headers=buyer)
    assert response.status_code == 200
    assert "cart_items" in response.json()


def test_cannot_add_own_product(client, buyer):
    """product 1 is listed by user1."""
    response = client.post("/api/v1/cart/items", json={"product_id": 1, "quantity": 1}, headers=buyer)
    assert response.status_code == 400
    assert "Cannot add your own product" in response.json()["detail"]


def test_item_lifecycle_reserves_and_releases_stock(client, buyer):
    """Thêm -> cập nhật -> xóa; tồn kho được giữ chỗ và trả lại đúng."""
    stock_before = client.get("/api/v1/products/6").json()["quantity"]

    added = client.post("/api/v1/cart/items", json={"product_id": 6, "quantity": 1}, headers=buyer)
    assert added.status_code == 201
    item_id = added.json()["cart_item_id"]
    assert client.get("/api/v1/products/6").json()["quantity"] == stock_before - 1

    updated = client.put(f"/api/v1/cart/items/{item_id}", json={"product_id": 6, "quantity": 2}, headers=buyer)
    assert updated.status_code == 200
    assert updated.json()["quantity"] == 2

    assert client.delete(f"/api/v1/cart/items/{item_id}", headers=buyer).status_code == 204
    assert client.get("/api/v1/products/6").json()["quantity"] == stock_before


def test_cannot_reserve_more_than_stock(client, buyer):
    response = client.post("/api/v1/cart/items", json={"product_id": 6, "quantity": 10_000}, headers=buyer)
    assert response.status_code == 400


def test_clear_cart(client, buyer):
    assert client.delete("/api/v1/cart", headers=buyer).status_code == 204
