"""Catalogue repository: core owns routing; the selected site owns product/stock."""

import hashlib
import uuid

from fastapi import HTTPException
from psycopg2 import sql

from app.buckets.db import execute, one, product_route, rows, transaction
from app.services.allocation import Allocator, canonical

FIELDS = {
    "category_id",
    "title",
    "description",
    "price",
    "quantity",
    "video_url",
    "weight_grams",
    "dimensions",
    "condition_rating",
    "warranty_months",
    "transfer_method",
    "status",
    "reject_reason",
    "approved_by",
    "is_deleted",
}


def provision_reference(core, target, seller_id: int, category_id: int):
    user = one(core, "SELECT user_id,username,email,is_active,is_deleted FROM user_core WHERE user_id=%s", (seller_id,))
    category = one(core, "SELECT * FROM category WHERE category_id=%s AND NOT is_deleted AND is_active", (category_id,))
    if not user or not category:
        raise HTTPException(422, "Seller or category reference not found")
    execute(
        target,
        "INSERT INTO user_core(user_id,username,email,is_active,is_deleted) VALUES(%s,%s,%s,%s,%s) "
        "ON CONFLICT(user_id) DO UPDATE SET username=excluded.username,email=excluded.email,"
        "is_active=excluded.is_active,is_deleted=excluded.is_deleted",
        tuple(user.values()),
    )
    # Ancestors are synchronized before children; refs do not contain identity secrets.
    if category["parent_id"]:
        provision_reference(core, target, seller_id, category["parent_id"])
    execute(
        target,
        "INSERT INTO category(category_id,name,description,parent_id,is_active,is_deleted) "
        "VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT(category_id) DO UPDATE SET name=excluded.name,"
        "description=excluded.description,parent_id=excluded.parent_id,is_active=excluded.is_active,"
        "is_deleted=excluded.is_deleted",
        tuple(category[key] for key in ("category_id", "name", "description", "parent_id", "is_active", "is_deleted")),
    )


def create(seller_id: int, data: dict, operation_id: str) -> dict:
    operation = str(uuid.UUID(operation_id))
    digest = hashlib.sha256(canonical(data).encode()).hexdigest()
    with transaction() as core:
        allocator = Allocator(core)
        route = allocator.resolve_seller(seller_id)
        execute(core, "SELECT pg_advisory_xact_lock(%s)", (seller_id,))
        record = one(core, "SELECT * FROM catalogue_directory WHERE operation_id=%s FOR UPDATE", (operation,))
        if record:
            if record["seller_id"] != seller_id or record["request_hash"] != digest:
                raise HTTPException(409, "Idempotency key reused for another listing")
            product_id = record["product_id"]
        else:
            product_id = allocator.allocate_ids("product")[0]
            execute(
                core, "INSERT INTO seller_bucket VALUES(%s,%s) ON CONFLICT DO NOTHING", (seller_id, route.bucket_id)
            )
            execute(
                core,
                "INSERT INTO catalogue_directory(product_id,seller_id,bucket_id,operation_id,request_hash) "
                "VALUES(%s,%s,%s,%s,%s)",
                (product_id, seller_id, route.bucket_id, operation, digest),
            )
    with transaction() as core, transaction(route.site_id, route) as site:
        provision_reference(core, site, seller_id, data["category_id"])
        execute(site, "INSERT INTO seller_bucket VALUES(%s,%s) ON CONFLICT DO NOTHING", (seller_id, route.bucket_id))
        if not one(site, "SELECT product_id FROM product WHERE product_id=%s", (product_id,)):
            values = {key: value for key, value in data.items() if key in FIELDS}
            values.update(product_id=product_id, seller_id=seller_id, bucket_id=route.bucket_id)
            query = sql.SQL("INSERT INTO product ({}) VALUES ({})").format(
                sql.SQL(",").join(map(sql.Identifier, values)), sql.SQL(",").join(sql.Placeholder() for _ in values)
            )
            execute(site, query, tuple(values.values()))
    with transaction() as core:
        execute(core, "UPDATE catalogue_directory SET lifecycle='active' WHERE product_id=%s", (product_id,))
    return get(product_id, public=False)


