"""Resumable, insert-only imports. Detect drift instead of replacing user edits."""

import hashlib
import shutil
import uuid
from datetime import datetime
from decimal import Decimal

from psycopg2 import sql
from psycopg2.extras import Json

from app.buckets.db import execute, one, rows, transaction
from app.core.config import settings
from app.core.security import hash_password
from app.services.allocation import Allocator, canonical, load_contract
from seeding.generate import DATABASE, generate


def normalized(value):
    if isinstance(value, datetime):
        return value.replace(tzinfo=None).isoformat()
    if isinstance(value, str):
        try:
            if "T" in value and value[:4].isdigit():
                return datetime.fromisoformat(value).replace(tzinfo=None).isoformat()
        except ValueError:
            pass
    if isinstance(value, Decimal):
        return format(value.normalize(), "f")
    return value


def put(connection, table: str, key: str, values: dict, check=True):
    existing = one(
        connection,
        sql.SQL("SELECT * FROM {} WHERE {}=%s").format(sql.Identifier(table), sql.Identifier(key)),
        (values[key],),
    )
    if existing:
        if check:
            for field, value in values.items():
                actual = existing[field]
                a, b = normalized(actual), normalized(value)
                if isinstance(actual, Decimal):
                    b = format(Decimal(str(value)).normalize(), "f")
                if a != b:
                    raise ValueError(f"Seed drift at {table}/{values[key]}/{field}; no data overwritten")
        return
    encoded = [Json(value) if isinstance(value, (dict, list)) else value for value in values.values()]
    execute(
        connection,
        sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
            sql.Identifier(table),
            sql.SQL(",").join(map(sql.Identifier, values)),
            sql.SQL(",").join(sql.Placeholder() for _ in values),
        ),
        encoded,
    )


def fingerprints() -> dict:
    from app.buckets.db import site_urls

    with transaction() as core:
        registered = [
            row["site_id"] for row in rows(core, "SELECT site_id FROM site_registry WHERE active ORDER BY site_id")
        ]
    targets = {}
    for name in [None, *registered]:
        if name is not None and name not in site_urls():
            raise ValueError("Registered site is missing a DSN")
        with transaction(name) as connection:
            identity = one(
                connection,
                "SELECT instance_id,kind,site_id,dataset_id,contract_digest,schema_digest FROM bucket_installation",
            )
            if identity["site_id"] != name or identity["kind"] != ("core" if name is None else "site"):
                raise ValueError("Target installation identity mismatch")
            if (
                identity["dataset_id"] != settings.BUCKET_DATASET
                or identity["contract_digest"] != load_contract().digest()
            ):
                raise ValueError("Target dataset/contract mismatch")
            identity["extensions"] = rows(connection, "SELECT * FROM bucket_extension ORDER BY name")
            targets[name or "core"] = {
                key: str(value) if isinstance(value, uuid.UUID) else value for key, value in identity.items()
            }
    with transaction() as core:
        mapping = rows(core, "SELECT * FROM bucket_assignment ORDER BY bucket_id")
    from urllib.parse import urlparse

    if settings.MONGO_URI:
        from app.services.mongo import get_database

        marker = get_database().bucket_installation.find_one({"_id": "bucket-v2"})
        if not marker or marker.get("core_instance") != str(targets["core"]["instance_id"]):
            raise ValueError("Mongo target is not bound to this core; run bucket_setup first")
    if settings.GRAPH_ENABLED:
        from app.services.neo4j import driver

        record = (
            driver()
            .execute_query(
                "CYPHER 5 MATCH(i:GraphInstallation {key:$key}) RETURN i.core_instance AS instance",
                key=settings.BUCKET_DATASET,
                database_=settings.NEO4J_DATABASE,
            )
            .records
        )
        if not record or record[0]["instance"] != str(targets["core"]["instance_id"]):
            raise ValueError("Graph target is not bound to this core; run scripts.graph init first")

    mongo = urlparse(settings.MONGO_URI)
    graph = urlparse(settings.NEO4J_URI)
    return {
        "targets": targets,
        "mapping": mapping,
        "mongo_target": {"hosts": mongo.netloc.rsplit("@", 1)[-1], "database": settings.MONGO_DB},
        "graph_target": {
            "host": graph.hostname,
            "port": graph.port,
            "database": settings.NEO4J_DATABASE,
            "namespace": settings.BUCKET_DATASET,
            "generation": settings.GRAPH_GENERATION,
        },
    }


