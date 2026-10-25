import time


def test_dashboard_stats(client, admin_headers):
    response = client.get("/api/v1/admin/stats", headers=admin_headers)
    assert response.status_code == 200
    assert {"total_users", "total_orders", "pending_products", "total_revenue"} <= response.json().keys()


def test_moderator_lifecycle(client, admin_headers):
    """Tạo moderator -> khóa -> mở khóa."""
    uid = time.time_ns()
    payload = {
        "username": f"qa_mod_{uid}",
        "email": f"qa_{uid}@oldshop.com",
        "password": "password123",
        "full_name": "Automation Tester",
        "phone_number": "0900000000",
        "address": "Phòng Lab",
    }
    created = client.post("/api/v1/admin/moderators", json=payload, headers=admin_headers)
    assert created.status_code == 200
    assert created.json()["role_id"] == 2
    mod_id = created.json()["user_id"]

    locked = client.patch(
        f"/api/v1/admin/moderators/{mod_id}/status", json={"action": "lock", "reason": "Test"}, headers=admin_headers
    )
    assert locked.json()["is_active"] is False

    unlocked = client.patch(
        f"/api/v1/admin/moderators/{mod_id}/status", json={"action": "unlock", "reason": "Test"}, headers=admin_headers
    )
    assert unlocked.json()["is_active"] is True

    duplicate = client.post("/api/v1/admin/moderators", json=payload, headers=admin_headers)
    assert duplicate.status_code == 400


def test_violation_logs_include_username(client, admin_headers):
    response = client.get("/api/v1/admin/violation-logs?limit=1", headers=admin_headers)
    assert response.status_code == 200
    if response.json():
        assert "username" in response.json()[0]


def test_admin_routes_require_auth(client, login):
    assert client.get("/api/v1/admin/stats").status_code == 401
    assert client.get("/api/v1/admin/stats", headers=login("user1@gmail.com")).status_code == 403
