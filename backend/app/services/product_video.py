"""One optional video per listing: a shared link or a managed MP4 object."""

import json
import logging
import math
import re
import subprocess
import tempfile
import uuid
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit

from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.core.config import settings
from app.core.exceptions import BadRequestError
from app.services import storage

logger = logging.getLogger(__name__)
MANAGED_VIDEO = re.compile(r"/media/videos/products/(\d+)/[a-f0-9]{32}\.mp4")


def video_source(url: str | None) -> str | None:
    if not url:
        return None
    if url.startswith("/media/videos/products/"):
        return "upload"
    try:
        if urlsplit(url).hostname == "drive.google.com":
            return "google_drive"
    except ValueError:
        pass  # Malformed legacy links must not break the entire product list.
    return "external"  # Previously stored YouTube/other links remain readable.


def normalize_video_link(value: str | None, *, current_url: str | None = None) -> str | None:
    value = (value or "").strip()
    if not value:
        return None
    # An existing uploaded URL may be kept, but cannot be claimed by another listing.
    if value == current_url:
        return value
    try:
        parsed = urlsplit(value)
        if parsed.scheme != "https" or parsed.username or parsed.password or parsed.port not in (None, 443):
            raise ValueError
        if parsed.hostname == "drive.google.com":
            match = re.fullmatch(r"/file/d/([\w-]+)(?:/(?:view|preview))?/?", parsed.path)
            query = parse_qs(parsed.query)
            identifier = match[1] if match else query.get("id", [""])[0] if parsed.path in ("/open", "/uc") else ""
            if not re.fullmatch(r"[A-Za-z0-9_-]{10,200}", identifier):
                raise ValueError
            value = f"https://drive.google.com/file/d/{identifier}/view"
            resource = query.get("resourcekey", [""])[0]
            if resource:
                if not re.fullmatch(r"[A-Za-z0-9_-]{1,200}", resource):
                    raise ValueError
                value += "?" + urlencode({"resourcekey": resource})
        elif parsed.hostname not in ("youtube.com", "www.youtube.com", "youtu.be"):
            raise ValueError
        if len(value) > 500:
            raise ValueError
    except ValueError as exc:
        raise BadRequestError("Video phải là liên kết HTTPS Google Drive hoặc YouTube hợp lệ.") from exc
    return value


def validate_mp4(path: Path) -> None:
    """Inspect the actual container and codecs; a filename/MIME alone is insufficient."""
    with path.open("rb") as source:
        header = source.read(12)
    if len(header) < 12 or header[4:8] != b"ftyp":
        raise BadRequestError("File không phải video MP4 hợp lệ.")
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=format_name,duration:stream=codec_type,codec_name",
                "-of",
                "json",
                str(path),
            ],
            capture_output=True,
            timeout=20,
            check=True,
        )
        info = json.loads(result.stdout)
        duration = float(info["format"].get("duration", 0))
        streams = info.get("streams", [])
        videos = [s for s in streams if s.get("codec_type") == "video"]
        audio = [s for s in streams if s.get("codec_type") == "audio"]
        if (
            "mp4" not in info["format"]["format_name"].split(",")
            or not math.isfinite(duration)
            or duration <= 0
            or not videos
            or any(s.get("codec_name") != "h264" for s in videos)
            or any(s.get("codec_name") != "aac" for s in audio)
        ):
            raise ValueError
    except FileNotFoundError as exc:
        raise HTTPException(503, "Máy chủ chưa cài ffprobe để kiểm tra video.") from exc
    except (subprocess.SubprocessError, ValueError, KeyError, TypeError) as exc:
        raise BadRequestError("Video cần là MP4 dùng H.264 và âm thanh AAC (hoặc không có âm thanh).") from exc


async def save_video(file: UploadFile, product_id: int) -> str:
    if Path(file.filename or "").suffix.lower() != ".mp4" or file.content_type not in (
        "video/mp4",
        "application/mp4",
        "application/octet-stream",
    ):
        raise BadRequestError("Vui lòng chọn file MP4.")
    with tempfile.TemporaryDirectory(prefix="oldshop-video-") as directory:
        source = Path(directory) / "upload.mp4"
        size = 0
        with source.open("wb") as target:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > settings.MAX_VIDEO_UPLOAD_BYTES:
                    raise BadRequestError(
                        f"Video quá lớn (tối đa {settings.MAX_VIDEO_UPLOAD_BYTES // (1024 * 1024)} MB)."
                    )
                target.write(chunk)
        await run_in_threadpool(validate_mp4, source)
        key = f"videos/products/{product_id}/{uuid.uuid4().hex}.mp4"
        try:
            await run_in_threadpool(storage.get_storage().put_file, key, source)
        except Exception:
            discard_video(f"/media/{key}")
            raise
    return f"/media/{key}"


def discard_video(url: str | None) -> None:
    """Best effort after rollback/commit; storage errors must not undo a successful DB write."""
    if not url or not MANAGED_VIDEO.fullmatch(url):
        return
    try:
        storage.delete_media(url)
    except Exception:
        logger.exception("Could not remove obsolete video", extra={"video_url": url})


def cleanup_replaced_video(db: Session, old_url: str | None, new_url: str | None) -> None:
    if old_url == new_url or not old_url or not MANAGED_VIDEO.fullmatch(old_url):
        return  # In particular, never remove shared seed files or external videos.
    from app.models import Product

    if not db.query(Product.product_id).filter(Product.video_url == old_url).first():
        discard_video(old_url)
