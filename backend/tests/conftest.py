"""Integration tests run against a real PostgreSQL loaded with database/init.sql (schema + seed data).

See the "Tests" section of the README for the exact commands.
"""

import os
import tempfile

# Must be set before `app` is imported: settings are read once at import time.
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-production")
os.environ.setdefault("MEDIA_DIR", tempfile.mkdtemp(prefix="oldshop-media-"))
os.environ.setdefault("GAS_WEBHOOK_URL", "")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

ADMIN = ("admin@oldshop.com", "admin123")
MODERATOR = ("mod1@oldshop.com", "mod123")

# Smallest valid PNG (1x1), for upload tests.
PNG_1PX = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    b"\x00\x00\x00\rIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe\xa7\x35\x81\x84\x00\x00\x00\x00IEND\xaeB`\x82"
)


@pytest.fixture
def png_bytes() -> bytes:
    return PNG_1PX


@pytest.fixture(scope="session")
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(scope="session")
def login(client):
    """Return Authorization headers for the given seeded account."""

    def _login(email: str, password: str = "user123") -> dict[str, str]:
        response = client.post("/api/v1/auth/login", data={"username": email, "password": password})
        assert response.status_code == 200, f"cannot log in as {email}: {response.text}"
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    return _login


@pytest.fixture(scope="session")
def admin_headers(login):
    return login(*ADMIN)


@pytest.fixture(scope="session")
def mod_headers(login):
    return login(*MODERATOR)
