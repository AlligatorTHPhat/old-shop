"""Read-only legacy inventory and explicit import to an EMPTY bucket installation.

Use BUCKET_LEGACY_URL (never credentials in argv). No source writes or auto-cutover.
Naive timestamps require --assume-naive-zone; available ETL provenance takes precedence.
"""

import argparse
import hashlib
import json
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import psycopg2

from app.buckets.catalogue import provision_reference
from app.buckets.db import execute, one, rows, transaction
from app.services.allocation import Allocator, canonical, load_contract
from seeding.load import fingerprints, put

TABLES = (
    "role",
    "user_core",
    "user_profile",
    "user_secret",
    "user_wallet",
    "user_role",
    "category",
    "payment_method",
    "voucher",
    "contact_info",
    "product",
    "product_image",
    "shopping_cart",
    "shopping_cart_item",
    "order",
    "order_detail",
    "transaction",
    "review",
)


def inventory(zone: str) -> dict:
    data = {}
    connection = psycopg2.connect(os.environ["BUCKET_LEGACY_URL"], connect_timeout=5)
    try:
        connection.set_session(readonly=True, isolation_level="REPEATABLE READ")
        for table in TABLES:
            from psycopg2 import sql

            data[table] = rows(connection, sql.SQL("SELECT * FROM {} ORDER BY 1").format(sql.Identifier(table)))
        origins = rows(connection, "SELECT source_table,source_key,field_name,source_zone FROM etl_time_origin")
    finally:
        connection.rollback()
        connection.close()
    if os.getenv("BUCKET_LEGACY_MONGO_URI"):
        from pymongo import MongoClient

        client = MongoClient(os.environ["BUCKET_LEGACY_MONGO_URI"], serverSelectionTimeoutMS=4000)
        try:
            data["mongo_metadata"] = list(
                client[os.environ["BUCKET_LEGACY_MONGO_DB"]]
                .product_details.find(
                    {"product_id": {"$in": [product["product_id"] for product in data["product"]]}},
                    {
                        "_id": 0,
                        "product_id": 1,
                        "attributes": 1,
                        "tags": 1,
                        "image_metadata": 1,
                        "metadata_revision": 1,
                    },
                )
                .sort("product_id", 1)
            )
        finally:
            client.close()
    source_hash = hashlib.sha256(canonical(data).encode()).hexdigest()
    by_contact = {row["contact_id"]: row for row in data["contact_info"]}
    by_product = {row["product_id"]: row for row in data["product"]}
    by_order = {row["order_id"]: row for row in data["order"]}
    violations = []
    for order in data["order"]:
        if by_contact[order["contact_id"]]["user_id"] != order["buyer_id"]:
            violations.append(f"contact_buyer_mismatch:{order['order_id']}")
        if order["final_amount"] != order["total_amount"] - order["discount_amount"] + order["shipping_fee"]:
            violations.append(f"order_total_mismatch:{order['order_id']}")
    for payment in data["transaction"]:
        if payment["transaction_status"] not in (0, 1, 2, 3):
            violations.append(f"unsupported_payment_state:{payment['transaction_id']}")
    for item in data["order_detail"]:
        if by_product[item["product_id"]]["seller_id"] == by_order[item["order_id"]]["buyer_id"]:
            violations.append(f"self_buy:{item['order_detail_id']}")
    timezone = ZoneInfo(zone)
    known = {
        (row["source_table"], canonical(row["source_key"]), row["field_name"]): row["source_zone"] for row in origins
    }
    primary = {"product": "product_id", "order": "order_id", "review": "review_id"}
    for table, values in data.items():
        for row in values:
            for field, value in list(row.items()):
                if isinstance(value, datetime) and value.tzinfo is None:
                    origin = known.get(
                        (table, canonical({primary.get(table, "id"): row.get(primary.get(table, "id"))}), field)
                    )
                    row[field] = (
                        value.replace(tzinfo=ZoneInfo(origin) if origin else timezone)
                        .astimezone(UTC)
                        .replace(tzinfo=None)
                    )
    return {"source_hash": source_hash, "data": data, "violations": violations, "zone": zone}


