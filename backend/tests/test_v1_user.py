import io

import pytest


@pytest.fixture(scope="module")
def user(login):
    return login("user2@gmail.com")


def test_get_my_profile(client, user):
    response = client.get("/api/v1/users/me", headers=user)
    assert response.status_code == 200
    assert response.json()["email"] == "user2@gmail.com"
    assert response.json()["roles"]


def test_profile_update_cannot_change_active_flag(client, user):
    response = client.put("/api/v1/users/me", json={"address": "1 Lê Lợi", "is_active": False}, headers=user)
    assert response.status_code == 200
    assert response.json()["address"] == "1 Lê Lợi"
    assert response.json()["is_active"] is True


def test_upload_avatar(client, user, png_bytes):
    files = {"file": ("avatar.png", io.BytesIO(png_bytes), "image/png")}
    response = client.post("/api/v1/users/me/avatar", files=files, headers=user)
    assert response.status_code == 200
    assert response.json()["avatar_url"].startswith("/media/users/user_3_4_")


def test_contact_lifecycle(client, user):
    payload = {"full_name": "Nguyen Van Test", "phone_number": "0900111222", "address": "456 CMT8", "is_default": False}
    created = client.post("/api/v1/users/me/contacts", json=payload, headers=user)
    assert created.status_code == 201
    contact_id = created.json()["contact_id"]

    default = client.post(f"/api/v1/users/me/contacts/{contact_id}/set-default", headers=user)
    assert default.json()["is_default"] is True

    assert client.delete(f"/api/v1/users/me/contacts/{contact_id}", headers=user).status_code == 204
    ids = [c["contact_id"] for c in client.get("/api/v1/users/me/contacts", headers=user).json()]
    assert contact_id not in ids


def test_seller_dashboard_stats(client, user):
    response = client.get("/api/v1/users/seller/dashboard-stats", headers=user)
    assert response.status_code == 200
    assert {"totalProducts", "newOrders", "revenue", "rating"} <= response.json().keys()


def test_admin_user_list(client, admin_headers):
    response = client.get("/api/v1/users", headers=admin_headers)
    assert response.status_code == 200
    assert len(response.json()) > 1
