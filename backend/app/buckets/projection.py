"""Multi-source delivery with independent Mongo/graph ACKs and Mongo-owned revisions."""

from datetime import UTC, datetime

from app.buckets import catalogue
from app.buckets.db import execute, one, pool, rows, transaction
from app.core.config import settings
from app.schemas.documents import ProductDetails
from app.services import neo4j
from app.services.mongo import get_database
from etl.load import pg_fields


def mongo_product(product: dict):
    data = ProductDetails.model_validate(
        {
            "_id": f"product:{product['product_id']}",
            "product_id": product["product_id"],
            "category_id": product["category_id"],
            "description": product["description"],
            "video_url": product.get("video_url"),
            "weight_grams": product.get("weight_grams"),
            "dimensions_raw": product.get("dimensions"),
            "deleted": product["is_deleted"],
            "images": [
                dict(
                    bucket="product-images",
                    key=image["image_url"].removeprefix("/media/"),
                    image_id=image["image_id"],
                    display_order=image["display_order"],
                    is_primary=image["is_primary"],
                    content_type=image.get("content_type"),
                    size=image.get("size_bytes"),
                )
                for image in product["product_images"]
            ],
            "updated_at": (product.get("updated_at") or product["created_at"]).replace(tzinfo=UTC),
            "etl": {"synced_at": datetime.now(UTC)},
        }
    ).model_dump(by_alias=True)
    from etl.pipelines.documents import OWNED

    defaults = {key: data[key] for key in OWNED["product_details"]}
    defaults["_id"] = data["_id"]
    get_database().product_details.update_one(
        {"product_id": product["product_id"]},
        {"$set": pg_fields("product_details", data), "$setOnInsert": defaults},
        upsert=True,
    )


def seed_metadata(entries: list[dict], dataset_id: str):
    by_product = {}
    for entry in entries:
        by_product.setdefault(entry["product_id"], []).append(
            {key: value for key, value in entry.items() if key != "product_id"}
        )
    collection = get_database().product_details
    for pid, metadata in by_product.items():
        document = collection.find_one({"product_id": pid})
        if document is None:
            raise ValueError("Product projection missing before seed metadata")
        if document.get("metadata_revision", 0) > 0 and document.get("metadata_seed_owner") != dataset_id:
            continue
        if document.get("image_metadata") == metadata:
            continue
        collection.update_one(
            {"product_id": pid, "metadata_revision": document.get("metadata_revision", 0)},
            [
                {
                    "$set": {
                        "image_metadata": {"$literal": metadata},
                        "metadata_seed_owner": {"$literal": dataset_id},
                        "metadata_revision": {"$add": [{"$ifNull": ["$metadata_revision", 0]}, 1]},
                        "graph_pending_revision": {"$add": [{"$ifNull": ["$metadata_revision", 0]}, 1]},
                    }
                }
            ],
        )


def metadata_pending(limit=100):
    count = 0
    collection = get_database().product_details
    for document in collection.find({"graph_pending_revision": {"$ne": None}}).limit(limit):
        product = catalogue.get(document["product_id"], public=False, include_deleted=True)
        if neo4j.metadata(product, document):
            revision = document["metadata_revision"]
            collection.update_one(
                {"_id": document["_id"], "metadata_revision": revision, "graph_pending_revision": revision},
                {"$set": {"graph_pending_revision": None}},
            )
            count += 1
    return count


def backfill(graph=True):
    from scripts.init_mongo import initialize

    initialize()
    get_database().product_details.create_index("graph_pending_revision", name="graph_metadata_pending")
    if graph:
        neo4j.initialize()
    with transaction() as core:
        ids = [
            row["product_id"]
            for row in rows(
                core, "SELECT product_id FROM catalogue_directory WHERE lifecycle='active' ORDER BY product_id"
            )
        ]
        orders = rows(core, 'SELECT * FROM "order" ORDER BY order_id')
        reviews = rows(core, "SELECT * FROM review ORDER BY review_id")
    for pid in ids:
        product = catalogue.get(pid, public=False, include_deleted=True)
        mongo_product(product)
        if graph:
            neo4j.catalogue(product)
            document = get_database().product_details.find_one({"product_id": pid})
            if not neo4j.metadata(product, document):
                raise ValueError("Graph image membership differs during backfill")
    if graph:
        for order in orders:
            with transaction() as core:
                items = rows(core, "SELECT * FROM order_detail WHERE order_id=%s", (order["order_id"],))
            neo4j.order(order, items)
        for review in reviews:
            neo4j.review(review)
        metadata_pending(max(len(ids), 1))
    return {"products": len(ids), "orders": len(orders), "reviews": len(reviews), "graph": graph}


