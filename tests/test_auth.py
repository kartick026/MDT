import pytest
import sys
from datetime import timedelta
from pathlib import Path
from starlette.testclient import TestClient

# Ensure backend is on sys.path
backend_dir = str(Path(__file__).parent.parent / "backend")
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app import app
from core.config import settings
from core.auth import (
    hash_password,
    verify_password,
    create_access_token,
    decode_access_token,
    authenticate_user,
)


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_password_hashing_and_verification():
    """Verify bcrypt salt hashing and password verification."""
    password = "secret-password-xyz-123"
    hashed = hash_password(password)
    assert hashed != password
    assert verify_password(password, hashed) is True
    assert verify_password("wrong-password", hashed) is False


def test_jwt_create_and_decode():
    """Verify JWT access token creation and decoding."""
    data = {"sub": "alice", "role": "engineer"}
    token = create_access_token(data, expires_delta=timedelta(minutes=15))
    assert isinstance(token, str)

    payload = decode_access_token(token)
    assert payload["sub"] == "alice"
    assert payload["role"] == "engineer"
    assert "exp" in payload
    assert "iat" in payload


def test_expired_jwt_rejection():
    """Verify that an expired JWT raises 401."""
    data = {"sub": "alice", "role": "engineer"}
    # Token expired 10 minutes ago
    expired_token = create_access_token(data, expires_delta=timedelta(minutes=-10))

    with pytest.raises(Exception) as exc_info:
        decode_access_token(expired_token)
    assert "expired" in str(exc_info.value).lower()


def test_invalid_jwt_tampering_rejection():
    """Verify that a tampered JWT raises 401."""
    token = create_access_token({"sub": "admin", "role": "admin"})
    tampered = token[:-4] + "abcd"

    with pytest.raises(Exception) as exc_info:
        decode_access_token(tampered)
    assert "invalid" in str(exc_info.value).lower() or "signature" in str(exc_info.value).lower()


def test_authenticate_user():
    """Verify authenticate_user with default admin credentials."""
    user = authenticate_user(settings.ADMIN_USERNAME, settings.ADMIN_PASSWORD)
    assert user is not None
    assert user.username == settings.ADMIN_USERNAME
    assert user.role == "admin"

    # Wrong password
    bad_user = authenticate_user(settings.ADMIN_USERNAME, "wrong-password-999")
    assert bad_user is None

    # Non-existent user
    unknown_user = authenticate_user("nonexistent_user", "password")
    assert unknown_user is None


