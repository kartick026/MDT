"""Analysis API routes — all data is live, nothing hardcoded."""
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException
from typing import List, Optional
from pydantic import BaseModel

logger = logging.getLogger(__name__)

from schemas.analysis import ImpactResult, SeverityLevel
from services.impact_engine import ImpactEngine
from services.git_analyzer import GitAnalyzer
from services.dependency_graph import DependencyGraph
from services.remediation_simulator import GraphEdit, RemediationSimulator
from core.registry import RegistryManager
from services.connection_validator import ConnectionValidator

router = APIRouter()
engine = ImpactEngine()
git_analyzer = GitAnalyzer()
graph = DependencyGraph()

# In-process history store — persists for the lifetime of the container.
# Entries are prepended so index 0 is always the most recent.
_analysis_history: List[dict] = []


class AnalysisRequest(BaseModel):
    """Manual analysis request"""
    repo_url: str
    commit_sha: str
    changed_files: Optional[List[str]] = None


@router.post("/analyze")
async def analyze_impact(request: AnalysisRequest):
    """
    Trigger impact analysis for a commit.
    If changed_files is omitted, automatically detects all files in the commit.
    Also validates inter-service connections to flag broken endpoints.
    """
    try:
        changes = await git_analyzer.analyze_push(
            repo_url=request.repo_url,
            commit_sha=request.commit_sha,
            changed_files=request.changed_files
        )

        result = await engine.analyze_impact(changes, commit_sha=request.commit_sha)

        # Validate connection integrity on changed files
        service_files = {}
        mappings = RegistryManager.get_file_mappings()
        for ch in changes:
            matched_svc = "unknown"
            for prefix, sname in mappings.items():
                if ch.file_path.startswith(prefix):
                    matched_svc = sname
                    break
            if matched_svc not in service_files:
                service_files[matched_svc] = {}
            service_files[matched_svc][ch.file_path] = ch.new_content or ch.old_content

        connection_bugs = ConnectionValidator.validate_topology(
            RegistryManager.get_services(), service_files
        )

        # Generate structured remediation with graph edits from smells
        try:
            from services.smell_detector import SmellDetector
            detector = SmellDetector()
            smells = await detector.detect_all_smells()
            structured_fixes = await engine.explainer.suggest_remediation_with_edits(
                smells=smells,
                impacted_services=result.impacted_services,
                changes=changes,
                risk_score=result.risk_score,
                connection_bugs=connection_bugs,
            )
            all_fixes = structured_fixes + result.suggested_fixes
        except Exception as exc:
            logger.warning("Failed to generate structured fixes with edits: %s", exc)
            all_fixes = result.suggested_fixes

        payload = {
            "status": "success",
            "commit": request.commit_sha,
            "repo_url": request.repo_url,
            "risk_score": result.risk_score,
            "severity": result.severity.value,
            "impacted_services": result.impacted_services,
            "confidence": result.confidence,
            "explanation": result.explanation,
            "suggested_fixes": all_fixes,
            "connection_bugs": [b.to_dict() for b in connection_bugs],
            "affected_files": [
                {
                    "path": f.path,
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
                "connection_bugs": len(connection_bugs),
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
    persisted = await graph.get_analysis_history(limit=limit, service=service)
    if persisted:
        results = [
            {
                "commit": item["commit"],
                "risk_score": item["risk_score"],
                "severity": item["severity"],
                "risk_level": (item["severity"] or "unknown").upper(),
                "service": item["services"][0] if item["services"] else "unknown",
                "downstream_services": item["services"],
                "affected_files": [
                    {"path": path, "change_type": "modified", "lines_changed": 0}
                    for path in item["changed_files"]
                ],
                "timestamp": item["timestamp"],
                "score_breakdown": {"file_count": len(item["changed_files"])},
            }
            for item in persisted
        ]
    else:
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


class PreviewFixRequest(BaseModel):
    """What-If remediation preview request."""
    edits: List[GraphEdit]


@router.post("/preview-fix")
async def preview_fix(request: PreviewFixRequest):
    """
    Simulate graph edits in a sandbox transaction and return
    before/after risk comparison.  The live graph is never modified.
    """
    try:
        simulator = RemediationSimulator()
        result = await simulator.simulate_fix(request.edits)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
