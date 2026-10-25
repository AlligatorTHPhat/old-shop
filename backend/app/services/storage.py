"""Local media storage (mounted as a Docker volume in production)."""

import re
import unicodedata
from pathlib import Path

from fastapi import UploadFile

from app.core.config import settings
from app.core.exceptions import BadRequestError

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


def media_root() -> Path:
    return settings.MEDIA_DIR


def ensure_media_dirs() -> None:
    for sub in ("products", "users"):
        (media_root() / sub).mkdir(parents=True, exist_ok=True)


def _slugify(name: str) -> str:
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-zA-Z0-9]+", "-", ascii_name).strip("-").lower()[:60] or "image"


async def save_image(file: UploadFile, folder: str, prefix: str) -> str:
    """Validate and save an uploaded image. Returns its public URL path (/media/...)."""
    if not (file.content_type or "").startswith("image/"):
        raise BadRequestError(f"File {file.filename} is not an image")

    original = Path(file.filename or "image")
    extension = original.suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise BadRequestError(f"Unsupported image type: {extension or 'unknown'}")

    content = await file.read()
    if len(content) > settings.MAX_UPLOAD_BYTES:
        limit_mb = settings.MAX_UPLOAD_BYTES // (1024 * 1024)
        raise BadRequestError(f"File quá lớn (Tối đa {limit_mb}MB)")

    filename = f"{prefix}_{_slugify(original.stem)}{extension}"
    target = media_root() / folder / filename
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    return f"/media/{folder}/{filename}"


def delete_media(url_path: str) -> None:
    if url_path.startswith("/media/"):
        (media_root() / url_path.removeprefix("/media/")).unlink(missing_ok=True)
