def test_pending_products(client, mod_headers):
    response = client.get("/api/v1/moderator/products/pending", headers=mod_headers)
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_lock_and_unlock_user(client, mod_headers):
    """user_id 4 = user2."""
    lock = client.post(
        "/api/v1/moderator/users/4/lock-unlock", json={"action": "lock", "reason": "Vi phạm"}, headers=mod_headers
    )
    assert lock.status_code == 200
    assert lock.json()["user"]["is_active"] is False

    unlock = client.post(
        "/api/v1/moderator/users/4/lock-unlock", json={"action": "unlock", "reason": "Đã xử lý"}, headers=mod_headers
    )
    assert unlock.status_code == 200
    assert unlock.json()["user"]["is_active"] is True


def test_cannot_lock_staff_account(client, mod_headers):
    response = client.post(
        "/api/v1/moderator/users/1/lock-unlock", json={"action": "lock", "reason": "x"}, headers=mod_headers
    )
    assert response.status_code == 400


def test_reported_reviews_listing(client, mod_headers):
    response = client.get("/api/v1/moderator/reviews/violations", headers=mod_headers)
    assert response.status_code == 200
    assert all(review["rating"] == 0 for review in response.json())


def test_moderator_routes_require_role(client, login):
    assert client.get("/api/v1/moderator/products/pending").status_code == 401
    assert client.get("/api/v1/moderator/products/pending", headers=login("user1@gmail.com")).status_code == 403
