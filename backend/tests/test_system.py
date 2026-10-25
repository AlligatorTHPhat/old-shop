import asyncio
from decimal import Decimal

import pytest

from app.core.exceptions import BadRequestError
from app.services import contact_relay
from app.services.fraud_detection import score_transaction
from app.services.paypal import capture_order, vnd_to_usd


def test_health_and_readiness(client):
    assert client.get("/health").json()["status"] == "ok"
    assert client.get("/health/ready").json()["database"] == "up"


def test_metrics_endpoint(client):
    client.get("/health")
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "http_requests_total" in response.text


def test_request_id_is_echoed(client):
    response = client.get("/api/v1/categories", headers={"X-Request-ID": "abc123"})
    assert response.headers["X-Request-ID"] == "abc123"


def test_guest_feedback_requires_email(client):
    assert client.post("/api/v1/system/feedback", json={"subject": "Hi", "content": "Hello"}).status_code == 400
    response = client.post(
        "/api/v1/system/feedback", json={"subject": "Hi", "content": "Hello", "guest_email": "guest@example.com"}
    )
    assert response.status_code == 201


def test_contact_form_is_stored_and_relayed(client, monkeypatch):
    relayed = []
    monkeypatch.setattr("app.api.v1.system.forward_contact_message", relayed.append)

    payload = {"full_name": "Khách", "email": "guest@example.com", "phone": "0909", "message": "Còn hàng không?"}
    response = client.post("/api/v1/system/contact", json=payload)

    assert response.status_code == 201
    assert response.json()["guest_email"] == "guest@example.com"
    assert relayed and relayed[0]["feedbackId"] == response.json()["feedback_id"]


def test_contact_envelope_signature_is_verifiable():
    envelope = contact_relay.build_envelope({"a": "ă"}, secret="s3cret", timestamp=1700000000)
    assert envelope["payload"] == '{"a":"ă"}'
    assert envelope["signature"] == contact_relay.sign(envelope["payload"], 1700000000, "s3cret")
    assert envelope["signature"] != contact_relay.sign(envelope["payload"], 1700000001, "s3cret")


def test_fraud_hard_limit():
    assert score_transaction(Decimal("150000000"), Decimal("0")).is_fraud
    small = score_transaction(Decimal("200000"), Decimal("10000000"))
    assert not small.is_fraud
    assert 0 <= small.score <= 1


def test_vnd_to_usd_rounding():
    assert vnd_to_usd(Decimal("25400")) == "1.00"
    assert vnd_to_usd(Decimal("38100")) == "1.50"


@pytest.mark.parametrize("bad_id", ["../../v1/oauth2/token", "abc", "5O190127TN364715T/refund"])
def test_paypal_capture_rejects_malformed_order_id(bad_id):
    """The id is client-supplied and ends up in the PayPal URL path."""
    with pytest.raises(BadRequestError):
        asyncio.run(capture_order(bad_id))
