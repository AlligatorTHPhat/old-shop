import uuid

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.buckets import catalogue, commerce
from app.buckets.db import one, rows, transaction
from app.core.config import settings
from app.main import app
from tests.buckets.test_buckets_integration import login, uid

pytestmark = pytest.mark.skipif(not settings.BUCKET_MODE, reason="Requires isolated bucket stack")


@pytest.fixture
def pair():
    buyer = uid(4)
    with transaction() as core:
        sellers = rows(
            core,
            "SELECT DISTINCT ON(a.owner_site_id) s.seller_id FROM seller_bucket s "
            "JOIN bucket_assignment a USING(bucket_id) WHERE s.seller_id<>%s ORDER BY a.owner_site_id,s.seller_id",
            (buyer,),
        )
    products = [
        catalogue.create(
            row["seller_id"],
            dict(category_id=1, title="Cross-site recovery item", price=100000, quantity=5, status=1),
            str(uuid.uuid4()),
        )
        for row in sellers[:2]
    ]
    assert len({row["site_id"] for row in products}) == 2
    yield products
    for product in products:
        catalogue.update(product["product_id"], {"is_deleted": True})


def body(pair):
    return dict(
        contact_id=uid(4),
        payment_method_id=1,
        shipping_fee=0,
        order_items=[dict(product_id=product["product_id"], quantity=1) for product in pair],
    )


def test_lost_ack_after_remote_commit_is_recoverable(pair, monkeypatch):
    original, lost = commerce.stock, [False]

    def with_lost_ack(*args, **kwargs):
        result = original(*args, **kwargs)
        if args[4] == "hold" and not lost[0]:
            lost[0] = True
            raise HTTPException(503, "Injected lost ACK after committed remote transaction")
        return result

    monkeypatch.setattr(commerce, "stock", with_lost_ack)
    operation = str(uuid.uuid4())
    with pytest.raises(HTTPException):
        commerce.place(uid(4), body(pair), operation)
    assert catalogue.get(pair[0]["product_id"])["quantity"] == 4
    recovered = commerce.recover()
    assert any(row.get("operation_id") == operation and row.get("state") == "recovered" for row in recovered)
    result = commerce.place(uid(4), body(pair), operation)
    assert all(catalogue.get(product["product_id"])["quantity"] == 4 for product in pair)
    commerce.cancel(result["order_id"])
    assert all(catalogue.get(product["product_id"])["quantity"] == 5 for product in pair)


def test_second_site_rejection_compensates_first_site(pair):
    catalogue.update(pair[1]["product_id"], {"quantity": 0, "status": 3})
    with pytest.raises(HTTPException) as error:
        commerce.place(uid(4), body(pair), str(uuid.uuid4()))
    assert error.value.status_code == 409
    assert catalogue.get(pair[0]["product_id"])["quantity"] == 5


def test_seller_only_advances_own_fulfillment(pair):
    result = commerce.place(uid(4), body(pair), str(uuid.uuid4()))
    with TestClient(app) as client:
        for status in (1, 2, 3):
            for index, product in enumerate(pair):
                with transaction() as core:
                    logical = one(
                        core,
                        "SELECT logical_key FROM seed_entities WHERE entity='user' AND global_id=%s",
                        (product["seller_id"],),
                    )["logical_key"]
                response = client.put(
                    f"/api/v1/orders/{result['order_id']}",
                    json={"order_status": status},
                    headers=login(client, logical),
                )
                assert response.status_code == 200, response.text
                assert response.json()["order_status"] == (status if index == 1 else status - 1)
        assert (
            client.put(
                f"/api/v1/orders/{result['order_id']}", json={"order_status": 4}, headers=login(client, 4)
            ).status_code
            == 409
        )
