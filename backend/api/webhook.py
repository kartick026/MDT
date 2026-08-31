"""
GitHub Webhook API
Receives and processes GitHub push events, triggering the MDT analysis pipeline.

Supported events:
  - push  → full GitAnalyzer → ImpactEngine pipeline
  - ping  → acknowledge and return hook info (sent by GitHub on webhook setup)

Signature verification:
  GitHub signs every payload with HMAC-SHA256 using the webhook secret.
  The signature is in the X-Hub-Signature-256 header as "sha256=<hex>".
  Verification is skipped when DEBUG=True to ease local development.

Body-read ordering:
  FastAPI body parsing and request.body() compete for the same stream.
  We solve this by accepting the raw body ourselves (body: bytes = Body(...))
  and manually deserialising, so the stream is only consumed once.
"""
import hmac
import hashlib
import json
import logging
from typing import Optional

from fastapi import APIRouter, Request, HTTPException, Header, Body
from pydantic import ValidationError

from schemas.webhook import GitHubPushPayload, GitHubPingPayload
from services.git_analyzer import GitAnalyzer, ChangeInfo
from services.impact_engine import ImpactEngine
from core.config import settings

router = APIRouter()
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _verify_signature(payload: bytes, signature: Optional[str], secret: str) -> bool:
    """
    Verify GitHub's HMAC-SHA256 webhook signature.

    Returns True when the computed digest matches the provided header value.
    Returns False if the signature header is missing or the digest does not match.
    """
    if not signature:
        return False
    if not signature.startswith("sha256="):
        return False

    mac = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256)
    expected = f"sha256={mac.hexdigest()}"
    return hmac.compare_digest(expected, signature)


def _extract_change_infos(push: GitHubPushPayload) -> list[ChangeInfo]:
    """
    Build ChangeInfo objects from the push payload's commit list.
    Each file is only returned once; the last change_type seen wins.
    """
    from dataclasses import replace

    changed = push.all_changed_files()
    result: list[ChangeInfo] = []
    for entry in changed:
        result.append(
            ChangeInfo(
                file_path=entry["path"],
                change_type=entry["change_type"],
                diff_content="",   # filled in by GitAnalyzer when repo is accessible
                additions=0,
                deletions=0,
                old_content="",
                new_content="",
            )
        )
    return result


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

from fastapi import BackgroundTasks

async def _process_push_background(push, x_github_delivery):
    try:
        branch = push.branch
        commit_sha = push.commit_sha
        repo_url = push.repo_url

        logger.info(
            "Processing push (Background) | repo=%s | branch=%s | commit=%s | commits=%d",
            repo_url, branch, commit_sha, len(push.commits)
        )

        change_infos = _extract_change_infos(push)
        if not change_infos:
            logger.info("Push event has no analysable file changes, skipping analysis")
            return

        # Enrich with actual diffs via GitAnalyzer
        analyzer = GitAnalyzer()
        enriched_changes = await analyzer.analyze_push(
            repo_url=repo_url,
            commit_sha=commit_sha,
            changed_files=[c.file_path for c in change_infos],
        )

        # Merge change_type from payload into enriched results
        change_type_map = {c.file_path: c.change_type for c in change_infos}
        for change in enriched_changes:
            if change.file_path in change_type_map:
                change.change_type = change_type_map[change.file_path]

        # Run HMDA impact analysis
        engine = ImpactEngine()
        impact_result = await engine.analyze_impact(
            enriched_changes, commit_sha=commit_sha
        )

        # Prepend to in-memory history (so /history works if no Neo4j)
        from api.analysis import _analysis_history
        from datetime import datetime, timezone
        payload = {
            "status": "success",
            "commit": commit_sha,
            "repo_url": repo_url,
            "risk_score": impact_result.risk_score,
            "severity": impact_result.severity.value if hasattr(impact_result.severity, 'value') else impact_result.severity,
            "impacted_services": impact_result.impacted_services,
            "confidence": impact_result.confidence,
            "explanation": impact_result.explanation,
            "suggested_fixes": impact_result.suggested_fixes,
            "affected_files": [
                {
                    "path": f.path,
                    "change_type": f.change_type,
                    "lines_changed": f.lines_changed
                }
                for f in impact_result.affected_files
            ],
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "risk_level": str(impact_result.severity).upper(),
            "service": impact_result.impacted_services[0] if impact_result.impacted_services else "unknown",
            "downstream_services": impact_result.impacted_services,
            "score_breakdown": {
                "file_count": len(impact_result.affected_files),
                "impacted_services": len(impact_result.impacted_services),
                "confidence": round(impact_result.confidence * 100),
            }
        }
        _analysis_history.insert(0, payload)
        if len(_analysis_history) > 100:
            _analysis_history.pop()

        logger.info(
            "Background Analysis complete | commit=%s | risk=%.1f | severity=%s | services=%s",
            commit_sha,
            impact_result.risk_score,
            impact_result.severity,
            impact_result.impacted_services,
        )
    except Exception as exc:
        logger.error("Background analysis failed: %s", exc)


