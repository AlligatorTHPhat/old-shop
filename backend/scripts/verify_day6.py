"""HTTP probes against the isolated Day 6 stack; emits statuses/counts, no credentials/PII."""

import argparse
import json
import urllib.error
import urllib.parse
import urllib.request

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--mode", choices=("normal", "mongo-down", "minio-down"), default="normal")
parser.add_argument("--authenticated", action="store_true", help="Use public seed credentials only on disposable tests")
args = parser.parse_args()


def get(path, base="http://127.0.0.1:8000", headers=None):
    try:
        response = urllib.request.urlopen(urllib.request.Request(base + path, headers=headers or {}), timeout=25)
    except urllib.error.HTTPError as error:
        return error.code, json.load(error)
    with response:
        if path.startswith("/media/"):
            return response.status, {"bytes": len(response.read())}
        return response.status, json.load(response)


result = {}
for path in ("/health", "/api/v1/products", "/api/v1/products/1", "/api/v1/categories"):
    code, body = get(path)
    assert code == 200, (path, code)
    result[path] = code
    if path == "/api/v1/products/1":
        assert body["price"] and "attributes" in body
        if args.mode == "mongo-down":
            assert body["metadata_status"] == "unavailable"
        image = body["product_images"][0]["image_url"]
code, body = get("/ready")
assert code == (200 if args.mode == "normal" else 503), body
result["readiness"] = {"code": code, **body}
code, _ = get("/api/v1/products", base="http://frontend:8080")
assert code == 200
result["frontend_proxy"] = code
code, _ = get("/api/v1/products?" + urllib.parse.urlencode({"attributes": '{"brand":"probe"}'}))
assert code == (503 if args.mode == "mongo-down" else 200)
result["attribute_search"] = code
code, body = get(image)
assert code == (503 if args.mode == "minio-down" else 200), (code, body)
result["media"] = code


# Credentials are public seed accounts in this disposable stack; tokens are never emitted.
def login(email, password):
    request = urllib.request.Request(
        "http://127.0.0.1:8000/api/v1/auth/login",
        data=urllib.parse.urlencode({"username": email, "password": password}).encode(),
    )
    with urllib.request.urlopen(request, timeout=25) as response:
        return {"Authorization": "Bearer " + json.load(response)["access_token"]}


if args.authenticated:
    headers = login("user1@gmail.com", "user123")
    if args.mode == "minio-down":
        _, before = get("/api/v1/users/me", headers=headers)
        boundary = "day6-upload-probe"
        payload = (
            (
                f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="probe.png"\r\n'
                "Content-Type: image/png\r\n\r\n"
            ).encode()
            + b"image-probe"
            + f"\r\n--{boundary}--\r\n".encode()
        )
        request = urllib.request.Request(
            "http://127.0.0.1:8000/api/v1/users/me/avatar",
            data=payload,
            headers={**headers, "Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
        try:
            urllib.request.urlopen(request, timeout=25)
        except urllib.error.HTTPError as error:
            assert error.code == 503
        else:
            raise AssertionError("Upload unexpectedly succeeded while MinIO was stopped")
        _, after = get("/api/v1/users/me", headers=headers)
        assert before["avatar_url"] == after["avatar_url"]
        result["failed_upload_preserved_avatar"] = True
    for path in ("/api/v1/cart", "/api/v1/orders"):
        code, _ = get(path, headers=headers)
        assert code == 200
        result[path] = code
    code, stats = get("/api/v1/admin/stats", headers=login("admin@oldshop.com", "admin123"))
    assert code == 200 and stats["sales_report"]["available"]
    result["admin_report"] = {"code": code, "available": True}
result["result"] = "PASS"
print(json.dumps(result))
