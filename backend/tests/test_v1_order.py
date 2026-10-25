import pytest


@pytest.fixture(scope="module")
def buyer(login):
    return login("user6@gmail.com")


@pytest.fixture(scope="module")
def contact_id(client, buyer):
    contacts = client.get("/api/v1/users/me/contacts", headers=buyer).json()
    if not contacts:
        pytest.skip("Seed data has no address for user6")
    return contacts[0]["contact_id"]


def test_create_cod_order(client, buyer, contact_id):
    payload = {
        "contact_id": contact_id,
        "payment_method_id": 1,  # COD
        "order_items": [{"product_id": 2, "quantity": 1}],
        "shipping_fee": 30000,
        "notes": "Kiểm tra hàng trước khi nhận",
    }
    response = client.post("/api/v1/orders", json=payload, headers=buyer)

    assert response.status_code == 201
    order = response.json()
    assert order["order_status"] == 0
    assert float(order["final_amount"]) == float(order["total_amount"]) + 30000
    assert len(order["order_details"]) == 1


def test_order_requires_own_address(client, buyer):
    payload = {"contact_id": 1, "payment_method_id": 1, "order_items": [{"product_id": 2, "quantity": 1}]}
    assert client.post("/api/v1/orders", json=payload, headers=buyer).status_code == 400


def test_unknown_voucher_is_rejected(client, buyer, contact_id):
    payload = {
        "contact_id": contact_id,
        "payment_method_id": 1,
        "voucher_code": "DOES-NOT-EXIST",
        "order_items": [{"product_id": 2, "quantity": 1}],
    }
    assert client.post("/api/v1/orders", json=payload, headers=buyer).status_code == 404


def test_paypal_checkout_blocks_high_risk_amount(client, buyer, contact_id):
    """Đơn > 100 triệu bị chặn bởi luật cứng của fraud detection trước khi gọi PayPal."""
    payload = {
        "contact_id": contact_id,
        "payment_method_id": 4,  # PayPal
        "order_items": [{"product_id": 2, "quantity": 20}],
        "shipping_fee": 50000,
    }
    response = client.post("/api/v1/orders/create-paypal-order", json=payload, headers=buyer)

    assert response.status_code == 403
    assert "Giao dịch bị từ chối" in response.json()["detail"]


def test_cancel_order_restocks(client, buyer):
    orders = client.get("/api/v1/orders?status_filter=0", headers=buyer).json()
    if not orders:
        pytest.skip("No pending order to cancel")
    order_id = orders[0]["order_id"]
    detail = client.get(f"/api/v1/orders/{order_id}", headers=buyer).json()["order_details"][0]
    stock_before = client.get(f"/api/v1/products/{detail['product_id']}").json()["quantity"]

    response = client.put(f"/api/v1/orders/{order_id}", json={"order_status": 4}, headers=buyer)

    assert response.status_code == 200
    stock_after = client.get(f"/api/v1/products/{detail['product_id']}").json()["quantity"]
    assert stock_after == stock_before + detail["quantity"]
    assert client.put(f"/api/v1/orders/{order_id}", json={"order_status": 4}, headers=buyer).status_code == 400


def test_buyer_cannot_confirm_own_order(client, buyer):
    orders = client.get("/api/v1/orders", headers=buyer).json()
    if not orders:
        pytest.skip("No order")
    response = client.put(f"/api/v1/orders/{orders[0]['order_id']}", json={"order_status": 1}, headers=buyer)
    assert response.status_code == 403
