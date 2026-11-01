"""Google-only publication, old-token rejection and confidential-error regressions."""
from fastapi import HTTPException
from fastapi.testclient import TestClient
import pytest

from app import app
from core.config import Settings, settings
from core.auth import authenticate_user, create_access_token


def test_runtime_defaults_have_no_password_accounts(monkeypatch):
    for name in ("PASSWORD_AUTH_ENABLED", "ADMIN_PASSWORD", "AUDITOR_PASSWORD", "ENABLE_DEFAULT_VIEWER", "ALLOW_SELF_SIGNUP"):
        monkeypatch.delenv(name, raising=False)
    config = Settings(_env_file=None)
    assert not config.PASSWORD_AUTH_ENABLED
    assert config.ADMIN_PASSWORD == config.AUDITOR_PASSWORD == ""
    assert not config.ENABLE_DEFAULT_VIEWER and not config.ALLOW_SELF_SIGNUP


def test_google_mode_rejects_password_endpoints_even_for_existing_users(monkeypatch, isolate_durable_store):
    monkeypatch.setattr(settings, "PASSWORD_AUTH_ENABLED", False)
    client = TestClient(app)
    account = {"role": "admin", "is_active": True, "password_hash": "preserved-existing-hash"}
    isolate_durable_store.create_account("retained-owner", account)
    payload = {"username": "retained-owner", "password": "test-password-placeholder"}
    assert client.post("/auth/login", json=payload).status_code == 403
    assert client.post("/auth/register", json=payload).status_code == 403
    assert client.post("/auth/token", data=payload).status_code == 403
    headers = {"Authorization": "Bearer " + create_access_token({"sub": "retained-owner", "auth_method": "google"})}
    assert client.post("/auth/invite", json=payload, headers=headers).status_code == 403
    assert authenticate_user("retained-owner", payload["password"]) is None
    assert isolate_durable_store.get("account", "retained-owner", "auth") == account


@pytest.mark.parametrize("method", [None, "password"])
def test_google_cutover_rejects_legacy_tokens_without_deleting_saved_data(method, monkeypatch, isolate_durable_store):
    monkeypatch.setattr(settings, "PASSWORD_AUTH_ENABLED", False)
    store = isolate_durable_store
    store.create_account("owner", {"role": "analyst", "is_active": True})
    store.put("project", "saved", "owner", {"id": "saved", "name": "Preserved"})
    claims = {"sub": "owner"}
    if method:
        claims["auth_method"] = method
    token = create_access_token(claims)
    response = TestClient(app).get("/auth/me", headers={"Authorization": "Bearer " + token})
    assert response.status_code == 401
    assert store.get("project", "saved", "owner")["name"] == "Preserved"


def test_google_login_and_refresh_preserve_owner_role_and_method(monkeypatch, isolate_durable_store):
    from core import neon_auth
    from core.auth import decode_access_token
    monkeypatch.setattr(settings, "PASSWORD_AUTH_ENABLED", False)
    store = isolate_durable_store
    store.create_account("existing-admin", {"role": "admin", "is_active": True, "provider": "neon",
        "neon_subject": "existing-subject", "neon_issuer": "https://provider.example"})
    store.put("project", "retained", "existing-admin", {"id": "retained"})
    monkeypatch.setattr(neon_auth, "verified_neon_identity", lambda token: (
        "https://provider.example", "existing-subject", {"email": "owner@example.com"}))
    client = TestClient(app)
    response = client.post("/auth/oauth-login", json={"id_token": "provider-token-placeholder"})
    assert response.status_code == 200
    data = response.json()
    assert data["user"]["username"] == "existing-admin" and data["user"]["role"] == "admin"
    assert decode_access_token(data["access_token"])["auth_method"] == "google"
    refresh = client.post("/auth/refresh", headers={"Authorization": "Bearer " + data["access_token"]})
    assert refresh.status_code == 200
    assert decode_access_token(refresh.json()["access_token"])["auth_method"] == "google"
    assert client.get("/auth/me", headers={"Authorization": "Bearer " + data["access_token"]}).status_code == 401
    assert store.get("project", "retained", "existing-admin") == {"id": "retained"}


def test_detailed_health_requires_authentication():
    response = TestClient(app).get("/health/detailed")
    assert response.status_code == 401
    assert TestClient(app).get("/health/ready").status_code == 200


def test_publication_config_rejects_password_auth_and_wildcard_origins():
    base = dict(_env_file=None, ENVIRONMENT="production", PASSWORD_AUTH_ENABLED=False,
        AUTH_REQUIRED=True, ENABLE_DEFAULT_VIEWER=False, ALLOW_SELF_SIGNUP=False,
        JWT_SECRET_KEY="unit-publication-signing-key-with-more-than-32-characters",
        GITHUB_WEBHOOK_SECRET="unit-publication-webhook-value", NEO4J_PASSWORD="unit-database-password",
        ALLOWED_ORIGINS=["https://app.example.com"], NEON_AUTH_URL="https://provider.example/neondb/auth",
        NEON_JWKS_URL="https://provider.example/neondb/auth/jwks")
    assert Settings(**base).published_deployment
    for overrides in ({"PASSWORD_AUTH_ENABLED": True}, {"ALLOWED_ORIGINS": ["*"]},
                      {"ALLOWED_ORIGINS": ["http://app.example.com"]}, {"NEON_JWKS_URL": "https://unrelated.example/jwks"},
                      {"SOCIAL_SIGNUP_ROLE": "admin"}):
        with pytest.raises(ValueError):
            Settings(**{**base, **overrides})


