"""Video regressions. API tests require the isolated seeded PostgreSQL test DB."""

import asyncio
import io
import json
import os
import subprocess
import uuid

import pytest
from etl.extract import Source
from etl.pipelines.documents import project
from etl.pipelines.media import ensure_images
from etl.transform import video_url
from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session
from starlette.datastructures import Headers

from app.core.config import settings
from app.core.exceptions import BadRequestError
from app.services import product_video, storage


@pytest.fixture(scope="module")
def mp4(tmp_path_factory):
    path = tmp_path_factory.mktemp("video") / "test.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=black:s=32x32:r=5",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=44100:cl=mono",
            "-t",
            "0.4",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-movflags",
            "+faststart",
            str(path),
        ],
        check=True,
        timeout=20,
    )
    return path.read_bytes()


@pytest.mark.parametrize(
    "url",
    [
        "https://drive.google.com/file/d/abcdefghijk/view?usp=sharing",
        "https://drive.google.com/open?id=abcdefghijk",
        "https://drive.google.com/uc?id=abcdefghijk",
    ],
)
def test_drive_normalization(url):
    assert product_video.normalize_video_link(url) == "https://drive.google.com/file/d/abcdefghijk/view"


@pytest.mark.parametrize(
    "url",
    [
        "javascript:alert(1)",
        "https://drive.google.com.evil.test/file/d/abcdefghijk/view",
        "https://drive.google.com@evil.test/a",
        "http://drive.google.com/open?id=abcdefghijk",
        "/media/videos/products/42/" + "a" * 32 + ".mp4",
        "https://example.com/a.mp4",
    ],
)
def test_rejects_untrusted_links_and_claimed_uploads(url):
    with pytest.raises(BadRequestError):
        product_video.normalize_video_link(url)


def test_resourcekey_is_preserved():
    assert product_video.normalize_video_link(
        "https://drive.google.com/open?id=abcdefghijk&resourcekey=0-abc&usp=sharing"
    ).endswith("/abcdefghijk/view?resourcekey=0-abc")


def test_etl_preserves_mp4_and_required_drive_query_without_tracking():
    uploaded = "/media/videos/products/42/" + "a" * 32 + ".mp4"
    assert video_url(uploaded) == uploaded
    assert video_url("/media/videos/products/seed/product-demo.mp4") is not None
    assert video_url("/media/videos/products/../secret.mp4") is None
    assert video_url("https://drive.google.com/open?id=abcdefghijk&resourcekey=0-abc&token=secret") == (
        "https://drive.google.com/open?id=abcdefghijk&resourcekey=0-abc"
    )


def test_etl_product_projection_keeps_seed_video_reference():
    with Source() as source:
        document = project(source, "product", {"id": 20}, "video-test")
    assert document["video_url"] == "/media/videos/products/seed/product-demo.mp4"


def test_bounded_real_video_upload(tmp_path, monkeypatch, mp4):
    monkeypatch.setattr(settings, "MEDIA_DIR", tmp_path)
    monkeypatch.setattr(settings, "STORAGE_BACKEND", "local")

    def upload(data):
        return UploadFile(io.BytesIO(data), filename="movie.mp4", headers=Headers({"content-type": "video/mp4"}))

    url = asyncio.run(product_video.save_video(upload(mp4), 42))
    assert storage.local_path(url.removeprefix("/media/")).read_bytes() == mp4
    with pytest.raises(BadRequestError):
        asyncio.run(product_video.save_video(upload(b"this is not a video"), 42))
    with pytest.raises(BadRequestError):
        asyncio.run(product_video.save_video(upload(b"\x00\x00\x00\x18ftypisomgarbage"), 42))
    monkeypatch.setattr(settings, "MAX_VIDEO_UPLOAD_BYTES", 16)
    with pytest.raises(BadRequestError):
        asyncio.run(product_video.save_video(upload(mp4), 42))
    assert len(list(tmp_path.rglob("*.mp4"))) == 1


def test_rejects_real_mp4_with_unsupported_codec(tmp_path):
    path = tmp_path / "mpeg4.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=black:s=32x32:r=5",
            "-t",
            "0.4",
            "-c:v",
            "mpeg4",
            str(path),
        ],
        check=True,
        timeout=20,
    )
    with pytest.raises(BadRequestError):
        product_video.validate_mp4(path)


@pytest.mark.parametrize(
    "header,expected", [("bytes=0-9", (0, 9)), ("bytes=8-", (8, 99)), ("bytes=-10", (90, 99)), ("bytes=0-999", (0, 99))]
)
def test_single_byte_range(header, expected):
    assert storage.byte_range(header, 100) == expected


