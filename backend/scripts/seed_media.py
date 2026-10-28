"""Copy legacy and canonical seed media to MinIO without modifying PG or existing objects.

Run explicitly after init_minio provisioning: python -m scripts.seed_media
"""

import json
import re
import uuid
from pathlib import Path

from minio.error import S3Error
from sqlalchemy import select

from app.core.config import settings
from app.core.database import SessionLocal
from app.models import ProductImage, User
from app.services.storage import bucket_for, content_type, minio_client, validate_path
from scripts.init_db import DATABASE_DIR, SEED_MEDIA_DIR


def seed_media(root: Path = SEED_MEDIA_DIR) -> dict:
    client = minio_client()
    stats = {"uploaded": 0, "skipped": 0, "missing": [], "avatar_fallbacks": 0}

    def upload(source: Path, key: str):
        validate_path(key)
        if not source.is_file():
            stats["missing"].append(key)
            return
        bucket = bucket_for(key)
        try:
            client.stat_object(bucket, key)
            stats["skipped"] += 1
            return
        except S3Error as exc:
            if exc.code not in ("NoSuchKey", "NoSuchObject"):
                raise
        client.fput_object(bucket, key, str(source), content_type=content_type(key))
        stats["uploaded"] += 1

    if not root.is_dir():
        raise ValueError("Seed media directory is missing")
    # Preserve runtime uploads as well as seed files before switching storage backends.
    sources = {}
    for directory in (root, settings.MEDIA_DIR):
        if directory.is_dir():
            for source in sorted(directory.rglob("*")):
                if source.is_file() and source.resolve().is_relative_to(directory.resolve()):
                    relative = source.relative_to(directory).as_posix()
                    if source.suffix.lower() in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
                        sources[validate_path(relative)] = source
    for key, source in sources.items():
        upload(source, key)
    seed_users = (DATABASE_DIR / "03_seeds/user/seed.sql").read_text()
    seed_avatars = set(re.findall(r"'/media/(users/[^']+)'", seed_users))
    with SessionLocal() as session:
        for image in session.scalars(select(ProductImage)):
            if not image.image_url.startswith("/media/"):
                continue
            relative = validate_path(image.image_url.removeprefix("/media/"))
            source = sources.get(relative)
            if source is None:
                stats["missing"].append(relative)
                continue
            name = uuid.uuid5(uuid.NAMESPACE_URL, f"oldshop:product-image:{image.image_id}:{relative}").hex
            upload(source, f"products/{image.product_id}/{name}{source.suffix.lower()}")
        for user in session.scalars(select(User)):
            if not user.avatar_url or not user.avatar_url.startswith("/media/users/"):
                continue
            relative = validate_path(user.avatar_url.removeprefix("/media/"))
            source = sources.get(relative)
            if source is None:
                # Only known seed URLs may receive the default avatar fallback.
                if relative not in seed_avatars:
                    stats["missing"].append(relative)
                    continue
                source = root / "users/default.png"
                stats["avatar_fallbacks"] += 1
                upload(source, relative)
            upload(source, f"users/{user.user_id}/avatar{source.suffix.lower()}")
    return stats


if __name__ == "__main__":
    print(json.dumps(seed_media(), ensure_ascii=False))