@router.post("/github", summary="Receive GitHub webhook events")
async def github_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_hub_signature_256: Optional[str] = Header(None, alias="X-Hub-Signature-256"),
    x_github_event: Optional[str] = Header(None, alias="X-GitHub-Event"),
    x_github_delivery: Optional[str] = Header(None, alias="X-GitHub-Delivery"),
):
    """
    Main GitHub webhook endpoint.

    GitHub delivers all events here. MDT processes:
      - **push**  — triggers the full impact analysis pipeline in the background
      - **ping**  — returned on initial webhook registration; always 200 OK
    """
    body = await request.body()

    logger.info(
        "GitHub webhook received | event=%s | delivery=%s | size=%d bytes",
        x_github_event,
        x_github_delivery,
        len(body),
    )

    if not settings.DEBUG:
        if not _verify_signature(body, x_hub_signature_256, settings.GITHUB_WEBHOOK_SECRET):
            logger.warning("Webhook signature verification failed")
            raise HTTPException(status_code=401, detail="Invalid webhook signature")
    else:
        logger.debug("DEBUG mode: skipping signature verification")

    try:
        payload_dict = json.loads(body)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    event = (x_github_event or "").lower()

    if event == "ping":
        try:
            ping = GitHubPingPayload(**payload_dict)
        except ValidationError:
            ping = GitHubPingPayload()
        return {
            "status": "pong",
            "message": "Webhook configured successfully",
            "hook_id": ping.hook_id,
            "zen": ping.zen,
        }

    if event == "push":
        try:
            push = GitHubPushPayload(**payload_dict)
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=f"Invalid push payload: {exc}")

        # Dispatch the actual heavy lifting to a background task
        background_tasks.add_task(_process_push_background, push, x_github_delivery)
        
        return {
            "status": "accepted",
            "message": "Push event received and queued for background processing",
            "delivery_id": x_github_delivery,
            "repo": push.repo_url,
            "commit": push.commit_sha
        }

    # --- unhandled event type ---
    logger.debug("Unhandled GitHub event type: %s", event)
    return {
        "status": "event_not_processed",
        "event": event,
        "delivery_id": x_github_delivery,
    }


@router.post("/test", summary="Test webhook connectivity")
async def test_webhook():
    """
    Confirm the webhook endpoint is reachable.
    Safe to call from GitHub's 'Redeliver' UI or from curl.
    """
    return {
        "status": "ok",
        "message": "Webhook endpoint is reachable and configured correctly",
        "debug_mode": settings.DEBUG,
        "signature_verification": not settings.DEBUG,
    }


@router.post("/simulate", summary="Simulate a GitHub push event (dev only)")
async def simulate_push(
    repo_url: str = Body(..., embed=True),
    branch: str = Body("main", embed=True),
    commit_sha: str = Body("abc123def456", embed=True),
    changed_files: list[str] = Body(
        default=["services/payment_service/main.py"],
        embed=True,
    ),
    commit_message: str = Body("chore: update payment endpoint", embed=True),
    author: str = Body("dev", embed=True),
):
    """
    Simulate a push event without needing a real GitHub webhook.
    Only available in all environments for demo/testing purposes.

    Builds a synthetic GitHubPushPayload, then runs the full pipeline.
    """
    logger.info("Simulating push event | repo=%s | files=%s", repo_url, changed_files)

    analyzer = GitAnalyzer()
    changes = await analyzer.analyze_push(
        repo_url=repo_url,
        commit_sha=commit_sha,
        changed_files=changed_files,
    )

    engine = ImpactEngine()
    impact_result = await engine.analyze_impact(changes, commit_sha=commit_sha)

    return {
        "status": "simulated",
        "repo": repo_url,
        "branch": branch,
        "commit": commit_sha,
        "commit_message": commit_message,
        "author": author,
        "files_analysed": len(changes),
        "risk_score": impact_result.risk_score,
        "severity": impact_result.severity,
        "impacted_services": impact_result.impacted_services,
        "confidence": impact_result.confidence,
        "explanation": impact_result.explanation,
        "suggested_fixes": impact_result.suggested_fixes,
        "affected_files": [
            {
                "path": f.path,
                "change_type": f.change_type,
                "lines_changed": f.lines_changed,
            }
            for f in impact_result.affected_files
        ],
    }