def plan(profile: str, scale=1) -> dict:
    data = generate(profile, scale)
    dataset_id = settings.BUCKET_DATASET
    if dataset_id != data["config"]["dataset_id"]:
        raise ValueError("BUCKET_DATASET must match the selected profile")
    return dict(
        run_id=str(uuid.uuid4()),
        dataset_id=dataset_id,
        profile=profile,
        scale=scale,
        dataset_hash=data["digest"],
        contract_digest=load_contract().digest(),
        fingerprint=fingerprints(),
    )


def phase(run_id: str, name: str):
    with transaction() as core:
        execute(core, "UPDATE seed_runs SET phase=%s,state='running',updated_at=now() WHERE run_id=%s", (name, run_id))


def sync_sequences(connection):
    """Explicit imports must not leave core-only SERIAL allocators behind."""
    for table, column in (
        ("user_core", "user_id"),
        ("role", "role_id"),
        ("category", "category_id"),
        ("contact_info", "contact_id"),
        ("payment_method", "payment_method_id"),
        ("transaction", "transaction_id"),
        ("review", "review_id"),
        ("order", "order_id"),
        ("order_detail", "order_detail_id"),
    ):
        sequence = one(connection, "SELECT pg_get_serial_sequence(%s,%s) AS name", (table, column))["name"]
        if sequence:
            maximum = one(
                connection,
                sql.SQL("SELECT COALESCE(max({}),0) AS maximum FROM {}").format(
                    sql.Identifier(column), sql.Identifier(table)
                ),
            )["maximum"]
            current = one(
                connection, sql.SQL("SELECT last_value FROM {}").format(sql.Identifier(sequence.split(".")[-1]))
            )["last_value"]
            execute(connection, "SELECT setval(%s,%s,true)", (sequence, max(maximum, current, 1)))


def bind(data: dict, dataset_id: str) -> tuple[dict, dict]:
    mapping = {}
    keys = {
        "users": ("user", "user_id"),
        "products": ("product", "product_id"),
        "images": ("image", "image_id"),
        "orders": ("order", "order_id"),
        "order_details": ("order_detail", "order_detail_id"),
        "reviews": ("review", "review_id"),
    }
    with transaction() as core:
        for collection, (entity, field) in keys.items():
            for row in data[collection]:
                logical = str(row[field])
                digest = hashlib.sha256(canonical(row).encode()).hexdigest()
                saved = one(
                    core,
                    "SELECT * FROM seed_entities WHERE dataset_id=%s AND entity=%s AND logical_key=%s",
                    (dataset_id, entity, logical),
                )
                if saved:
                    if saved["content_hash"] != digest:
                        raise ValueError("Dataset changed; use a different version/namespace")
                    value = saved["global_id"]
                else:
                    value = Allocator(core).allocate_ids(entity)[0]
                    execute(
                        core,
                        "INSERT INTO seed_entities VALUES(%s,%s,%s,%s,%s)",
                        (dataset_id, entity, logical, value, digest),
                    )
                mapping[(entity, row[field])] = value
    # Translate all references before choosing owner sites.
    foreign = {
        "seller_id": "user",
        "buyer_id": "user",
        "product_id": "product",
        "order_id": "order",
        "image_id": "image",
        "user_id": "user",
        "review_id": "review",
        "order_detail_id": "order_detail",
    }
    for collection in keys:
        for row in data[collection]:
            for field, entity in foreign.items():
                if field in row:
                    row[field] = mapping[(entity, row[field])]
            if "contact_id" in row:
                row["contact_id"] = mapping[("user", row["contact_id"])]
    for row in data["metadata"]:
        row["image_id"] = mapping[("image", row["image_id"])]
        row["product_id"] = mapping[("product", row["product_id"])]
    return data, mapping