def import_snapshot(snapshot: dict):
    if snapshot["violations"]:
        raise ValueError("Legacy business invariants failed; review correction report before import")
    data = snapshot["data"]
    with transaction() as core:
        marker = one(core, "SELECT * FROM migration_import WHERE source_hash=%s", (snapshot["source_hash"],))
        if not marker and (
            one(core, "SELECT 1 FROM user_core LIMIT 1") or one(core, "SELECT 1 FROM catalogue_directory LIMIT 1")
        ):
            raise ValueError("Import requires an empty target dataset; existing user data will not be overwritten")
        execute(
            core, "INSERT INTO migration_import VALUES(%s,'running') ON CONFLICT DO NOTHING", (snapshot["source_hash"],)
        )
    core_tables = (
        "role",
        "user_core",
        "user_profile",
        "user_secret",
        "user_wallet",
        "user_role",
        "category",
        "payment_method",
        "voucher",
        "contact_info",
    )
    for table in core_tables:
        with transaction() as core:
            for row in data[table]:
                if table == "user_role":
                    execute(
                        core,
                        "INSERT INTO user_role(user_id,role_id) VALUES(%s,%s) ON CONFLICT DO NOTHING",
                        (row["user_id"], row["role_id"]),
                    )
                else:
                    columns = rows(
                        core,
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_schema='public' AND table_name=%s",
                        (table,),
                    )
                    allowed = {column["column_name"] for column in columns}
                    filtered = {k: v for k, v in row.items() if k in allowed}
                    key = next(iter(row))
                    put(core, table, key, filtered)
    for product in data["product"]:
        with transaction() as core:
            route = Allocator(core).resolve_seller(product["seller_id"])
            execute(
                core,
                "INSERT INTO seller_bucket VALUES(%s,%s) ON CONFLICT DO NOTHING",
                (product["seller_id"], route.bucket_id),
            )
            execute(
                core,
                "INSERT INTO catalogue_directory(product_id,seller_id,bucket_id,lifecycle,operation_id) "
                "VALUES(%s,%s,%s,'active',%s) ON CONFLICT DO NOTHING",
                (
                    product["product_id"],
                    product["seller_id"],
                    route.bucket_id,
                    str(uuid.uuid5(uuid.NAMESPACE_URL, f"{snapshot['source_hash']}:{product['product_id']}")),
                ),
            )
        with transaction() as core, transaction(route.site_id, route, maintenance=True) as site:
            provision_reference(core, site, product["seller_id"], product["category_id"])
            if product["approved_by"]:
                provision_reference(core, site, product["approved_by"], product["category_id"])
            execute(
                site,
                "INSERT INTO seller_bucket VALUES(%s,%s) ON CONFLICT DO NOTHING",
                (product["seller_id"], route.bucket_id),
            )
            values = {k: v for k, v in product.items() if k not in {"site_id", "bucket_id", "catalogue_revision"}}
            put(site, "product", "product_id", {**values, "bucket_id": route.bucket_id})
            for image in (image for image in data["product_image"] if image["product_id"] == product["product_id"]):
                put(site, "product_image", "image_id", image)
            execute(
                site,
                "UPDATE product SET updated_at=%s,catalogue_revision=1 WHERE product_id=%s",
                (product.get("updated_at"), product["product_id"]),
            )
    with transaction() as core:
        for table, key in (
            ("shopping_cart", "cart_id"),
            ("order", "order_id"),
            ("order_detail", "order_detail_id"),
            ("transaction", "transaction_id"),
            ("review", "review_id"),
        ):
            for row in data[table]:
                values = dict(row)
                if table == "order_detail":
                    values["product_snapshot"] = __import__("json").loads(
                        canonical(next(p for p in data["product"] if p["product_id"] == row["product_id"]))
                    )
                put(core, table, key, values)
        execute(
            core,
            "INSERT INTO order_fulfillment(order_id,seller_id,bucket_id,status) SELECT DISTINCT "
            "d.order_id,p.seller_id,p.bucket_id,o.order_status FROM order_detail d "
            "JOIN catalogue_directory p USING(product_id) "
            'JOIN "order" o USING(order_id) ON CONFLICT DO NOTHING',
        )
        for entity, collection, field in (
            ("product", "product", "product_id"),
            ("image", "product_image", "image_id"),
            ("user", "user_core", "user_id"),
            ("order", "order", "order_id"),
            ("order_detail", "order_detail", "order_detail_id"),
            ("review", "review", "review_id"),
        ):
            maximum = max((row[field] for row in data[collection]), default=0)
            execute(
                core,
                "UPDATE global_id_allocator SET next_id=GREATEST(next_id,%s) WHERE entity=%s",
                (maximum + 1, entity),
            )
    # Existing carts have already reduced available stock in the legacy system.
    # Materialize held reservations without decrementing it a second time.
    from app.buckets.db import product_route

    carts = {row["cart_id"]: row["user_id"] for row in data["shopping_cart"]}
    for item in data["shopping_cart_item"]:
        route = product_route(item["product_id"])
        reservation = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{snapshot['source_hash']}:cart:{item['cart_item_id']}"))
        product = next(p for p in data["product"] if p["product_id"] == item["product_id"])
        with transaction(route.site_id, route) as site:
            execute(
                site,
                "INSERT INTO stock_reservation VALUES(%s,%s,%s,%s,%s,%s,'held',now()+interval '24 hours',now()) "
                "ON CONFLICT DO NOTHING",
                (
                    reservation,
                    reservation,
                    item["product_id"],
                    carts[item["cart_id"]],
                    item["quantity"],
                    product["price"],
                ),
            )
        with transaction() as core:
            put(core, "shopping_cart_item", "cart_item_id", {**item, "reservation_id": reservation})
    from seeding.load import sync_sequences

    with transaction() as core:
        sync_sequences(core)
        execute(
            core, "UPDATE migration_import SET state='sql_complete' WHERE source_hash=%s", (snapshot["source_hash"],)
        )
    return {"products": len(data["product"]), "images": len(data["product_image"]), "source_untouched": True}


