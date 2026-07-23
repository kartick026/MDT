"""Analysis API routes"""
from fastapi import APIRouter, HTTPException
from typing import List, Optional
from pydantic import BaseModel

from schemas.analysis import ImpactResult, SeverityLevel
from services.impact_engine import ImpactEngine
from services.git_analyzer import GitAnalyzer

router = APIRouter()
engine = ImpactEngine()
git_analyzer = GitAnalyzer()


class AnalysisRequest(BaseModel):
    """Manual analysis request"""
    repo_url: str
    commit_sha: str
    changed_files: List[str]


@router.post("/analyze")
async def analyze_impact(request: AnalysisRequest):
    """
    Manually trigger impact analysis for a commit

    This endpoint allows testing the analysis pipeline without
    going through the GitHub webhook
    """
    try:
        changes = await git_analyzer.analyze_push(
            repo_url=request.repo_url,
            commit_sha=request.commit_sha,
            changed_files=request.changed_files
        )

        result = await engine.analyze_impact(changes)

        return {
            "status": "success",
            "commit": request.commit_sha,
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
            ]
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history")
async def get_analysis_history(
    limit: int = 10,
    service: Optional[str] = None
):
    """
    Get historical analysis results

    In production, this would query the database for past analyses
    """
    # Placeholder - would query database
    return {
        "analyses": [],
        "total": 0,
        "limit": limit,
        "service_filter": service
    }


@router.get("/severity-thresholds")
async def get_severity_thresholds():
    """Get the current severity thresholds"""
    return {
        "low": {"max": 25, "color": "green"},
        "medium": {"max": 50, "color": "yellow"},
        "high": {"max": 75, "color": "orange"},
        "critical": {"max": 100, "color": "red"}
    }