import time

import pytest


def test_register_new_user(client):
    """Đăng ký tài khoản mới; username được sinh tự động từ email."""
    payload = {
        "email": f"tester_{time.time_ns()}@gmail.com",
        "password": "password123",
        "full_name": "QA Automation User",
        "phone_number": "0901112223",
        "address": "TP.HCM",
    }
    response = client.post("/api/v1/auth/register", json=payload)

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == payload["email"]
    assert body["username"].startswith("tester_")
    assert body["role_id"] == 3


def test_register_rejects_duplicate_email(client):
    payload = {"email": "user1@gmail.com", "password": "anypassword", "full_name": "Trùng Email"}
    assert client.post("/api/v1/auth/register", json=payload).status_code == 400


def test_register_cannot_choose_staff_role(client):
    payload = {"email": f"x_{time.time_ns()}@gmail.com", "password": "password123", "full_name": "X", "role_id": 1}
    assert client.post("/api/v1/auth/register", json=payload).status_code == 422


@pytest.mark.parametrize(
    ("email", "password", "expected_status"),
    [
        ("admin@oldshop.com", "admin123", 200),
        ("mod1@oldshop.com", "mod123", 200),
        ("user1@gmail.com", "user123", 200),
        ("user1@gmail.com", "wrongpass", 401),
        ("nonexistent@gmail.com", "pass", 401),
    ],
)
def test_login_scenarios(client, email, password, expected_status):
    response = client.post("/api/v1/auth/login", data={"username": email, "password": password})
    assert response.status_code == expected_status
    if expected_status == 200:
        assert "access_token" in response.json()


def test_get_me(client, login):
    response = client.get("/api/v1/auth/me", headers=login("user2@gmail.com"))
    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "user2@gmail.com"
    assert body["role_id"] == 3
    assert body["roles"][0]["role_id"] == 3


def test_me_requires_token(client):
    assert client.get("/api/v1/auth/me").status_code == 401
    assert client.get("/api/v1/auth/me", headers={"Authorization": "Bearer garbage"}).status_code == 401