@pytest.mark.parametrize("header", ["bytes=100-", "bytes=-0", "bytes=9-2", "bytes=0-1,4-5", "bytes=-", "nonsense"])
def test_invalid_range_is_416(header):
    with pytest.raises(HTTPException) as error:
        storage.byte_range(header, 100)
    assert error.value.status_code == 416
    assert error.value.headers["Content-Range"] == "bytes */100"


@pytest.fixture
def video_seller(login):
    return login("user1@gmail.com")


def create_listing(client, seller, png_bytes, *, video=None, link=None):
    fields = {"category_id": "1", "title": "Video test", "price": "1000", "quantity": "1"}
    if link:
        fields["video_url"] = link
    files = [("files", ("photo.png", png_bytes, "image/png"))]
    if video is not None:
        files.append(("video_file", ("test.mp4", video, "video/mp4")))
    return client.post("/api/v1/products", headers=seller, data=fields, files=files)


def test_create_replace_remove_and_seek(client, video_seller, png_bytes, mp4):
    created = create_listing(client, video_seller, png_bytes, video=mp4)
    assert created.status_code == 201, created.text
    product = created.json()
    assert product["video_source"] == "upload"
    old_url = product["video_url"]
    assert client.get(old_url).content == mp4
    head = client.head(old_url)
    assert head.status_code == 200 and head.content == b""
    assert head.headers["content-length"] == str(len(mp4))
    partial = client.get(old_url, headers={"Range": "bytes=5-19"})
    assert partial.status_code == 206 and partial.content == mp4[5:20]
    assert partial.headers["content-type"] == "video/mp4"
    assert partial.headers["content-range"] == f"bytes 5-19/{len(mp4)}"
    assert client.get(old_url, headers={"Range": f"bytes={len(mp4)}-"}).status_code == 416

    endpoint = f"/api/v1/products/{product['product_id']}/listing"
    replaced = client.put(
        endpoint,
        headers=video_seller,
        data={"details": json.dumps({"title": "New title"})},
        files={"video_file": ("new.mp4", mp4, "video/mp4")},
    )
    assert replaced.status_code == 200, replaced.text
    assert replaced.json()["title"] == "New title"
    new_url = replaced.json()["video_url"]
    assert new_url != old_url and client.get(old_url).status_code == 404

    # Omitting video_url preserves the upload; explicit null removes it (also via legacy JSON API).
    kept = client.put(endpoint, headers=video_seller, data={"details": '{"quantity":2}'})
    assert kept.json()["video_url"] == new_url
    cleared = client.put(f"/api/v1/products/{product['product_id']}", headers=video_seller, json={"video_url": None})
    assert cleared.status_code == 200 and cleared.json()["video_url"] is None
    assert cleared.json()["video_source"] is None
    assert client.get(new_url).status_code == 404


def test_drive_mp4_switch_and_shared_seed_protection(client, video_seller, png_bytes, mp4):
    drive = "https://drive.google.com/file/d/abcdefghijk/view"
    created = create_listing(client, video_seller, png_bytes, link=drive).json()
    assert created["video_source"] == "google_drive"
    endpoint = f"/api/v1/products/{created['product_id']}/listing"
    uploaded = client.put(
        endpoint, headers=video_seller, data={"details": "{}"}, files={"video_file": ("v.mp4", mp4, "video/mp4")}
    ).json()
    switched = client.put(endpoint, headers=video_seller, data={"details": json.dumps({"video_url": drive})})
    assert switched.status_code == 200 and switched.json()["video_source"] == "google_drive"
    assert client.get(uploaded["video_url"]).status_code == 404
    seed = "/media/videos/products/seed/product-demo.mp4"
    product_video.cleanup_replaced_video(None, seed, drive)
    assert storage.local_path(seed.removeprefix("/media/")).is_file()


def test_bad_upload_and_bad_fields_leave_original_unchanged(client, video_seller, png_bytes, mp4):
    created = create_listing(client, video_seller, png_bytes, video=mp4).json()
    endpoint = f"/api/v1/products/{created['product_id']}/listing"
    original_files = set(settings.MEDIA_DIR.rglob("*.mp4"))
    bad = client.put(
        endpoint,
        headers=video_seller,
        data={"details": '{"title":"Should not save"}'},
        files={"video_file": ("fake.mp4", b"not mp4", "video/mp4")},
    )
    assert bad.status_code == 400
    bad_category = client.put(
        endpoint,
        headers=video_seller,
        data={"details": '{"category_id":99999999}'},
        files={"video_file": ("new.mp4", mp4, "video/mp4")},
    )
    assert bad_category.status_code == 400
    assert set(settings.MEDIA_DIR.rglob("*.mp4")) == original_files
    product = client.get(f"/api/v1/products/{created['product_id']}").json()
    assert product["title"] == created["title"] and product["video_url"] == created["video_url"]


