"""
Tests for GitHub Webhook Security & Rate Limiting (Phase 1)
"""
import hmac
import hashlib
import json
import pytest
from fastapi.testclient import TestClient
from app import app
from core.config import settings
import api.webhook as webhook_module


@pytest.fixture
def client():
    return TestClient(app)


def compute_signature(payload: bytes, secret: str) -> str:
    mac = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256)
    return f"sha256={mac.hexdigest()}"


def test_webhook_ping_with_valid_signature(client):
    secret = settings.GITHUB_WEBHOOK_SECRET
    body = json.dumps({"zen": "Keep it logically awesome."}).encode("utf-8")
    sig = compute_signature(body, secret)

    headers = {
        "X-GitHub-Event": "ping",
        "X-GitHub-Delivery": "test-delivery-123",
        "X-Hub-Signature-256": sig,
        "Content-Type": "application/json",
    }
    response = client.post("/webhook/github", content=body, headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "pong"
    assert data["zen"] == "Keep it logically awesome."


def test_webhook_invalid_signature_rejected(client):
    body = json.dumps({"zen": "Test"}).encode("utf-8")
    headers = {
        "X-GitHub-Event": "ping",
        "X-Hub-Signature-256": "sha256=badbadbadbadbadbadbadbadbadbadbadbadbadbadbadbadbadbadbadbadbadb",
        "Content-Type": "application/json",
    }
    # Ensure signature verification is active
    original_req = settings.WEBHOOK_SIGNATURE_REQUIRED
    settings.WEBHOOK_SIGNATURE_REQUIRED = True
    try:
        response = client.post("/webhook/github", content=body, headers=headers)
        assert response.status_code == 401
        assert "Invalid webhook signature" in response.json()["detail"]
    finally:
        settings.WEBHOOK_SIGNATURE_REQUIRED = original_req


def test_webhook_rate_limiting_enforced(client):
    body = json.dumps({"zen": "Test"}).encode("utf-8")
    sig = compute_signature(body, settings.GITHUB_WEBHOOK_SECRET)
    headers = {
        "X-GitHub-Event": "ping",
        "X-Hub-Signature-256": sig,
        "Content-Type": "application/json",
    }

    # Temporarily lower limit to test sliding window rate limit
    original_limit = settings.RATE_LIMIT_WEBHOOK_PER_MINUTE
    settings.RATE_LIMIT_WEBHOOK_PER_MINUTE = 3
    webhook_module._rate_limit_records.clear()
    try:
        # First 3 requests succeed
        for _ in range(3):
            res = client.post("/webhook/github", content=body, headers=headers)
            assert res.status_code == 200

        # 4th request must fail with 429
        res = client.post("/webhook/github", content=body, headers=headers)
        assert res.status_code == 429
        assert "Too many webhook requests" in res.json()["detail"]
    finally:
        settings.RATE_LIMIT_WEBHOOK_PER_MINUTE = original_limit
        webhook_module._rate_limit_records.clear()


def test_webhook_test_endpoint(client):
    response = client.post("/webhook/test")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "signature_verification" in data
    assert "rate_limit_per_minute" in data
