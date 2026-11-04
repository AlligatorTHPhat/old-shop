"""Optional read-only catalogue gateway over the site's global views.

Run explicitly with ``uvicorn app.catalogue_gateway:app``. It is not installed
over the existing checkout API. The database credential is global_reader at A.
"""

import os
from collections.abc import Iterator
from typing import Annotated, Any

import psycopg2
from fastapi import Depends, FastAPI, HTTPException, Query
from psycopg2.extras import RealDictCursor


def create_app(database_url: str | None = None) -> FastAPI:
    url = database_url if database_url is not None else os.getenv("DISTRIBUTED_CATALOG_URL", "")
    app = FastAPI(title="OldShop distributed catalogue", version="1.0.0")

    def database() -> Iterator[Any]:
        if not url:
            raise HTTPException(503, "Distributed catalogue is not configured")
        connection = None
        try:
            connection = psycopg2.connect(url, connect_timeout=3, options="-c statement_timeout=5000")
            connection.set_session(isolation_level="REPEATABLE READ", readonly=True)
            # Always touch both sites. LIMIT/filter pruning must never turn an
            # unavailable B into a successful, incomplete global response.
            with connection.cursor() as cursor:
                cursor.execute("SELECT site_id FROM v_site_health ORDER BY site_id")
                if cursor.fetchall() != [("A",), ("B",)]:
                    raise HTTPException(503, "Distributed catalogue is unavailable")
            yield connection
        except psycopg2.Error as exc:
            raise HTTPException(503, "Distributed catalogue is unavailable") from exc
        finally:
            if connection is not None:
                connection.close()

    def rows(connection, sql, parameters=()):
        with connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(sql, parameters)
            return [dict(row) for row in cursor.fetchall()]

    def attach_images(connection, items):
        if not items:
            return items
        images = rows(
            connection,
            """SELECT image_id,product_id,image_url,alt_text,is_primary,display_order
            FROM v_product_image WHERE product_id=ANY(%s)
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
    def ready(connection: Annotated[Any, Depends(database)]):
        return {"status": "ok", "sites": ["A", "B"]}

    @app.get("/products")
    def catalogue(
        connection: Annotated[Any, Depends(database)],
        skip: int = Query(0, ge=0),
        limit: int = Query(20, ge=1, le=100),
        category_id: int | None = Query(None, gt=0),
        search: str | None = Query(None, max_length=200),
        sort_by: str = Query("created_at", pattern="^(created_at|price|rating)$"),
    ):
        conditions = ["p.status=1", "NOT p.is_deleted", "c.is_active", "NOT c.is_deleted"]
        params = []
        if category_id is not None:
            conditions.append("p.category_id=%s")
            params.append(category_id)
        if search:
            conditions.append("(p.title ILIKE %s OR p.description ILIKE %s)")
            params.extend([f"%{search}%", f"%{search}%"])
        where = " AND ".join(conditions)
        ordering = {"created_at": "p.created_at DESC", "price": "p.price ASC", "rating": "p.view_count DESC"}[sort_by]
        source = " FROM v_product p JOIN v_category c USING(category_id) WHERE " + where
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
            "items": attach_images(connection, items),
            "total": total,
            "skip": skip,
            "limit": limit,
            "complete": True,
            "sites": ["A", "B"],
        }

    @app.get("/products/{product_id}")
    def detail(product_id: int, connection: Annotated[Any, Depends(database)]):
        items = rows(
            connection,
            """SELECT p.product_id,p.seller_id,p.category_id,p.title,p.description,p.price,
            p.quantity,p.status,p.view_count,p.created_at,p.updated_at,p.site_id,c.name AS category_name
            FROM v_product p JOIN v_category c USING(category_id)
            WHERE p.product_id=%s AND p.status=1 AND NOT p.is_deleted AND c.is_active AND NOT c.is_deleted""",
            (product_id,),
        )
        if not items:
            raise HTTPException(404, "Product not found")
        # A read-only gateway deliberately does not mutate view_count or expose
        # profiles, pending moderation, attributes/tags or checkout endpoints.
        return attach_images(connection, items)[0]

    return app


app = create_app()
