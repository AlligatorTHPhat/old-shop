import pytest
from fastapi.testclient import TestClient

from app.buckets import catalogue, projection
from app.core.config import settings
from app.main import app
from app.schemas.catalog import ImageMetadataInput
from app.services import image_metadata, neo4j
from app.services.mongo import get_database
from tests.buckets.test_buckets_integration import uid

pytestmark = pytest.mark.skipif(not settings.BUCKET_MODE, reason="Requires isolated bucket stack")


def test_newer_metadata_revision_is_not_acknowledged_by_old_worker(monkeypatch):
    import uuid

    product = catalogue.create(
        uid(3),
        dict(category_id=1, title="Metadata revision fixture", price=100000, quantity=1, status=1),
        str(uuid.uuid4()),
    )
    pid = product["product_id"]
    projection.mongo_product(product)
    neo4j.catalogue(product)
    image_metadata.replace(pid, [])
    original = neo4j.metadata
    changed = [False]

    def interleave(product, document):
        result = original(product, document)
        if product["product_id"] == pid and not changed[0]:
            changed[0] = True
            image_metadata.replace(pid, [])
        return result

    monkeypatch.setattr(neo4j, "metadata", interleave)
    try:
        projection.metadata_pending(10000)
        row = get_database().product_details.find_one({"product_id": pid})
        assert row["metadata_revision"] == 2 and row["graph_pending_revision"] == 2
        projection.metadata_pending(10000)
        assert get_database().product_details.find_one({"product_id": pid})["graph_pending_revision"] is None
    finally:
        catalogue.update(pid, {"is_deleted": True})


def test_generation_mismatch_rejects_search_without_losing_pending_work(monkeypatch):
    monkeypatch.setattr(settings, "GRAPH_GENERATION", settings.GRAPH_GENERATION + 100)
    with TestClient(app) as client:
        response = client.get("/api/v1/images/search", params={"q": "alphaonly"})
        assert response.status_code == 503


def test_removed_image_is_hidden_before_graph_reconciles():
    import uuid

    product = catalogue.create(
        uid(3),
        dict(category_id=1, title="Removed image fixture", price=100000, quantity=1, status=1),
        str(uuid.uuid4()),
    )
    pid = product["product_id"]
    catalogue.add_images(pid, ["/media/products/nonexistent-test-image.jpg"])
    product = catalogue.get(pid)
    image_id = product["product_images"][0]["image_id"]
    projection.mongo_product(product)
    image_metadata.replace(pid, [ImageMetadataInput(image_id=image_id, caption="uniqueremovalfixture")])
    neo4j.catalogue(product)
    projection.metadata_pending(10000)
    with TestClient(app) as client:
        assert client.get("/api/v1/images/search", params={"q": "uniqueremovalfixture"}).json()["items"]
        catalogue.delete_image(pid, image_id)
        assert client.get("/api/v1/images/search", params={"q": "uniqueremovalfixture"}).json()["items"] == []
    catalogue.update(pid, {"is_deleted": True})
