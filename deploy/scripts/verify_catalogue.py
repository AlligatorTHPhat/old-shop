"""Exercise the actual catalogue HTTP gateway and fail-closed behaviour."""

import json
from datetime import UTC, datetime
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from sites import EVIDENCE, save_json


def verify_api(sites):
    if sites.selected != "AB":
        raise ValueError("Automatic outage checks require the two local virtual sites")
    root = "http://127.0.0.1:" + sites.env.get("CATALOGUE_PORT", "56480")

    def request(path, expected=200, method="GET", payload=None):
        data = json.dumps(payload).encode() if payload is not None else None
        req = Request(root + path, data=data, method=method, headers={"Content-Type": "application/json"})
        try:
            with urlopen(req, timeout=15) as response:
                status, body = response.status, json.load(response)
        except HTTPError as exc:
            status, body = exc.code, json.load(exc)
        if status != expected:
            raise AssertionError(f"{method} {path}: expected {expected}, got {status}: {body}")
        return body

    request("/ready")
    all_products = request("/products?limit=100")
    assert all_products["total"] == 6 and all_products["complete"] is True
    assert {p["site_id"] for p in all_products["items"]} == {"A", "B"}
    ids = [p["product_id"] for p in all_products["items"]]
    assert ids == [1, 2, 3, 4, 9, 10], ids
    paged = [p["product_id"] for offset in (0, 2, 4) for p in request(f"/products?skip={offset}&limit=2")["items"]]
    assert paged == ids
    assert [p["product_id"] for p in request("/products?search=Site%20B&limit=100")["items"]] == [2, 4, 10]
    price_order = request("/products?sort_by=price&limit=100")["items"]
    assert [float(p["price"]) for p in price_order] == sorted(float(p["price"]) for p in price_order)
    assert all(p["category_id"] == 2 for p in request("/products?category_id=2")["items"])
    assert request("/products?category_id=3")["items"] == []
    assert request("/products?search=%27%3BSELECT%201%3B--")["items"] == []
    assert request("/products/2")["product_images"] == []
    assert len(request("/products/4")["product_images"]) == 4
    for identifier in (5, 6, 7, 8, 999999):
        request(f"/products/{identifier}", 404)
    for path in ("/products?limit=101", "/products?skip=-1", "/products?sort_by=arbitrary"):
        request(path, 422)
    request("/products", 405, "POST", {"title": "No writes through global views"})
    request("/products/2", 405, "DELETE")
    # Reader is denied all SQL mutation, even if a handler regresses later.
    denied = sites.sql("A", "UPDATE product SET price=0 WHERE product_id=1;", role="global", check=False)
    assert denied.returncode != 0 and "42501" in denied.stderr
    assert sites.query("B", "SELECT view_count FROM product WHERE product_id=2")[0]["view_count"] == 0
    try:
        sites.run(["stop", "-t", "2", "pg-b"])
        b_down = request("/products?limit=1", 503)
        request("/products/1", 503)  # A-only ID must not masquerade as a complete service.
        request("/ready", 503)
        request("/health")
    finally:
        sites.run(["up", "-d", "--wait", "--wait-timeout", "60", "pg-b"])
    assert request("/products/2")["site_id"] == "B"
    try:
        sites.run(["stop", "-t", "2", "pg-a"])
        request("/products", 503)
        request("/health")
    finally:
        sites.run(["up", "-d", "--wait", "--wait-timeout", "60", "pg-a"])
    request("/ready")
    report = {
        "status": "PASS",
        "verified_at": datetime.now(UTC).isoformat(),
        "physical_hosts_verified": False,
        "checks": [
            "global pagination",
            "category/search/sort before pagination",
            "parameter binding",
            "image batching and empty images",
            "pending/deleted product visibility",
            "input validation",
            "read-only HTTP and SQL",
            "no view-count mutation",
            "503 on A or B outage",
            "recovery",
        ],
        "product_ids": ids,
        "b_down_response": b_down,
        "scope": "Optional read-only gateway; existing commerce API, Mongo and checkout are unchanged",
    }
    save_json(EVIDENCE / "api_results.json", report)
    print("Catalogue HTTP integration and outage checks: PASS")