def test_render_origin_fallback_is_explicit_and_validated():
    base = dict(_env_file=None, ENVIRONMENT="production", PASSWORD_AUTH_ENABLED=False,
        AUTH_REQUIRED=True, ENABLE_DEFAULT_VIEWER=False, ALLOW_SELF_SIGNUP=False,
        JWT_SECRET_KEY="unit-publication-signing-key-with-more-than-32-characters",
        GITHUB_WEBHOOK_SECRET="unit-publication-webhook-value", NEO4J_PASSWORD="unit-database-password",
        ALLOWED_ORIGINS=[], NEON_AUTH_URL="https://provider.example/neondb/auth",
        NEON_JWKS_URL="https://provider.example/neondb/auth/jwks")
    assert Settings(**base, RENDER_EXTERNAL_URL="https://app.onrender.com").ALLOWED_ORIGINS == ["https://app.onrender.com"]
    for origin in ("", "http://app.onrender.com", "https://user:password@app.onrender.com", "https://app.onrender.com/path"):
        with pytest.raises(ValueError):
            Settings(**base, RENDER_EXTERNAL_URL=origin)


def test_security_headers_allow_google_oauth_popup_but_block_embedding(monkeypatch):
    monkeypatch.setattr(settings, "NEON_AUTH_URL", "https://provider.example/neondb/auth")
    response = TestClient(app).get("/health/")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["Cross-Origin-Opener-Policy"] == "same-origin-allow-popups"
    policy = response.headers["Content-Security-Policy"]
    assert "frame-ancestors 'none'" in policy and "object-src 'none'" in policy
    assert "connect-src 'self' https://provider.example" in policy
    assert "frame-src https://provider.example" in policy
    assert "unsafe-eval" not in policy


def test_static_frontend_keeps_api_priority_and_rejects_path_traversal(tmp_path, monkeypatch):
    import importlib
    import app as app_module
    frontend = tmp_path / "web"
    frontend.mkdir()
    (frontend / "index.html").write_text("<html><body>Static frontend fixture</body></html>")
    (frontend / "assets").mkdir()
    (frontend / "assets" / "app-test.js").write_text("console.log('fixture')")
    (tmp_path / "private.txt").write_text("private-file-placeholder")
    original = settings.STATIC_FRONTEND_DIR
    monkeypatch.setattr(settings, "STATIC_FRONTEND_DIR", str(frontend))
    try:
        reloaded = importlib.reload(app_module)
        client = TestClient(reloaded.app)
        response = client.get("/")
        assert response.status_code == 200 and "Static frontend fixture" in response.text
        assert response.headers["Cache-Control"] == "no-cache"
        assert client.get("/health/").json()["status"] == "healthy"
        assert client.get("/assets/app-test.js").status_code == 200
        escaped = client.get("/%2e%2e/private.txt")
        assert escaped.status_code == 404 and "private-file-placeholder" not in escaped.text
    finally:
        monkeypatch.setattr(settings, "STATIC_FRONTEND_DIR", original)
        importlib.reload(app_module)


def test_static_frontend_config_requires_a_built_index(tmp_path):
    with pytest.raises(ValueError, match="built frontend"):
        Settings(_env_file=None, STATIC_FRONTEND_DIR=str(tmp_path))


@pytest.mark.asyncio
async def test_unexpected_import_error_never_echoes_private_driver_details(monkeypatch):
    from api import registry
    from schemas.service import ImportRepoRequest
    async def fail(*args):
        raise RuntimeError("private-driver-credential-placeholder")
    monkeypatch.setattr(registry.onboarder, "import_from_repo", fail)
    with pytest.raises(HTTPException) as caught:
        await registry.import_repo(ImportRepoRequest(repo_url="https://github.com/example/repo"), current_user=None)
    assert caught.value.status_code == 500
    assert "private-driver" not in caught.value.detail


@pytest.mark.asyncio
@pytest.mark.parametrize("handler", ["analysis", "preview"])
async def test_analysis_handlers_hide_unexpected_driver_errors(handler, monkeypatch):
    from api import analysis
    def fail(*args, **kwargs):
        raise RuntimeError("private-driver-credential-placeholder")
    if handler == "analysis":
        monkeypatch.setattr(analysis, "_ensure_active_project_matches", fail)
        operation = analysis.analyze_impact(analysis.AnalysisRequest(), current_user=None)
    else:
        monkeypatch.setattr(analysis, "RemediationSimulator", fail)
        operation = analysis.preview_fix(analysis.PreviewFixRequest(edits=[]), current_user=None)
    with pytest.raises(HTTPException) as caught:
        await operation
    assert caught.value.status_code == 500
    assert "private-driver" not in caught.value.detail
