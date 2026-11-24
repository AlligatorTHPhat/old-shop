import uuid

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.buckets import catalogue, commerce
from app.buckets.db import execute, one, product_route, transaction
from app.catalogue_gateway import create_app
from app.core.config import settings
from scripts.move_bucket import apply, plan

pytestmark = pytest.mark.skipif(not settings.BUCKET_MODE, reason="Requires isolated bucket stack")


def test_move_to_c_and_reverse_preserves_new_writes():
    with transaction() as core:
        if not one(core, "SELECT site_id FROM site_registry WHERE site_id='C'"):
            pytest.skip("Expansion site C not initialized")
        seller = one(
            core,
            "SELECT global_id FROM seed_entities WHERE dataset_id=%s AND entity='user' AND logical_key='3'",
            (settings.BUCKET_DATASET,),
        )["global_id"]
        buyer = one(
            core,
            "SELECT global_id FROM seed_entities WHERE dataset_id=%s AND entity='user' AND logical_key='4'",
            (settings.BUCKET_DATASET,),
        )["global_id"]
    product = catalogue.create(
        seller, dict(category_id=1, title="Move bucket test", price=100000, quantity=7, status=1), str(uuid.uuid4())
    )
    before = product_route(product["product_id"])
    reservation, operation = str(uuid.uuid4()), str(uuid.uuid4())
    commerce.stock(reservation, product["product_id"], buyer, 2, "hold", operation)
    proposal = plan(before.bucket_id, "C")
    result = apply(proposal)
    assert result["state"] == "complete"
    assert product_route(product["product_id"]).site_id == "C"
    assert catalogue.get(product["product_id"])["quantity"] == 5
    with TestClient(create_app()) as gateway:
        response = gateway.get(f"/products/{product['product_id']}")
        assert response.status_code == 200, response.text
        assert response.json()["site_id"] == "C"
        assert gateway.post("/products", json={}).status_code == 405
    # Replaying an old operation at the new site must not reserve twice.
    commerce.stock(reservation, product["product_id"], buyer, 2, "hold", operation)
    assert catalogue.get(product["product_id"])["quantity"] == 5
    with pytest.raises(HTTPException), transaction(before.site_id) as site:
        execute(site, "SELECT set_config('oldshop.ownership_epoch',%s,true)", (str(before.ownership_epoch),))
        execute(site, "UPDATE product SET quantity=100 WHERE product_id=%s", (product["product_id"],))
    commerce.stock(reservation, product["product_id"], buyer, 0, "release", str(uuid.uuid4()))
    assert catalogue.get(product["product_id"])["quantity"] == 7
    reverse = plan(before.bucket_id, before.site_id)
    assert apply(reverse)["state"] == "complete"
    assert product_route(product["product_id"]).site_id == before.site_id
    assert catalogue.get(product["product_id"])["quantity"] == 7
    catalogue.update(product["product_id"], {"is_deleted": True})
