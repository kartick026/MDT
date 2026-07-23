"""GitHub webhook endpoints"""
from fastapi import APIRouter, Request, HTTPException, Header
import hmac
import hashlib
import logging
from typing import Optional

from schemas.webhook import WebhookPayload, PushEvent
from services.git_analyzer import GitAnalyzer
from services.impact_engine import ImpactEngine
from core.config import settings

router = APIRouter()
logger = logging.getLogger(__name__)


def verify_github_signature(payload: bytes, signature: str, secret: str) -> bool:
    """Verify GitHub webhook signature"""
    if not signature:
        return False

    mac = hmac.new(
        secret.encode('utf-8'),
        payload,
        hashlib.sha256
    )
    expected_signature = f"sha256={mac.hexdigest()}"

    return hmac.compare_digest(expected_signature, signature)


@router.post("/github")
async def github_webhook(
    request: Request,
    payload: WebhookPayload,
    x_hub_signature_256: Optional[str] = Header(None),
    x_github_event: str = Header("push")
):
    """
    Receive GitHub webhook events

    Events handled:
    - push: Trigger analysis on code push
    """
    # Get raw body for signature verification
    body = await request.body()

    # Verify signature (skip in debug mode)
    if not settings.DEBUG:
        if not verify_github_signature(body, x_hub_signature_256, settings.GITHUB_WEBHOOK_SECRET):
            raise HTTPException(status_code=401, detail="Invalid signature")

    logger.info(f"Received GitHub webhook: event={x_github_event}")

    if x_github_event == "push":
        # Process push event
        push_data = PushEvent(**payload.data)

        # Run analysis
        analyzer = GitAnalyzer()
        diff_result = await analyzer.analyze_push(
            repo_url=push_data.repo_url,
            commit_sha=push_data.commit_sha,
            changed_files=push_data.changed_files
        )

        # Calculate impact
        engine = ImpactEngine()
        impact_result = await engine.analyze_impact(diff_result)

        return {
            "status": "analyzed",
            "commit": push_data.commit_sha,
            "risk_score": impact_result.risk_score,
            "severity": impact_result.severity,
            "impacted_services": impact_result.impacted_services
        }

    return {"status": "event_not_processed", "event": x_github_event}


@router.post("/test")
async def test_webhook():
    """Test endpoint for webhook configuration"""
    return {
        "status": "ok",
        "message": "Webhook endpoint is configured correctly"
    }