def process_event(source: str | None, entity: str, entity_id: int, target: str):
    if entity in ("category", "user"):
        if entity == "user":
            with transaction() as core:
                product_ids = [
                    row["product_id"]
                    for row in rows(core, "SELECT product_id FROM catalogue_directory WHERE seller_id=%s", (entity_id,))
                ]
        else:
            product_ids = [
                row["product_id"] for row in catalogue.listing(category_id=entity_id, public=False, limit=100000)
            ]
        for product_id in product_ids:
            process_event(None, "product", product_id, target)
        return
    if entity == "product":
        from fastapi import HTTPException

        try:
            product = catalogue.get(entity_id, public=False, include_deleted=True)
        except HTTPException as error:
            if error.status_code != 404:
                raise
            if target == "mongo":
                get_database().product_details.update_one({"product_id": entity_id}, {"$set": {"deleted": True}})
            else:
                neo4j.tombstone(entity_id)
            return
        if target == "mongo":
            mongo_product(product)
        else:
            neo4j.catalogue(product)
            document = get_database().product_details.find_one({"product_id": entity_id})
            if document:
                neo4j.metadata(product, document)
    elif target == "graph":
        with transaction() as core:
            if entity == "order":
                row = one(core, 'SELECT * FROM "order" WHERE order_id=%s', (entity_id,))
                items = rows(core, "SELECT * FROM order_detail WHERE order_id=%s", (entity_id,))
                if row:
                    neo4j.order(row, items)
            elif entity == "review":
                row = one(core, "SELECT * FROM review WHERE review_id=%s", (entity_id,))
                if row:
                    neo4j.review(row)


def incremental(batch_size=100):
    from app.buckets.db import site_urls

    lock = pool().getconn()
    count, failures = 0, 0
    try:
        if not one(lock, "SELECT pg_try_advisory_lock(7363196021) AS acquired")["acquired"]:
            return {"done": 0, "failed": 0, "locked": True}
        lock.commit()
        with transaction() as core:
            sources = [None] + [row["site_id"] for row in rows(core, "SELECT site_id FROM site_registry WHERE active")]
        for source in sources:
            if source is not None and source not in site_urls():
                raise ValueError("Registered site has no configured DSN")
            for target in ["mongo", "graph"] if settings.GRAPH_ENABLED else ["mongo"]:
                if target == "graph" and not neo4j.ready():
                    continue
                with transaction(source) as connection:
                    groups = rows(
                        connection,
                        "SELECT e.entity,e.entity_id,max(e.event_id) AS boundary FROM app_event e "
                        "JOIN app_delivery d USING(event_id) WHERE d.target=%s AND d.status='pending' "
                        "AND d.available_at<=now() GROUP BY e.entity,e.entity_id ORDER BY max(e.event_id) LIMIT %s",
                        (target, batch_size),
                    )
                for group in groups:
                    try:
                        process_event(source, group["entity"], group["entity_id"], target)
                        with transaction(source) as connection:
                            execute(
                                connection,
                                "UPDATE app_delivery d SET status='done',error_code=NULL FROM app_event e "
                                "WHERE e.event_id=d.event_id AND d.target=%s AND e.entity=%s AND e.entity_id=%s "
                                "AND e.event_id<=%s",
                                (target, group["entity"], group["entity_id"], group["boundary"]),
                            )
                        count += 1
                    except Exception as error:
                        with transaction(source) as connection:
                            execute(
                                connection,
                                "UPDATE app_delivery d SET attempts=attempts+1,"
                                "status=CASE WHEN attempts>=4 THEN 'dead' ELSE 'pending' END,"
                                "available_at=now()+interval '15 seconds',error_code=%s FROM app_event e "
                                "WHERE e.event_id=d.event_id AND d.target=%s AND e.entity=%s AND e.entity_id=%s "
                                "AND e.event_id<=%s",
                                (type(error).__name__, target, group["entity"], group["entity_id"], group["boundary"]),
                            )
                        failures += 1
        if settings.GRAPH_ENABLED and neo4j.ready():
            metadata_pending(batch_size)
        from app.buckets.commerce import expire_reservations, recover

        recover()
        expire_reservations()
        return {"done": count, "failed": failures}
    finally:
        lock.rollback()
        execute(lock, "SELECT pg_advisory_unlock(7363196021)")
        lock.commit()
        pool().putconn(lock)


def status():
    with transaction() as core:
        sources = [None] + [row["site_id"] for row in rows(core, "SELECT site_id FROM site_registry WHERE active")]
    result = {}
    for source in sources:
        with transaction(source) as connection:
            result[source or "core"] = rows(
                connection, "SELECT target,status,count(*) AS count FROM app_delivery GROUP BY target,status"
            )
    result["metadata_pending"] = get_database().product_details.count_documents(
        {"graph_pending_revision": {"$ne": None}}
    )
    return result


def rebuild(generation: int):
    if type(generation) is not int or generation < 1:
        raise ValueError("Invalid graph generation")
    lock = pool().getconn()
    try:
        execute(lock, "SELECT pg_advisory_lock(7363196021)")
        lock.commit()
        with transaction() as core:
            current = one(core, "SELECT * FROM graph_projection_state FOR UPDATE")
            if generation < current["generation"] or (
                generation == current["generation"] and current["state"] != "rebuilding"
            ):
                raise ValueError("Rebuild needs a new generation, or a pending generation to resume")
            execute(core, "UPDATE graph_projection_state SET generation=%s,state='rebuilding'", (generation,))
        settings.GRAPH_GENERATION = generation
        result = backfill(graph=True)
        with transaction() as core:
            execute(core, "UPDATE graph_projection_state SET state='active' WHERE generation=%s", (generation,))
        return {**result, "generation": generation, "previous_generation_retained": True}
    finally:
        lock.rollback()
        execute(lock, "SELECT pg_advisory_unlock(7363196021)")
        lock.commit()
        pool().putconn(lock)
