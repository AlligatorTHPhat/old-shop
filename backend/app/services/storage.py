"""Local/MinIO image storage behind the existing /media URL contract."""

import io
import mimetypes
import re
import unicodedata
import uuid
from abc import ABC, abstractmethod
from functools import lru_cache
from pathlib import Path

import urllib3
from fastapi import HTTPException, UploadFile
from minio import Minio
from minio.error import S3Error
from starlette.background import BackgroundTask
from starlette.concurrency import run_in_threadpool
from starlette.responses import FileResponse, Response, StreamingResponse

from app.core.config import settings
from app.core.exceptions import BadRequestError

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


def media_root() -> Path:
    return settings.MEDIA_DIR


def ensure_media_dirs() -> None:
    for sub in ("products", "users"):
        (media_root() / sub).mkdir(parents=True, exist_ok=True)


def validate_path(path: str) -> str:
    parts = path.split("/")
    if (
        not parts
        or parts[0] not in ("products", "users")
        or any(part in ("", ".", "..") for part in parts)
        or "\\" in path
        or Path(path).suffix.lower() not in ALLOWED_EXTENSIONS
    ):
        raise HTTPException(status_code=404, detail="Media not found")
    return path


def local_path(path: str) -> Path:
    result = (media_root() / validate_path(path)).resolve()
    if not result.is_relative_to(media_root().resolve()):
        raise HTTPException(status_code=404, detail="Media not found")
    return result


def content_type(path: str) -> str:
    return mimetypes.guess_type(path)[0] or "application/octet-stream"


@lru_cache(maxsize=1)
def minio_client() -> Minio:
    if not settings.MINIO_ACCESS_KEY or not settings.MINIO_SECRET_KEY:
        raise ValueError("MinIO application credentials are not configured")
    return Minio(
        settings.MINIO_ENDPOINT,
        access_key=settings.MINIO_ACCESS_KEY,
        secret_key=settings.MINIO_SECRET_KEY,
        secure=settings.MINIO_SECURE,
        http_client=urllib3.PoolManager(timeout=urllib3.Timeout(connect=3, read=10), retries=False),
    )


def bucket_for(path: str) -> str:
    validate_path(path)
    return settings.MINIO_BUCKET_PRODUCT_IMAGES if path.startswith("products/") else settings.MINIO_BUCKET_USER_AVATARS


class StorageBackend(ABC):
    @abstractmethod
    def put(self, path: str, data: bytes) -> None: ...

    @abstractmethod
    def delete(self, path: str) -> None: ...

    @abstractmethod
    def response(self, path: str, *, head: bool = False) -> Response: ...


class LocalStorage(StorageBackend):
    def put(self, path: str, data: bytes) -> None:
        target = local_path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    def delete(self, path: str) -> None:
        local_path(path).unlink(missing_ok=True)

    def response(self, path: str, *, head: bool = False) -> Response:
        target = local_path(path)
        if not target.is_file():
            raise HTTPException(status_code=404, detail="Media not found")
        return FileResponse(target, media_type=content_type(path))


class MinioStorage(StorageBackend):
    def put(self, path: str, data: bytes) -> None:
        try:
            minio_client().put_object(
                bucket_for(path), path, io.BytesIO(data), len(data), content_type=content_type(path)
            )
        except (S3Error, urllib3.exceptions.HTTPError, ValueError) as exc:
            raise HTTPException(status_code=503, detail="Image storage unavailable") from exc

    def delete(self, path: str) -> None:
        try:
            minio_client().remove_object(bucket_for(path), path)
        except (S3Error, urllib3.exceptions.HTTPError, ValueError) as exc:
            raise HTTPException(status_code=503, detail="Image storage unavailable") from exc

    def response(self, path: str, *, head: bool = False) -> Response:
        try:
            result = minio_client().get_object(bucket_for(path), path)
        except S3Error as exc:
            if exc.code in ("NoSuchKey", "NoSuchObject", "NoSuchBucket"):
                raise HTTPException(status_code=404, detail="Media not found") from exc
            raise HTTPException(status_code=503, detail="Image storage unavailable") from exc
        except (urllib3.exceptions.HTTPError, ValueError) as exc:
            raise HTTPException(status_code=503, detail="Image storage unavailable") from exc

        def close():
            result.close()
            result.release_conn()

        headers = {"Content-Length": result.headers["Content-Length"], "Cache-Control": "public, max-age=3600"}
        if head:
            close()
            return Response(media_type=content_type(path), headers=headers)

        def chunks():
            try:
                yield from result.stream(64 * 1024)
            finally:
                close()

        return StreamingResponse(
            chunks(), media_type=content_type(path), headers=headers, background=BackgroundTask(close)
        )


def get_storage() -> StorageBackend:
    return MinioStorage() if settings.STORAGE_BACKEND == "minio" else LocalStorage()


def ping_minio() -> bool:
    try:
        return all(
            minio_client().bucket_exists(bucket)
            for bucket in (settings.MINIO_BUCKET_PRODUCT_IMAGES, settings.MINIO_BUCKET_USER_AVATARS)
        )
    except (S3Error, urllib3.exceptions.HTTPError, ValueError):
        return False


def _slugify(name: str) -> str:
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-zA-Z0-9]+", "-", ascii_name).strip("-").lower()[:60] or "image"


async def save_image(file: UploadFile, folder: str, prefix: str) -> str:
    if not (file.content_type or "").startswith("image/"):
        raise BadRequestError(f"File {file.filename} is not an image")
    original = Path(file.filename or "image")
    extension = original.suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise BadRequestError(f"Unsupported image type: {extension or 'unknown'}")
    content = await file.read(settings.MAX_UPLOAD_BYTES + 1)
    if len(content) > settings.MAX_UPLOAD_BYTES:
        raise BadRequestError(f"File quá lớn (Tối đa {settings.MAX_UPLOAD_BYTES // (1024 * 1024)}MB)")
    token = uuid.uuid4().hex
    if settings.STORAGE_BACKEND == "minio":
        match = (
            re.fullmatch(r"prod_(\d+)_\d+", prefix) if folder == "products" else re.fullmatch(r"user_\d+_(\d+)", prefix)
        )
        if not match or folder not in ("products", "users"):
            raise BadRequestError("Invalid image destination")
        name = f"{token}{extension}" if folder == "products" else f"avatar-{token}{extension}"
        path = f"{folder}/{match[1]}/{name}"
    else:
        path = f"{folder}/{prefix}_{_slugify(original.stem)}_{token}{extension}"
    await run_in_threadpool(get_storage().put, path, content)
    return f"/media/{path}"


def delete_media(url_path: str) -> None:
    if url_path.startswith("/media/"):
        get_storage().delete(url_path.removeprefix("/media/"))


def image_metadata(url: str, backend: str | None = None) -> dict:
    """Stat one referenced image; never scan a bucket or infer a product from its filename."""
    path = validate_path(url.removeprefix("/media/"))
    if (backend or settings.STORAGE_BACKEND) == "minio":
        try:
            info = minio_client().stat_object(bucket_for(path), path)
            return {"content_type": info.content_type, "size_bytes": info.size}
        except (S3Error, urllib3.exceptions.HTTPError, ValueError) as exc:
            raise HTTPException(status_code=503, detail="Image metadata unavailable") from exc
    try:
        return {"content_type": content_type(path), "size_bytes": local_path(path).stat().st_size}
    except OSError as exc:
        raise HTTPException(status_code=404, detail="Media not found") from exc
