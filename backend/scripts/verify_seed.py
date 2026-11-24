"""Read-only reconstruction/ownership/media/graph verifier for a bucket seed run."""

import argparse
import hashlib
import json

from app.buckets.db import one, rows, transaction
from app.core.config import settings
from app.services.allocation import load_contract
from app.services.mongo import get_database


def verify(include_graph=False, run_id=None):
    contract = load_contract()
    with transaction() as core:
        run = one(core, "SELECT * FROM seed_runs WHERE run_id=%s", (run_id,)) if run_id else None
        if run_id and not run:
            raise ValueError("Unknown seed run")
        mapping = {row["bucket_id"]: row for row in rows(core, "SELECT * FROM bucket_assignment")}
        sites = rows(core, "SELECT site_id FROM site_registry WHERE active")
        directory = rows(core, "SELECT * FROM catalogue_directory WHERE lifecycle='active'")
        invalid_order = one(
            core,
            'SELECT count(*) AS count FROM "order" o JOIN contact_info c USING(contact_id) '
            "WHERE c.user_id<>o.buyer_id OR o.final_amount<>o.total_amount-o.discount_amount+o.shipping_fee",
        )["count"]
        self_buys = one(
            core,
            'SELECT count(*) AS count FROM order_detail d JOIN "order" o USING(order_id) '
            "JOIN catalogue_directory p ON p.product_id=d.product_id WHERE p.seller_id=o.buyer_id",
        )["count"]
    seen, images, errors, counts = set(), set(), [], {}
    if invalid_order or self_buys:
        errors.append("invalid_order_business_contract")
    for site in sites:
        sid = site["site_id"]
        with transaction(sid) as connection:
            active = rows(
                connection, "SELECT p.* FROM product p JOIN bucket_lease l USING(bucket_id) WHERE l.state='active'"
            )
            counts[sid] = len(active)
            for product in active:
                pid = product["product_id"]
                if pid in seen or contract.bucket_for_seller(product["seller_id"]) != product["bucket_id"]:
                    errors.append(f"duplicate_or_wrong_owner:{pid}")
                seen.add(pid)
                assignment = mapping[product["bucket_id"]]
                if assignment["owner_site_id"] != sid or assignment["state"] != "active":
                    errors.append(f"mapping_drift:{pid}")
                for image in rows(connection, "SELECT * FROM product_image WHERE product_id=%s", (pid,)):
                    if image["image_id"] in images:
                        errors.append("duplicate_image")
                    images.add(image["image_id"])
                    if not (settings.MEDIA_DIR / image["image_url"].removeprefix("/media/")).is_file():
                        errors.append(f"missing_media:{image['image_id']}")
    if seen != {row["product_id"] for row in directory}:
        errors.append("directory_reconstruction_mismatch")
    mongo_ids = {doc["product_id"] for doc in get_database().product_details.find({}, {"product_id": 1})}
    if mongo_ids != seen:
        errors.append("mongo_reconstruction_mismatch")
    graph_counts = None
    if run:
        with transaction() as core:
            ledger = rows(core, "SELECT entity,global_id FROM seed_entities WHERE dataset_id=%s", (run["dataset_id"],))
            expected = {}
            for entry in ledger:
                expected.setdefault(entry["entity"], set()).add(entry["global_id"])
            actual = {"product": seen, "image": images}
            for entity, table, column in [
                ("user", "user_core", "user_id"),
                ("order", '"order"', "order_id"),
                ("order_detail", "order_detail", "order_detail_id"),
                ("review", "review", "review_id"),
            ]:
                actual[entity] = {row[column] for row in rows(core, f"SELECT {column} FROM {table}")}
        if any(not identifiers.issubset(actual[entity]) for entity, identifiers in expected.items()):
            errors.append("seed_entity_missing")
    if include_graph:
        from app.services.neo4j import driver, namespace

        record = (
            driver()
            .execute_query(
                "CYPHER 5 MATCH(p:Product) WHERE p.namespace=$namespace RETURN collect(p.product_id) AS ids",
                namespace=namespace(),
                database_=settings.NEO4J_DATABASE,
            )
            .records[0]
        )
        if set(record["ids"]) != seen:
            errors.append("graph_reconstruction_mismatch")
        graph_counts = len(record["ids"])
        graph_images = (
            driver()
            .execute_query(
                "CYPHER 5 MATCH(i:Image) WHERE i.namespace=$namespace AND i.deleted=false "
                "RETURN collect(i.image_id) AS ids",
                namespace=namespace(),
                database_=settings.NEO4J_DATABASE,
            )
            .records[0]["ids"]
        )
        if set(graph_images) != images:
            errors.append("graph_image_reconstruction_mismatch")
    return dict(
        ok=not errors,
        errors=errors,
        sites=counts,
        products=len(seen),
        images=len(images),
        graph_products=graph_counts,
        run_id=str(run["run_id"]) if run else None,
        id_checksum=hashlib.sha256(json.dumps(sorted(seen)).encode()).hexdigest(),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id")
    parser.add_argument("--include-graph", action="store_true")
    args = parser.parse_args()
    result = verify(args.include_graph, args.run_id)
    print(json.dumps(result))
    raise SystemExit(0 if result["ok"] else 1)
