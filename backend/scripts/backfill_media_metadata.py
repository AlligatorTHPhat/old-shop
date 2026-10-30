"""Fill nullable PG image metadata using exact referenced keys, never bucket scans."""

import json

from fastapi import HTTPException
from sqlalchemy import select

from app.core.database import SessionLocal
from app.models import ProductImage
from app.services.storage import image_metadata


def backfill(backend: str | None = None) -> dict:
    result = {"updated": 0, "unavailable_image_ids": []}
    with SessionLocal() as session:
        images = session.scalars(
            select(ProductImage).where(ProductImage.content_type.is_(None) | ProductImage.size_bytes.is_(None))
        )
        for image in images:
            if not image.image_url.startswith("/media/"):
                result["unavailable_image_ids"].append(image.image_id)
                continue
            try:
                metadata = image_metadata(image.image_url, backend)
            except HTTPException:
                result["unavailable_image_ids"].append(image.image_id)
                continue
            image.content_type = metadata["content_type"]
            image.size_bytes = metadata["size_bytes"]
            result["updated"] += 1
        session.commit()
    return result


if __name__ == "__main__":
    print(json.dumps(backfill()))
