"""Mongo-owned image annotations; PostgreSQL remains the authority for image membership."""

import re

from fastapi import HTTPException
from pydantic import TypeAdapter, ValidationError
from pymongo.errors import PyMongoError

from app.core.config import settings
from app.schemas.catalog import ImageMetadataInput, ProductDetailResponse
from app.services.mongo import get_database

ANNOTATIONS = TypeAdapter(list[ImageMetadataInput])
MAX_MATCHES = 5000


def enrich(response: ProductDetailResponse) -> ProductDetailResponse:
    if not settings.MONGO_URI:
        return response.model_copy(update={"image_metadata_status": "unavailable"})
    try:
        row = get_database().product_details.find_one(
            {"product_id": response.product_id, "deleted": False},
            {"image_metadata": 1},
            max_time_ms=2000,
        )
        if row is None:
            return response.model_copy(update={"image_metadata_status": "missing"})
        metadata = {entry.image_id: entry for entry in ANNOTATIONS.validate_python(row.get("image_metadata", []))}
        images = [
            image.model_copy(update=metadata[image.image_id].model_dump(exclude={"image_id"}))
            if image.image_id in metadata
            else image
            for image in response.product_images
        ]
        return response.model_copy(update={"product_images": images, "image_metadata_status": "available"})
    except (PyMongoError, ValidationError):
        return response.model_copy(update={"image_metadata_status": "unavailable"})


def replace(product_id: int, entries: list[ImageMetadataInput]) -> None:
    """Replace the product's annotation set atomically, without touching ETL-owned fields."""
    if not settings.MONGO_URI:
        raise HTTPException(503, "Chưa cấu hình kho metadata ảnh.")
    try:
        result = get_database().product_details.update_one(
            {"product_id": product_id, "deleted": False},
            [
                {
                    "$set": {
                        "image_metadata": {"$literal": [entry.model_dump() for entry in entries]},
                        "metadata_revision": {"$add": [{"$ifNull": ["$metadata_revision", 0]}, 1]},
                        "graph_pending_revision": {"$add": [{"$ifNull": ["$metadata_revision", 0]}, 1]},
                        "metadata_seed_owner": None,
                    }
                }
            ],
        )
    except PyMongoError as exc:
        raise HTTPException(503, "Không thể lưu metadata ảnh. Vui lòng thử lại.") from exc
    if not result.matched_count:
        raise HTTPException(409, "Sản phẩm chưa được đồng bộ metadata. Vui lòng thử lại sau khi ETL hoàn tất.")


def matching_image_ids(term: str) -> list[int]:
    """Literal, bounded substring search; current SQL membership/visibility is checked by the caller."""
    if not term.strip():
        raise HTTPException(422, "Nhập nội dung mô tả ảnh cần tìm.")
    if not settings.MONGO_URI:
        raise HTTPException(503, "Tìm theo mô tả ảnh chưa khả dụng.")
    pattern = re.escape(term.strip())
    pipeline = [
        {"$match": {"deleted": False}},
        {"$unwind": "$image_metadata"},
        {
            "$match": {
                "$or": [
                    {"image_metadata.caption": {"$regex": pattern, "$options": "i"}},
                    {"image_metadata.description": {"$regex": pattern, "$options": "i"}},
                ]
            }
        },
        {"$limit": MAX_MATCHES + 1},
        {"$project": {"_id": 0, "image_id": "$image_metadata.image_id"}},
    ]
    try:
        with get_database().product_details.aggregate(pipeline, maxTimeMS=2000) as cursor:
            rows = list(cursor)
    except PyMongoError as exc:
        raise HTTPException(503, "Tìm theo mô tả ảnh chưa khả dụng.") from exc
    if len(rows) > MAX_MATCHES:
        raise HTTPException(422, "Quá nhiều ảnh phù hợp; hãy nhập mô tả cụ thể hơn.")
    return [row["image_id"] for row in rows if type(row.get("image_id")) is int and row["image_id"] > 0]
