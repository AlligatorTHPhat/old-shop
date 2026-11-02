"""Local/MinIO image and video storage behind the /media URL contract."""

import io
import mimetypes
import re
import shutil
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
    for sub in ("products", "users", "videos/products"):
        (media_root() / sub).mkdir(parents=True, exist_ok=True)


def validate_path(path: str) -> str:
    parts = path.split("/")
    if (
        not parts
        or parts[0] not in ("products", "users", "videos")
        or any(part in ("", ".", "..") for part in parts)
        or "\\" in path
        or (
            (parts[0] != "videos" and Path(path).suffix.lower() not in ALLOWED_EXTENSIONS)
            or (
                parts[0] == "videos"
                and (len(parts) != 4 or parts[1] != "products" or Path(path).suffix.lower() != ".mp4")
            )
        )
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
    if path.startswith("videos/"):
        return settings.MINIO_BUCKET_PRODUCT_VIDEOS
    return settings.MINIO_BUCKET_PRODUCT_IMAGES if path.startswith("products/") else settings.MINIO_BUCKET_USER_AVATARS


class StorageBackend(ABC):
    @abstractmethod
    def put(self, path: str, data: bytes) -> None: ...

    @abstractmethod
    def delete(self, path: str) -> None: ...

    @abstractmethod
    def put_file(self, path: str, source: Path) -> None: ...

    @abstractmethod
    def response(self, path: str, *, head: bool = False, range_header: str | None = None) -> Response: ...


def byte_range(value: str | None, size: int) -> tuple[int, int] | None:
    """Single HTTP byte range; malformed/unsatisfiable requests return 416."""
    if value is None:
        return None
    match = re.fullmatch(r"bytes=(\d{0,20})-(\d{0,20})", value.strip())
    if not match or not any(match.groups()) or size == 0:
        raise HTTPException(416, "Invalid byte range", headers={"Content-Range": f"bytes */{size}"})
    first, last = match.groups()
    start = int(first) if first else max(0, size - int(last))
    end = min(int(last), size - 1) if first and last else size - 1
    if start >= size or start > end:
        raise HTTPException(416, "Invalid byte range", headers={"Content-Range": f"bytes */{size}"})
    return start, end


def media_headers(size: int, selected: tuple[int, int] | None) -> dict[str, str]:
    headers = {"Accept-Ranges": "bytes", "Cache-Control": "public, max-age=3600"}
    headers["Content-Length"] = str(selected[1] - selected[0] + 1 if selected else size)
    if selected:
        headers["Content-Range"] = f"bytes {selected[0]}-{selected[1]}/{size}"
    return headers


class LocalStorage(StorageBackend):
    def put(self, path: str, data: bytes) -> None:
        target = local_path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    def delete(self, path: str) -> None:
        local_path(path).unlink(missing_ok=True)

    def put_file(self, path: str, source: Path) -> None:
        target = local_path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)

    def response(self, path: str, *, head: bool = False, range_header: str | None = None) -> Response:
        target = local_path(path)
        if not target.is_file():
            raise HTTPException(status_code=404, detail="Media not found")
        size = target.stat().st_size
        selected = byte_range(range_header, size) if not head else None
        headers = media_headers(size, selected)
        if head:
            return Response(headers=headers, media_type=content_type(path))
        if selected:

            def chunks():
                with target.open("rb") as source:
                    source.seek(selected[0])
                    remaining = selected[1] - selected[0] + 1
                    while remaining:
                        block = source.read(min(64 * 1024, remaining))
                        if not block:
                            break
                        remaining -= len(block)
                        yield block

            return StreamingResponse(chunks(), status_code=206, headers=headers, media_type=content_type(path))
        return FileResponse(target, media_type=content_type(path), headers=headers)


class MinioStorage(StorageBackend):
    def put_file(self, path: str, source: Path) -> None:
        try:
            minio_client().fput_object(bucket_for(path), path, str(source), content_type=content_type(path))
        except (S3Error, urllib3.exceptions.HTTPError, ValueError) as exc:
            raise HTTPException(status_code=503, detail="Video storage unavailable") from exc

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

    def response(self, path: str, *, head: bool = False, range_header: str | None = None) -> Response:
        try:
            client = minio_client()
            # Keep the existing image streaming contract; video supports HEAD and seeking.
            if path.startswith("videos/"):
                info = client.stat_object(bucket_for(path), path)
                selected = byte_range(range_header, info.size) if not head else None
                headers = media_headers(info.size, selected)
                if head:
                    return Response(media_type=content_type(path), headers=headers)
                arguments = {"offset": selected[0], "length": selected[1] - selected[0] + 1} if selected else {}
                result = client.get_object(bucket_for(path), path, **arguments)
            else:
                selected = None
                result = client.get_object(bucket_for(path), path)
                headers = {"Content-Length": result.headers["Content-Length"], "Cache-Control": "public, max-age=3600"}
        except S3Error as exc:
            if exc.code in ("NoSuchKey", "NoSuchObject", "NoSuchBucket"):
                raise HTTPException(status_code=404, detail="Media not found") from exc
            raise HTTPException(status_code=503, detail="Image storage unavailable") from exc
        except (urllib3.exceptions.HTTPError, ValueError) as exc:
            raise HTTPException(status_code=503, detail="Image storage unavailable") from exc

        def close():
            result.close()
            result.release_conn()

        if head:
            close()
            return Response(media_type=content_type(path), headers=headers)

        def chunks():
            try:
                yield from result.stream(64 * 1024)
            finally:
                close()

        return StreamingResponse(
            chunks(),
            status_code=206 if selected else 200,
            media_type=content_type(path),
            headers=headers,
            background=BackgroundTask(close),
        )


def get_storage() -> StorageBackend:
    return MinioStorage() if settings.STORAGE_BACKEND == "minio" else LocalStorage()


def ping_minio() -> bool:
    try:
        return all(
            minio_client().bucket_exists(bucket)
            for bucket in (
                settings.MINIO_BUCKET_PRODUCT_IMAGES,
                settings.MINIO_BUCKET_USER_AVATARS,
                settings.MINIO_BUCKET_PRODUCT_VIDEOS,
            )
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
