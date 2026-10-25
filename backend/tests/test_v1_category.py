import time


def test_list_categories_is_public(client):
    response = client.get("/api/v1/categories")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_category_lifecycle(client, admin_headers):
    """Tạo -> tạo con -> xóa khi còn active bị chặn -> vô hiệu hóa -> xóa mềm -> khôi phục."""
    name = f"Đồ điện tử cũ {time.time_ns()}"
    created = client.post("/api/v1/categories", json={"name": name, "description": "Laptop..."}, headers=admin_headers)
    assert created.status_code == 201
    cat_id = created.json()["category_id"]

    child = client.post(
        "/api/v1/categories", json={"name": f"{name} - con", "parent_id": cat_id}, headers=admin_headers
    )
    assert child.status_code == 201
    assert child.json()["parent_id"] == cat_id

    assert client.delete(f"/api/v1/categories/{cat_id}", headers=admin_headers).status_code == 400

    client.put(f"/api/v1/categories/{cat_id}", json={"is_active": False}, headers=admin_headers)
    assert client.delete(f"/api/v1/categories/{cat_id}", headers=admin_headers).status_code == 204
    assert client.get(f"/api/v1/categories/{cat_id}").status_code == 404

    restored = client.post(f"/api/v1/categories/{cat_id}/restore", headers=admin_headers)
    assert restored.status_code == 200
    assert restored.json()["is_deleted"] is False


def test_duplicate_name_rejected(client, admin_headers):
    existing = client.get("/api/v1/categories").json()[0]["name"]
    assert client.post("/api/v1/categories", json={"name": existing}, headers=admin_headers).status_code == 400


def test_regular_user_cannot_create(client, login):
    response = client.post("/api/v1/categories", json={"name": "Hack"}, headers=login("user1@gmail.com"))
    assert response.status_code == 403