def test_commit_failure_rolls_back_fields_and_removes_new_upload(client, video_seller, png_bytes, mp4, monkeypatch):
    created = create_listing(client, video_seller, png_bytes, video=mp4).json()
    original_files = set(settings.MEDIA_DIR.rglob("*.mp4"))

    def fail_commit(self):
        raise RuntimeError("simulated commit failure")

    with monkeypatch.context() as patch:
        patch.setattr(Session, "commit", fail_commit)
        with pytest.raises(RuntimeError, match="simulated commit failure"):
            client.put(
                f"/api/v1/products/{created['product_id']}/listing",
                headers=video_seller,
                data={"details": '{"title":"Uncommitted title"}'},
                files={"video_file": ("new.mp4", mp4, "video/mp4")},
            )
    assert set(settings.MEDIA_DIR.rglob("*.mp4")) == original_files
    product = client.get(f"/api/v1/products/{created['product_id']}").json()
    assert product["title"] == created["title"] and product["video_url"] == created["video_url"]


def test_removing_video_from_one_seed_product_keeps_shared_file(client, admin_headers):
    seed = "/media/videos/products/seed/product-demo.mp4"
    assert client.get("/api/v1/products/17").json()["video_url"] == seed
    assert client.put("/api/v1/products/17", headers=admin_headers, json={"video_url": None}).status_code == 200
    assert client.get("/api/v1/products/20").json()["video_url"] == seed
    assert client.head(seed).status_code == 200


def test_conflict_permission_and_claim_protection(client, video_seller, login, png_bytes, mp4):
    conflict = create_listing(
        client, video_seller, png_bytes, video=mp4, link="https://drive.google.com/file/d/abcdefghijk/view"
    )
    assert conflict.status_code == 400
    created = create_listing(client, video_seller, png_bytes, video=mp4).json()
    other_seller = login("user2@gmail.com")
    endpoint = f"/api/v1/products/{created['product_id']}/listing"
    assert client.put(endpoint, headers=other_seller, data={"details": "{}"}).status_code == 403
    own = create_listing(client, other_seller, png_bytes).json()
    claimed = client.put(
        f"/api/v1/products/{own['product_id']}", headers=other_seller, json={"video_url": created["video_url"]}
    )
    assert claimed.status_code == 400


@pytest.mark.skipif(os.getenv("VIDEO_MINIO_INTEGRATION") != "1", reason="Needs private video test bucket")
def test_real_minio_video_stream_and_range(client, monkeypatch, mp4):
    monkeypatch.setattr(settings, "STORAGE_BACKEND", "minio")
    client_s3 = storage.minio_client()
    bucket = settings.MINIO_BUCKET_PRODUCT_VIDEOS
    if not client_s3.bucket_exists(bucket):
        client_s3.make_bucket(bucket)
    file = UploadFile(io.BytesIO(mp4), filename="test.mp4", headers=Headers({"content-type": "video/mp4"}))
    url = asyncio.run(product_video.save_video(file, 999999))
    key = url.removeprefix("/media/")
    try:
        response = client.get(f"/media/{key}", headers={"Range": "bytes=-25"})
        assert response.status_code == 206 and response.content == mp4[-25:]
        assert response.headers["content-range"] == f"bytes {len(mp4) - 25}-{len(mp4) - 1}/{len(mp4)}"
        assert client.head(f"/media/{key}").headers["content-length"] == str(len(mp4))
        assert client.get(f"/media/{key}", headers={"Range": "bytes=999999999-"}).status_code == 416
    finally:
        client_s3.remove_object(bucket, key)


@pytest.mark.skipif(os.getenv("VIDEO_MINIO_INTEGRATION") != "1", reason="Needs private video test bucket")
def test_etl_copies_local_video_to_minio_before_ack(client, mp4):
    key = f"videos/products/999999/{uuid.uuid4().hex}.mp4"
    storage.LocalStorage().put(key, mp4)
    bucket = storage.bucket_for(key)
    client_s3 = storage.minio_client()
    if not client_s3.bucket_exists(bucket):
        client_s3.make_bucket(bucket)
    try:
        ensure_images({"images": [], "video_url": f"/media/{key}"})
        result = client_s3.get_object(bucket, key)
        try:
            assert result.read() == mp4
        finally:
            result.close()
            result.release_conn()
    finally:
        client_s3.remove_object(bucket, key)
        storage.LocalStorage().delete(key)
