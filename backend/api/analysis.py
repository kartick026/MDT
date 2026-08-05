"""Analysis API routes — all data is live, nothing hardcoded."""
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException
from typing import List, Optional
from pydantic import BaseModel

from schemas.analysis import ImpactResult, SeverityLevel
from services.impact_engine import ImpactEngine
from services.git_analyzer import GitAnalyzer

router = APIRouter()
engine = ImpactEngine()
git_analyzer = GitAnalyzer()

# In-process history store — persists for the lifetime of the container.
# Entries are prepended so index 0 is always the most recent.
_analysis_history: List[dict] = []


class AnalysisRequest(BaseModel):
    """Manual analysis request"""
    repo_url: str
    commit_sha: str
    changed_files: List[str]


@router.post("/analyze")
async def analyze_impact(request: AnalysisRequest):
    """
    Trigger impact analysis for a commit.
    Stores the result in the in-process history so /history can return it.
    """
    try:
        changes = await git_analyzer.analyze_push(
            repo_url=request.repo_url,
            commit_sha=request.commit_sha,
            changed_files=request.changed_files
        )

        result = await engine.analyze_impact(changes)

        payload = {
            "status": "success",
            "commit": request.commit_sha,
            "repo_url": request.repo_url,
            "risk_score": result.risk_score,
            "severity": result.severity.value,
            "impacted_services": result.impacted_services,
            "confidence": result.confidence,
            "explanation": result.explanation,
            "suggested_fixes": result.suggested_fixes,
            "affected_files": [
                {
                    "path": f.file_path,
                    "change_type": f.change_type,
                    "lines_changed": f.lines_changed
                }
                for f in result.affected_files
            ],
            "timestamp": datetime.now(timezone.utc).isoformat(),
            # History fields (matches AnalysisHistory UI expectations)
            "risk_level": result.severity.value.upper(),
            "service": result.impacted_services[0] if result.impacted_services else "unknown",
            "downstream_services": result.impacted_services,
            "score_breakdown": {
                "file_count": len(result.affected_files),
                "impacted_services": len(result.impacted_services),
                "confidence": round(result.confidence * 100),
            }
        }

        # Prepend to history (most recent first), keep last 100
        _analysis_history.insert(0, payload)
        if len(_analysis_history) > 100:
            _analysis_history.pop()

        return payload

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history")
async def get_analysis_history(
    limit: int = 20,
    service: Optional[str] = None
):
    """Return historical analysis results from the in-process store."""
    results = _analysis_history
    if service:
        results = [r for r in results if r.get("service") == service]
    return {
        "analyses": results[:limit],
        "total": len(results),
        "limit": limit,
        "service_filter": service,
    }


@router.get("/severity-thresholds")
async def get_severity_thresholds():
    """Get the current severity thresholds."""
    return {
        "low":      {"max": 25,  "color": "green"},
        "medium":   {"max": 50,  "color": "yellow"},
        "high":     {"max": 75,  "color": "orange"},
        "critical": {"max": 100, "color": "red"},
    }