def get(product_id: int, public: bool = True, include_deleted=False) -> dict:
    route = product_route(product_id)
    with transaction(route.site_id, route) as site:
        product = one(site, "SELECT p.* FROM product p WHERE product_id=%s", (product_id,))
        if not product or (product["is_deleted"] and not include_deleted):
            raise HTTPException(404, "Product not found")
        category_id = product["category_id"]
        product["product_images"] = rows(
            site, "SELECT * FROM product_image WHERE product_id=%s ORDER BY display_order,image_id", (product_id,)
        )
    with transaction() as core:
        category = one(core, "SELECT * FROM category WHERE category_id=%s", (category_id,))
        seller = one(
            core,
            "SELECT user_id,username,is_active,is_deleted FROM user_core WHERE user_id=%s",
            (product["seller_id"],),
        )
    visible = bool(
        category
        and category["is_active"]
        and not category["is_deleted"]
        and seller
        and seller["is_active"]
        and not seller["is_deleted"]
        and product["status"] == 1
        and not product["is_deleted"]
    )
    if public and not visible:
        raise HTTPException(404, "Product not found")
    product.update(
        trade_allowed=bool(
            category
            and category["is_active"]
            and not category["is_deleted"]
            and seller
            and seller["is_active"]
            and not seller["is_deleted"]
            and not product["is_deleted"]
        ),
        is_approved=product["status"] == 1,
        bucket_id=route.bucket_id,
        site_id=route.site_id,
        visible=visible,
        category_name=category["name"] if category else "",
        seller_name=seller["username"] if seller else "",
    )
    return product


def listing(
    *,
    skip=0,
    limit=100,
    seller_id=None,
    status=None,
    category_id=None,
    search=None,
    exclude_seller=None,
    product_ids=None,
    sort_by="created_at",
    public=True,
) -> list[dict]:
    with transaction() as core:
        allocator = Allocator(core)
        assignments = rows(core, "SELECT * FROM bucket_assignment ORDER BY bucket_id")
        selected = (
            [allocator.resolve_seller(seller_id)]
            if seller_id is not None
            else [allocator.resolve_bucket(row["bucket_id"]) for row in assignments]
        )
        users = {
            row["user_id"]: row for row in rows(core, "SELECT user_id,username,is_active,is_deleted FROM user_core")
        }
        categories = {row["category_id"]: row for row in rows(core, "SELECT * FROM category")}
    grouped = {}
    for route in selected:
        grouped.setdefault(route.site_id, []).append(route)
    found = []
    # Per-site top K, followed by one global merge. No OFFSET on individual sites.
    order = {
        "created_at": "p.created_at DESC,p.product_id ASC",
        "price": "p.price ASC,p.product_id ASC",
        "rating": "p.condition_rating DESC NULLS LAST,p.product_id ASC",
    }[sort_by]
    for site_id, routes in grouped.items():
        with transaction(site_id) as site:
            for route in routes:
                lease = one(
                    site, "SELECT ownership_epoch,state FROM bucket_lease WHERE bucket_id=%s", (route.bucket_id,)
                )
                if not lease or lease["state"] != "active" or lease["ownership_epoch"] != route.ownership_epoch:
                    raise HTTPException(503, "Catalogue mapping changed")
            conditions = ["p.bucket_id=ANY(%s)", "NOT p.is_deleted"]
            params = [[route.bucket_id for route in routes]]
            if public:
                active_categories = [
                    key for key, value in categories.items() if value["is_active"] and not value["is_deleted"]
                ]
                active_sellers = [key for key, value in users.items() if value["is_active"] and not value["is_deleted"]]
                conditions += ["p.status=1", "p.category_id=ANY(%s)", "p.seller_id=ANY(%s)"]
                params += [active_categories, active_sellers]
            for column, value in (("seller_id", seller_id), ("category_id", category_id), ("status", status)):
                if value is not None:
                    conditions.append(f"p.{column}=%s")
                    params.append(value)
            if exclude_seller is not None:
                conditions.append("p.seller_id<>%s")
                params.append(exclude_seller)
            if product_ids is not None:
                conditions.append("p.product_id=ANY(%s)")
                params.append(product_ids)
            if search:
                pattern = "%" + search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
                conditions.append("(p.title ILIKE %s OR p.description ILIKE %s)")
                params += [pattern, pattern]
            products = rows(
                site,
                "SELECT p.* FROM product p WHERE " + " AND ".join(conditions) + " ORDER BY " + order + " LIMIT %s",
                (*params, skip + limit),
            )
            ids = [product["product_id"] for product in products]
            images = rows(
                site, "SELECT * FROM product_image WHERE product_id=ANY(%s) ORDER BY display_order,image_id", (ids,)
            )
            by_product = {}
            for image in images:
                by_product.setdefault(image["product_id"], []).append(image)
            for product in products:
                product.update(
                    product_images=by_product.get(product["product_id"], []),
                    seller_name=users.get(product["seller_id"], {}).get("username", ""),
                    category_name=categories.get(product["category_id"], {}).get("name", ""),
                    site_id=site_id,
                )
                found.append(product)
    if sort_by == "price":
        found.sort(key=lambda p: (p["price"], p["product_id"]))
    elif sort_by == "rating":
        found.sort(key=lambda p: (-(p["condition_rating"] or 0), p["product_id"]))
    else:
        found.sort(key=lambda p: (-p["created_at"].timestamp(), p["product_id"]))
    return found[skip : skip + limit]


