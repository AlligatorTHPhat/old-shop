"""Read-only compatibility facade using the SAME bucket repositories as the main API."""

from fastapi import FastAPI, HTTPException, Query

from app.buckets import catalogue
from app.buckets.api import detail, related, search_images
from app.buckets.db import product_route, rows, transaction


def create_app():
    app = FastAPI(title="OldShop bucket catalogue", version="2.0.0")

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/ready")
    def ready():
        with transaction() as core:
            sites = [
                row["site_id"] for row in rows(core, "SELECT site_id FROM site_registry WHERE active ORDER BY site_id")
            ]
        for site in sites:
            with transaction(site):
                pass
        return {"status": "ok", "sites": sites}

    @app.get("/products")
    def products(
        skip: int = Query(0, ge=0),
        limit: int = Query(20, ge=1, le=100),
        seller_id: int | None = Query(None, gt=0),
        category_id: int | None = Query(None, gt=0),
        search: str | None = Query(None, max_length=200),
        sort_by: str = Query("created_at", pattern="^(created_at|price|rating)$"),
    ):
        items = catalogue.listing(
            limit=100000, seller_id=seller_id, category_id=category_id, search=search, sort_by=sort_by
        )
        if len(items) >= 100000:
            raise HTTPException(422, "Narrow the gateway filter; exact count exceeds the local limit")
        with transaction() as core:
            sites = [
                row["site_id"] for row in rows(core, "SELECT site_id FROM site_registry WHERE active ORDER BY site_id")
            ]
        return dict(
            items=items[skip : skip + limit], total=len(items), skip=skip, limit=limit, complete=True, sites=sites
        )

    @app.get("/products/{product_id}")
    def product(product_id: int):
        response = detail(product_id, user=None)
        route = product_route(product_id)
        return {**response.model_dump(mode="json"), "site_id": route.site_id, "bucket_id": route.bucket_id}

    app.add_api_route("/products/{product_id}/related", related, methods=["GET"])
    app.add_api_route("/images/search", search_images, methods=["GET"])
    return app
