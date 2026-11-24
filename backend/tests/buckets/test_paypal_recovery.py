"""Use fake provider responses; never send a real payment or train a model."""

import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.buckets import catalogue
from app.core.config import settings
from app.main import app
from app.services import fraud_detection, paypal
from tests.buckets.test_buckets_integration import login, uid

pytestmark = pytest.mark.skipif(not settings.BUCKET_MODE, reason="Requires isolated bucket stack")


def test_payment_retry_ownership_and_amount_reconciliation(monkeypatch):
    monkeypatch.setattr(settings, "PAYPAL_CLIENT_ID", "test-provider-no-network")
    monkeypatch.setattr(settings, "PAYPAL_SECRET", "test-provider-no-network")
    monkeypatch.setattr(
        fraud_detection, "score_transaction", lambda *_: SimpleNamespace(is_fraud=False, is_suspicious=False)
    )
    product = catalogue.create(
        uid(3),
        dict(category_id=1, title="Payment recovery fixture", price=100000, quantity=5, status=1),
        str(uuid.uuid4()),
    )
    requests = []
    correct = [False]
    provider = "FAKE" + uuid.uuid4().hex[:20].upper()

    async def create(oid, amount, request_id):
        requests.append(request_id)
        if len(requests) == 1:
            raise HTTPException(503, "Injected missing provider ACK")
        return {"id": provider, "status": "CREATED"}

    async def capture(identifier, request_id):
        return {
            "id": identifier,
            "status": "COMPLETED",
            "purchase_units": [
                {
                    "payments": {
                        "captures": [
                            {
                                "id": "FAKECAPTURE123",
                                "status": "COMPLETED",
                                "amount": {
                                    "currency_code": "USD",
                                    "value": paypal.vnd_to_usd(100000) if correct[0] else "0.01",
                                },
                            }
                        ]
                    }
                }
            ],
        }

    monkeypatch.setattr(paypal, "create_order", create)
    monkeypatch.setattr(paypal, "capture_order", capture)
    body = dict(
        contact_id=uid(4),
        payment_method_id=4,
        shipping_fee=0,
        order_items=[dict(product_id=product["product_id"], quantity=1)],
    )
    with TestClient(app) as client:
        headers = {**login(client, 4), "Idempotency-Key": str(uuid.uuid4())}
        assert client.post("/api/v1/orders/create-paypal-order", json=body, headers=headers).status_code == 503
        response = client.post("/api/v1/orders/create-paypal-order", json=body, headers=headers)
        assert response.status_code == 200, response.text
        oid = response.json()["internal_order_id"]
        assert len(requests) == 2 and requests[0] == requests[1]
        assert catalogue.get(product["product_id"])["quantity"] == 4
        path = f"/api/v1/orders/{oid}/capture-paypal?paypal_order_id={provider}"
        assert client.post(path, headers=login(client, 5)).status_code == 404
        assert client.post(path, headers=headers).status_code == 409
        assert client.put(f"/api/v1/orders/{oid}", json={"order_status": 4}, headers=headers).status_code == 409
        correct[0] = True
        assert client.post(path, headers=headers).status_code == 200
        assert client.post(path, headers=headers).status_code == 200
        assert catalogue.get(product["product_id"])["quantity"] == 4
    catalogue.update(product["product_id"], {"is_deleted": True})