def update(product_id: int, data: dict):
    route = product_route(product_id)
    values = {key: value for key, value in data.items() if key in FIELDS}
    if not values:
        return get(product_id, public=False)
    with transaction() as core, transaction(route.site_id, route) as site:
        product = one(site, "SELECT seller_id,category_id FROM product WHERE product_id=%s", (product_id,))
        provision_reference(core, site, product["seller_id"], values.get("category_id", product["category_id"]))
        if values.get("approved_by"):
            provision_reference(core, site, values["approved_by"], values.get("category_id", product["category_id"]))
        query = sql.SQL(
            "UPDATE product SET {},updated_at=timezone('UTC',clock_timestamp()) WHERE product_id=%s"
        ).format(sql.SQL(",").join(sql.SQL("{}=%s").format(sql.Identifier(key)) for key in values))
        execute(site, query, (*values.values(), product_id))
    return get(product_id, public=False, include_deleted=bool(values.get("is_deleted")))


def add_images(product_id: int, urls: list[str]):
    route = product_route(product_id)
    with transaction() as core:
        image_ids = Allocator(core).allocate_ids("image", len(urls))
    with transaction(route.site_id, route) as site:
        execute(site, "SELECT product_id FROM product WHERE product_id=%s FOR UPDATE", (product_id,))
        if one(site, "SELECT image_id FROM product_image WHERE product_id=%s LIMIT 1", (product_id,)):
            return
        for index, (image_id, url) in enumerate(zip(image_ids, urls, strict=True)):
            execute(
                site,
                "INSERT INTO product_image(image_id,product_id,image_url,is_primary,display_order) "
                "VALUES(%s,%s,%s,%s,%s)",
                (image_id, product_id, url, index == 0, index),
            )


def delete_image(product_id: int, image_id: int):
    route = product_route(product_id)
    with transaction(route.site_id, route) as site:
        execute(site, "SELECT product_id FROM product WHERE product_id=%s FOR UPDATE", (product_id,))
        image = one(site, "SELECT * FROM product_image WHERE product_id=%s AND image_id=%s", (product_id, image_id))
        if not image:
            raise HTTPException(404, "Image not found")
        execute(site, "DELETE FROM product_image WHERE image_id=%s", (image_id,))
        execute(
            site,
            "UPDATE product_image SET is_primary=true WHERE image_id=(SELECT image_id FROM product_image "
            "WHERE product_id=%s ORDER BY display_order,image_id LIMIT 1) AND NOT EXISTS"
            "(SELECT 1 FROM product_image WHERE product_id=%s AND is_primary)",
            (product_id, product_id),
        )