def test_api_login_json_success(client):
    """Verify POST /auth/login with valid JSON credentials returns JWT."""
    payload = {
        "username": settings.ADMIN_USERNAME,
        "password": settings.ADMIN_PASSWORD
    }
    response = client.post("/auth/login", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["expires_in"] > 0
    assert data["user"]["username"] == settings.ADMIN_USERNAME
    assert data["user"]["role"] == "admin"


def test_api_login_json_invalid_credentials(client):
    """Verify POST /auth/login with bad credentials returns 401."""
    payload = {
        "username": settings.ADMIN_USERNAME,
        "password": "incorrect-password"
    }
    response = client.post("/auth/login", json=payload)
    assert response.status_code == 401
    assert "Incorrect" in response.json()["detail"]


def test_viewer_signup_and_login(client, tmp_path, monkeypatch):
    """Self-service registration creates a durable, least-privilege account."""
    import uuid
    import core.auth as auth_module
    monkeypatch.setattr(auth_module, "USERS_FILE", tmp_path / "users.json")
    username = f"viewer-{uuid.uuid4().hex[:8]}"
    response = client.post("/auth/register", json={
        "username": username,
        "password": "safe-viewer-password",
    })
    assert response.status_code == 201
    data = response.json()
    assert data["user"]["username"] == username
    assert data["user"]["role"] == "viewer"
    assert data["access_token"]

    login = client.post("/auth/login", json={
        "username": username,
        "password": "safe-viewer-password",
    })
    assert login.status_code == 200
    assert login.json()["user"]["role"] == "viewer"


def test_signup_rejects_duplicate_username(client):
    response = client.post("/auth/register", json={
        "username": "admin",
        "password": "safe-viewer-password",
    })
    assert response.status_code == 409


def test_api_login_oauth2_form(client):
    """Verify POST /auth/token with form data works for Swagger UI."""
    data = {
        "username": settings.ADMIN_USERNAME,
        "password": settings.ADMIN_PASSWORD
    }
    response = client.post("/auth/token", data=data)
    assert response.status_code == 200
    res_data = response.json()
    assert "access_token" in res_data
    assert res_data["token_type"] == "bearer"


def test_api_me_authenticated(client):
    """Verify GET /auth/me returns current user profile when authenticated."""
    # Obtain token
    login_res = client.post("/auth/login", json={
        "username": settings.ADMIN_USERNAME,
        "password": settings.ADMIN_PASSWORD
    })
    token = login_res.json()["access_token"]

    response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    data = response.json()
    assert data["username"] == settings.ADMIN_USERNAME
    assert data["role"] == "admin"


def test_api_me_unauthenticated(client):
    """Verify GET /auth/me returns 401 when no token is provided."""
    response = client.get("/auth/me")
    assert response.status_code == 401


def test_api_refresh_token(client):
    """Verify POST /auth/refresh generates a fresh token for active user."""
    login_res = client.post("/auth/login", json={
        "username": settings.ADMIN_USERNAME,
        "password": settings.ADMIN_PASSWORD
    })
    token = login_res.json()["access_token"]

    refresh_res = client.post("/auth/refresh", headers={"Authorization": f"Bearer {token}"})
    assert refresh_res.status_code == 200
    new_data = refresh_res.json()
    assert "access_token" in new_data
    assert new_data["access_token"] != ""


def test_protected_registry_endpoint_unauthenticated(client):
    """Verify POST /registry/services requires authentication."""
    payload = {
        "name": "unauthorized-service",
        "port": 9999,
        "url": "http://localhost:9999"
    }
    response = client.post("/registry/services", json=payload)
    assert response.status_code == 401


def test_protected_registry_endpoint_authenticated(client):
    """Verify POST /registry/services succeeds when authenticated."""
    login_res = client.post("/auth/login", json={
        "username": settings.ADMIN_USERNAME,
        "password": settings.ADMIN_PASSWORD
    })
    token = login_res.json()["access_token"]

    payload = {
        "name": "auth-verified-service",
        "port": 9998,
        "url": "http://localhost:9998",
        "language": "python",
        "description": "Authenticated service registration"
    }
    response = client.post(
        "/registry/services",
        json=payload,
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "success"


def test_viewer_cannot_mutate_registry(client):
    """Viewer credentials must not bypass the UI's read-only contract."""
    login_res = client.post("/auth/login", json={
        "username": "auditor",
        "password": "auditor123",
    })
    token = login_res.json()["access_token"]

    response = client.post(
        "/registry/reset-default",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403


def test_production_rejects_insecure_or_missing_secrets():
    """App must fail fast in production if JWT or Webhook secrets are missing or insecure."""
    from pydantic import ValidationError
    from core.config import Settings

    # Production with empty/default secrets must raise ValidationError
    with pytest.raises(ValidationError):
        Settings(ENVIRONMENT="production", JWT_SECRET_KEY="")

    with pytest.raises(ValidationError):
        Settings(
            ENVIRONMENT="production",
            JWT_SECRET_KEY="mdt-production-super-secret-jwt-key-minimum-32-chars!",
        )

    with pytest.raises(ValidationError):
        Settings(
            ENVIRONMENT="production",
            JWT_SECRET_KEY="short-key",
        )

    with pytest.raises(ValidationError):
        Settings(
            ENVIRONMENT="production",
            JWT_SECRET_KEY="a-sufficiently-long-production-key-at-least-32-characters!",
            GITHUB_WEBHOOK_SECRET="secret",
        )

    # Valid production settings pass
    prod_settings = Settings(
        ENVIRONMENT="production",
        JWT_SECRET_KEY="a-sufficiently-long-production-key-at-least-32-characters!",
        GITHUB_WEBHOOK_SECRET="a-valid-high-entropy-webhook-secret-string",
        ADMIN_PASSWORD="super-strong-production-admin-password",
        NEO4J_PASSWORD="super-strong-production-neo4j-password",
        AUDITOR_PASSWORD="super-strong-production-auditor-password",
    )
    assert prod_settings.ENVIRONMENT == "production"
    assert len(prod_settings.JWT_SECRET_KEY) >= 32
