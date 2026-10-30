"""Reuse idempotent seed/runtime-media transfer and PG key-based metadata backfill."""

from minio.error import S3Error

from app.services.storage import bucket_for, content_type, local_path, minio_client, validate_path
from etl.transform import QualityError
from scripts.backfill_media_metadata import backfill
from scripts.init_db import SEED_MEDIA_DIR
from scripts.seed_media import seed_media


def run():
    result = seed_media()
    metadata = backfill("minio")
    result["metadata"] = metadata
    if result["missing"] or metadata["unavailable_image_ids"]:
        raise QualityError("media_source_missing")
    return result


def ensure_images(document):
    """Copy a newly referenced local image if needed; no bucket/volume scan per event."""
    client = minio_client()
    for image in document["images"]:
        key = validate_path(image["key"])
        bucket = bucket_for(key)
        try:
            client.stat_object(bucket, key)
            continue
        except S3Error as error:
            if error.code not in ("NoSuchKey", "NoSuchObject"):
                raise
        candidates = (local_path(key), SEED_MEDIA_DIR / key)
        source = next((path for path in candidates if path.is_file()), None)
        if source is None:
            raise QualityError("media_source_missing")
        client.fput_object(bucket, key, str(source), content_type=content_type(key))
