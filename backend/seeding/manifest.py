"""Deterministic global IDs, media checksums and expected queries for a seed run."""

from collections import Counter

from app.buckets.db import transaction
from app.services.allocation import Allocator, load_contract


def build(data, dataset_id):
    with transaction() as core:
        routes = {row["seller_id"]: Allocator(core).resolve_seller(row["seller_id"]) for row in data["products"]}
    contract = load_contract()
    return dict(
        dataset_id=dataset_id,
        dataset_hash=data["digest"],
        contract_digest=contract.digest(),
        reference_time=data["config"]["reference_time"],
        random_seed=data["config"]["random_seed"],
        scale=data["scale"],
        counts={
            name: len(data[name]) for name in ("users", "products", "images", "orders", "order_details", "reviews")
        },
        ids={
            name: sorted(row[field] for row in data[name])
            for name, field in (
                ("users", "user_id"),
                ("products", "product_id"),
                ("images", "image_id"),
                ("orders", "order_id"),
                ("order_details", "order_detail_id"),
                ("reviews", "review_id"),
            )
        },
        sites=dict(sorted(Counter(routes[p["seller_id"]].site_id for p in data["products"]).items())),
        buckets=dict(
            sorted(Counter(str(contract.bucket_for_seller(p["seller_id"])) for p in data["products"]).items())
        ),
        media=[
            {key: row[key] for key in ("image_id", "product_id", "image_url", "sha256", "size_bytes", "content_type")}
            for row in data["images"]
        ],
        expected_queries=[
            dict(
                q="alphaonly",
                image_ids=[row["image_id"] for row in data["metadata"] if "alphaonly" in row.get("description", "")],
            ),
            dict(q="zznomatchzz", image_ids=[]),
        ],
    )