def apply(document: dict, project=True):
    if document["contract_digest"] != load_contract().digest() or document["fingerprint"] != fingerprints():
        raise ValueError("Target or mapping changed since plan; create a new plan")
    data = generate(document["profile"], document["scale"])
    if data["digest"] != document["dataset_hash"]:
        raise ValueError("Dataset definition changed since plan")
    run_id, dataset_id = document["run_id"], document["dataset_id"]
    # A process-wide core advisory session lock also serializes concurrent resume/apply.
    from app.buckets.db import pool

    lock = pool().getconn()
    try:
        execute(lock, "SELECT pg_advisory_lock(7363196020)")
        lock.commit()
        with transaction() as core:
            existing = one(core, "SELECT * FROM seed_runs WHERE dataset_id=%s", (dataset_id,))
            if existing and existing["dataset_hash"] != data["digest"]:
                raise ValueError("Dataset namespace already has different content")
            if existing:
                run_id = str(existing["run_id"])
                execute(core, "UPDATE seed_runs SET plan=%s WHERE run_id=%s", (Json(document), run_id))
            else:
                execute(
                    core,
                    "INSERT INTO seed_runs(run_id,dataset_id,dataset_hash,plan) VALUES(%s,%s,%s,%s)",
                    (run_id, dataset_id, data["digest"], Json(document)),
                )
        data, mapping = bind(data, dataset_id)
        phase(run_id, "identity")
        reference_time = data["config"]["reference_time"]
        password = hash_password("BucketDemo123!")
        with transaction() as core:
            for i, name in enumerate(("Admin", "Mod", "User"), 1):
                put(
                    core,
                    "role",
                    "role_id",
                    dict(role_id=i, role_name=name, description="Bucket demo", created_at=reference_time),
                )
            for user in data["users"]:
                uid = user["user_id"]
                put(
                    core,
                    "user_core",
                    "user_id",
                    dict(user_id=uid, username=user["username"], email=user["email"], created_at=reference_time),
                )
                put(core, "user_profile", "user_id", dict(user_id=uid, full_name=user["full_name"]))
                put(
                    core,
                    "user_secret",
                    "user_id",
                    dict(user_id=uid, password_hash=password, random_key=f"seed-{dataset_id}-{uid}"),
                    check=False,
                )
                put(core, "user_wallet", "user_id", dict(user_id=uid, balance="10000000"), check=False)
                execute(
                    core,
                    "INSERT INTO user_role(user_id,role_id) VALUES(%s,%s) ON CONFLICT DO NOTHING",
                    (uid, user["role_id"]),
                )
                put(
                    core,
                    "contact_info",
                    "contact_id",
                    dict(
                        contact_id=uid,
                        user_id=uid,
                        full_name=user["full_name"],
                        phone_number="0900000000",
                        address=f"Địa chỉ mẫu của user {uid}",
                        created_at=reference_time,
                    ),
                )
            for category in data["categories"]:
                put(core, "category", "category_id", {**category, "created_at": reference_time})
            for mid, name in enumerate(("COD", "MOMO", "VNPAY", "PAYPAL", "BANK"), 1):
                put(
                    core,
                    "payment_method",
                    "payment_method_id",
                    dict(payment_method_id=mid, method_name=name, is_online=mid != 1),
                )
        phase(run_id, "catalogue")
        products = {p["product_id"]: p for p in data["products"]}
        for product in data["products"]:
            pid, seller = product["product_id"], product["seller_id"]
            with transaction() as core:
                route = Allocator(core).resolve_seller(seller)
                put(core, "seller_bucket", "seller_id", dict(seller_id=seller, bucket_id=route.bucket_id))
                put(
                    core,
                    "catalogue_directory",
                    "product_id",
                    dict(
                        product_id=pid,
                        seller_id=seller,
                        bucket_id=route.bucket_id,
                        lifecycle="active",
                        operation_id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"{dataset_id}:product:{pid}")),
                    ),
                    check=False,
                )
            with transaction() as core, transaction(route.site_id, route) as site:
                from app.buckets.catalogue import provision_reference

                provision_reference(core, site, seller, product["category_id"])
                put(site, "seller_bucket", "seller_id", dict(seller_id=seller, bucket_id=route.bucket_id))
                put(
                    site,
                    "product",
                    "product_id",
                    {
                        **{key: value for key, value in product.items() if key != "initial_quantity"},
                        "bucket_id": route.bucket_id,
                    },
                )
                for image in (image for image in data["images"] if image["product_id"] == pid):
                    put(
                        site,
                        "product_image",
                        "image_id",
                        {key: value for key, value in image.items() if key not in {"asset", "sha256"}},
                    )
        phase(run_id, "commerce")
        with transaction() as core:
            for order in data["orders"]:
                order["shipping_address"] = f"Địa chỉ mẫu của user {order['buyer_id']}"
                put(core, "order", "order_id", order)
                put(
                    core,
                    "transaction",
                    "transaction_id",
                    dict(
                        transaction_id=order["order_id"],
                        order_id=order["order_id"],
                        user_id=order["buyer_id"],
                        payment_method_id=1,
                        amount=order["final_amount"],
                        transaction_status=3 if order["order_status"] == 4 else 1 if order["order_status"] == 3 else 0,
                        reference_number=f"seed-{dataset_id}-{order['order_id']}",
                        created_at=order["order_date"],
                    ),
                )
            for item in data["order_details"]:
                put(core, "order_detail", "order_detail_id", {**item, "product_snapshot": products[item["product_id"]]})
                reservation = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{dataset_id}:order-line:{item['order_detail_id']}"))
                saved = one(
                    core, "SELECT reservation_id FROM order_detail WHERE order_detail_id=%s", (item["order_detail_id"],)
                )
                if saved["reservation_id"] is not None and str(saved["reservation_id"]) != reservation:
                    raise ValueError("Seed reservation changed; refusing overwrite")
                execute(
                    core,
                    "UPDATE order_detail SET reservation_id=%s WHERE order_detail_id=%s",
                    (reservation, item["order_detail_id"]),
                )
            for review in data["reviews"]:
                put(core, "review", "review_id", {**review, "created_at": reference_time})
            sync_sequences(core)
            execute(
                core,
                "INSERT INTO order_fulfillment(order_id,seller_id,bucket_id,status) SELECT DISTINCT "
                "d.order_id,p.seller_id,p.bucket_id,o.order_status FROM order_detail d "
                'JOIN catalogue_directory p USING(product_id) JOIN "order" o USING(order_id) ON CONFLICT DO NOTHING',
            )
        states = {order["order_id"]: order for order in data["orders"]}
        for item in data["order_details"]:
            product = products[item["product_id"]]
            with transaction() as core:
                route = Allocator(core).resolve_seller(product["seller_id"])
            reservation = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{dataset_id}:order-line:{item['order_detail_id']}"))
            with transaction(route.site_id, route) as site:
                put(
                    site,
                    "stock_reservation",
                    "reservation_id",
                    dict(
                        reservation_id=reservation,
                        operation_id=reservation,
                        product_id=item["product_id"],
                        buyer_id=states[item["order_id"]]["buyer_id"],
                        quantity=item["quantity"],
                        price=item["price_at_purchase"],
                        state="released" if states[item["order_id"]]["order_status"] == 4 else "committed",
                        expires_at=data["config"]["reference_time"],
                    ),
                    check=False,
                )
        phase(run_id, "media")
        for image in data["images"]:
            source = DATABASE / "03_seeds/media/products" / image["asset"]
            target = settings.MEDIA_DIR / image["image_url"].removeprefix("/media/")
            if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() != image["sha256"]:
                raise ValueError("Media key has different content; refusing overwrite")
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists():
                shutil.copyfile(source, target)
        if project:
            phase(run_id, "projection")
            from app.buckets.projection import backfill, seed_metadata

            backfill(graph=False)
            seed_metadata(data["metadata"], dataset_id)
            backfill(graph=settings.GRAPH_ENABLED)
        phase(run_id, "verification")
        from scripts.verify_seed import verify
        from seeding.manifest import build

        manifest = build(data, dataset_id)
        verification = (
            verify(include_graph=project and settings.GRAPH_ENABLED, run_id=run_id) if project else {"ok": False}
        )
        if project and not verification["ok"]:
            raise ValueError(f"Seed verification failed: {verification['errors']}")
        if project and settings.GRAPH_ENABLED and not (existing and existing["state"] == "complete"):
            from app.services.neo4j import driver, search

            driver().execute_query("CYPHER 5 CALL db.index.fulltext.awaitEventuallyConsistentIndexRefresh()")
            for expected in manifest["expected_queries"]:
                if sorted(row["image_id"] for row in search(expected["q"], limit=1000)) != expected["image_ids"]:
                    raise ValueError("Seed expected image query failed")
        with transaction() as core:
            execute(
                core,
                "INSERT INTO seed_manifest(run_id,manifest,verification) VALUES(%s,%s,%s) "
                "ON CONFLICT(run_id) DO UPDATE SET manifest=excluded.manifest,"
                "verification=excluded.verification,verified_at=now()",
                (run_id, Json(manifest), Json(verification)),
            )
            execute(
                core,
                "UPDATE seed_runs SET state=%s,phase=%s,error_code=NULL WHERE run_id=%s",
                ("complete" if project else "loaded", "complete" if project else "projection", run_id),
            )
        return {
            "run_id": run_id,
            "dataset_hash": document["dataset_hash"],
            "verification": verification,
            "counts": {
                key: len(data[key]) for key in ("users", "products", "images", "orders", "order_details", "reviews")
            },
        }
    except BaseException as error:
        with transaction() as core:
            execute(
                core,
                "UPDATE seed_runs SET state='failed',error_code=%s WHERE run_id=%s",
                (type(error).__name__, run_id),
            )
        raise
    finally:
        lock.rollback()
        execute(lock, "SELECT pg_advisory_unlock(7363196020)")
        lock.commit()
        pool().putconn(lock)
