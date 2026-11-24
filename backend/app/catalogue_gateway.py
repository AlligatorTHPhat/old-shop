"""Optional read-only catalogue gateway over the site's global views.

Run explicitly with ``uvicorn app.catalogue_gateway:app``. It is not installed
over the existing checkout API. Credentials are read-only global_reader accounts.
"""

import os
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Annotated, Any

import psycopg2
from fastapi import FastAPI, HTTPException, Query
from fastapi import Path as APIPath
from psycopg2.extras import RealDictCursor

from app.services.fragment_router import load_contract, relations


def create_app(
    database_url: str | None = None, *, site_b_url: str | None = None, routed: bool | None = None
) -> FastAPI:
    from app.core.config import settings

    if settings.BUCKET_MODE:
        from app.buckets.gateway import create_app as bucket_gateway

        return bucket_gateway()
    url = database_url if database_url is not None else os.getenv("DISTRIBUTED_CATALOG_URL", "")
    b_url = site_b_url if site_b_url is not None else os.getenv("DISTRIBUTED_CATALOG_B_URL", "")
    use_router = routed if routed is not None else os.getenv("DISTRIBUTED_CATALOG_ROUTING", "1") == "1"
    contract = load_contract()
    app = FastAPI(title="OldShop distributed catalogue", version="1.1.0")

    # B can be read directly even when A is unavailable. Without a B URL, use
    # scoped FDW views at A; that compatibility mode still depends on hub A.
    @contextmanager
    def database(site=None) -> Iterator[Any]:
        selected_url = b_url if use_router and site == "B" and b_url else url
        if not selected_url:
            raise HTTPException(503, "Distributed catalogue is not configured")
        connection = None
        try:
            connection = psycopg2.connect(selected_url, connect_timeout=3, options="-c statement_timeout=5000")
            connection.set_session(isolation_level="REPEATABLE READ", readonly=True)
            scope = "global" if site is None or not use_router else "remote" if site == "B" and not b_url else "local"
            if use_router:
                identities = (
                    ["v_fragment_identity", "v_remote_fragment_identity"]
                    if scope == "global"
                    else ["v_remote_fragment_identity" if scope == "remote" else "v_fragment_identity"]
                )
                states = []
                for view, expected_site in zip(identities, ["A", "B"] if scope == "global" else [site], strict=True):
                    found = rows(connection, "SELECT * FROM " + view)
                    if len(found) != 1:
                        raise ValueError("Missing fragment identity")
                    contract.validate_state(found[0], expected_site)
                    states.append(found[0])
                if len(states) == 2 and states[0]["reference_sha256"] != states[1]["reference_sha256"]:
                    raise ValueError("Reference copies differ")
            else:
                # Rollback path retains the old all-sites availability contract.
                found = rows(connection, "SELECT site_id FROM v_site_health ORDER BY site_id")
                if found != [{"site_id": "A"}, {"site_id": "B"}]:
                    raise ValueError("Missing site")
            yield connection, scope
        except (psycopg2.Error, ValueError) as exc:
            raise HTTPException(503, "Distributed catalogue is unavailable") from exc
        finally:
            if connection is not None:
                # Closing discards this read-only transaction, including a
                # broken connection; a failed rollback must not mask the 503.
                connection.close()

    def rows(connection, sql, parameters=()):
        with connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(sql, parameters)
            return [dict(row) for row in cursor.fetchall()]

    def attach_images(connection, items, scope):
        if not items:
            return items
        images = rows(
            connection,
            f"""SELECT image_id,product_id,image_url,alt_text,is_primary,display_order
            FROM {relations(scope)[2]} WHERE product_id=ANY(%s)
            ORDER BY display_order,image_id""",
            ([item["product_id"] for item in items],),
        )
        by_product = {}
        for image in images:
            by_product.setdefault(image.pop("product_id"), []).append(image)
        for item in items:
            item["price"] = str(item["price"])
            item["product_images"] = by_product.get(item["product_id"], [])
        return items

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/ready")
    def ready():
        with database():
            return {"status": "ok", "sites": ["A", "B"]}

    @app.get("/products")
    def catalogue(
        skip: int = Query(0, ge=0),
        limit: int = Query(20, ge=1, le=100),
        category_id: int | None = Query(None, gt=0, le=2147483647),
        seller_id: int | None = Query(None, gt=0, le=2147483647),
        search: str | None = Query(None, max_length=200),
        sort_by: str = Query("created_at", pattern="^(created_at|price|rating)$"),
    ):
        site = None
        if seller_id is not None and use_router:
            # A is the reference authority. Seller routing deliberately needs A;
            # product ID routing does not consult it or cache seller mappings.
            with database("A") as (connection, _):
                owners = rows(connection, "SELECT site_id FROM v_local_seller_site WHERE seller_id=%s", (seller_id,))
            if not owners:
                raise HTTPException(404, "Seller has no fragment owner")
            if len(owners) != 1 or owners[0]["site_id"] not in ("A", "B"):
                raise HTTPException(503, "Seller fragment mapping is invalid")
            site = owners[0]["site_id"]
        with database(site) as (connection, scope):
            return catalogue_rows(connection, scope, site, skip, limit, category_id, seller_id, search, sort_by)

    def catalogue_rows(connection, scope, site, skip, limit, category_id, seller_id, search, sort_by):
        product_view, category_view, _ = relations(scope)
        conditions = ["p.status=1", "NOT p.is_deleted", "c.is_active", "NOT c.is_deleted"]
        params = []
        if seller_id is not None:
            conditions.append("p.seller_id=%s")
            params.append(seller_id)
        if category_id is not None:
            conditions.append("p.category_id=%s")
            params.append(category_id)
        if search:
            conditions.append("(p.title ILIKE %s OR p.description ILIKE %s)")
            params.extend([f"%{search}%", f"%{search}%"])
        where = " AND ".join(conditions)
        ordering = {"created_at": "p.created_at DESC", "price": "p.price ASC", "rating": "p.view_count DESC"}[sort_by]
        source = f" FROM {product_view} p JOIN {category_view} c USING(category_id) WHERE " + where
        total = rows(connection, "SELECT count(*) AS n" + source, params)[0]["n"]
        items = rows(
            connection,
            """SELECT p.product_id,p.seller_id,p.category_id,p.title,p.description,p.price,
            p.quantity,p.status,p.view_count,p.created_at,p.updated_at,p.site_id,c.name AS category_name"""
            + source
            + " ORDER BY "
            + ordering
            + ",p.product_id ASC OFFSET %s LIMIT %s",
            [*params, skip, limit],
        )
        return {
            "items": attach_images(connection, items, scope),
            "total": total,
            "skip": skip,
            "limit": limit,
            "complete": True,
            "sites": [site] if site is not None else ["A", "B"],
        }

    @app.get("/products/{product_id}")
    def detail(product_id: Annotated[int, APIPath(gt=0, le=2147483647)]):
        site = contract.product_site(product_id) if use_router else None
        with database(site) as (connection, scope):
            product_view, category_view, _ = relations(scope)
            items = rows(
                connection,
                f"""SELECT p.product_id,p.seller_id,p.category_id,p.title,p.description,p.price,
                p.quantity,p.status,p.view_count,p.created_at,p.updated_at,p.site_id,c.name AS category_name
                FROM {product_view} p JOIN {category_view} c USING(category_id)
                WHERE p.product_id=%s AND p.status=1 AND NOT p.is_deleted AND c.is_active AND NOT c.is_deleted""",
                (product_id,),
            )
            if not items:
                raise HTTPException(404, "Product not found")
            return attach_images(connection, items, scope)[0]

    return app


app = create_app()