def finish_import(snapshot):
    from app.buckets.projection import backfill
    from app.core.config import settings
    from app.services.mongo import get_database
    from app.services.storage import get_storage, validate_path

    backfill(graph=False)
    for metadata in snapshot["data"].get("mongo_metadata", []):
        current = get_database().product_details.find_one({"product_id": metadata["product_id"]})
        provenance = "migration:" + snapshot["source_hash"]
        if current.get("metadata_revision", 0) > 0 and current.get("metadata_seed_owner") != provenance:
            raise ValueError("Target metadata was edited; refusing migration overwrite")
        revision = max(metadata.get("metadata_revision", 0), 1)
        get_database().product_details.update_one(
            {"product_id": metadata["product_id"]},
            {
                "$set": {
                    "attributes": metadata.get("attributes", {}),
                    "tags": metadata.get("tags", []),
                    "image_metadata": metadata.get("image_metadata", []),
                    "metadata_revision": revision,
                    "graph_pending_revision": revision,
                    "metadata_seed_owner": provenance,
                }
            },
        )
    import shutil

    for image in snapshot["data"]["product_image"]:
        path = validate_path(image["image_url"].removeprefix("/media/"))
        if os.getenv("BUCKET_LEGACY_MEDIA_DIR"):
            source = Path(os.environ["BUCKET_LEGACY_MEDIA_DIR"]) / path
            if not source.is_file():
                raise ValueError("Source media missing; import remains pending")
            if settings.STORAGE_BACKEND == "local":
                target = settings.MEDIA_DIR / path
                if target.exists() and target.read_bytes() != source.read_bytes():
                    raise ValueError("Target media key differs; refusing overwrite")
                target.parent.mkdir(parents=True, exist_ok=True)
                if not target.exists():
                    shutil.copyfile(source, target)
            else:
                # Shared MinIO references should already be present and readable.
                if get_storage().response(path, head=True).status_code != 200:
                    raise ValueError("Target MinIO reference must be provisioned before cutover")
        elif get_storage().response(path, head=True).status_code != 200:
            raise ValueError("Configure BUCKET_LEGACY_MEDIA_DIR or an accessible shared object store")
    if settings.GRAPH_ENABLED:
        backfill(graph=True)
    with transaction() as core:
        execute(core, "UPDATE migration_import SET state='complete' WHERE source_hash=%s", (snapshot["source_hash"],))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("plan")
    p.add_argument("--assume-naive-zone", required=True)
    p.add_argument("--output", type=Path, required=True)
    p = sub.add_parser("apply")
    p.add_argument("--plan", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "plan":
        snapshot = inventory(args.assume_naive_zone)
        document = {k: v for k, v in snapshot.items() if k != "data"}
        document.update(
            target=fingerprints(),
            contract_digest=load_contract().digest(),
            counts={table: len(values) for table, values in snapshot["data"].items()},
        )
        with args.output.open("x") as stream:
            json.dump(document, stream, indent=2)
        print(json.dumps({"counts": document["counts"], "violations": document["violations"]}))
    else:
        document = json.loads(args.plan.read_text())
        snapshot = inventory(document["zone"])
        if snapshot["source_hash"] != document["source_hash"] or fingerprints() != document["target"]:
            raise ValueError("Source/target changed; create a new migration plan during maintenance")
        result = import_snapshot(snapshot)
        finish_import(snapshot)
        print(json.dumps(result))


if __name__ == "__main__":
    main()
