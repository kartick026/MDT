"""Analysis API routes — all data is live, strongly typed, and thread-safe."""
import asyncio
import logging
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field, field_validator

from schemas.analysis import (
    AnalysisResponse,
    HistoryResponse,
    ScoreBreakdown,
    DiffFile,
    ImpactResult,
    SeverityLevel,
)
from services.impact_engine import ImpactEngine
from services.git_analyzer import GitAnalyzer
from services.dependency_graph import DependencyGraph
from services.remediation_simulator import GraphEdit, RemediationSimulator
from core.registry import RegistryManager
from core.auth import get_current_user_optional, require_admin
from core.history import history_store
from schemas.auth import UserOut
from services.connection_validator import ConnectionValidator

logger = logging.getLogger(__name__)

router = APIRouter()

# Dependency getters
def get_impact_engine() -> ImpactEngine:
    return ImpactEngine()

def get_git_analyzer() -> GitAnalyzer:
    return GitAnalyzer()

def get_dependency_graph() -> DependencyGraph:
    return DependencyGraph()

engine = ImpactEngine()
git_analyzer = GitAnalyzer()
graph = DependencyGraph()

# Backward-compatible references to history store
_analysis_history = history_store._history
_history_lock = history_store._lock


def _ensure_active_project_matches(repo_url: str) -> Dict[str, Any]:
    """Prevent a repository from being analysed with another repo's topology."""
    active_context = RegistryManager.get_project_context()
    active_key = active_context.get("repository_key")
    requested_key = RegistryManager.repository_key(repo_url)
    if active_key and requested_key == active_key:
        return active_context

    active_repo = active_context.get("repo_url") or "an unassigned architecture"
    raise HTTPException(
        status_code=409,
        detail={
            "code": "ACTIVE_PROJECT_MISMATCH",
            "message": (
                "The active architecture belongs to a different repository. "
                "Import this repository from Overview before running impact analysis."
            ),
            "active_repository": active_repo,
            "requested_repository": repo_url,
        },
    )


class AnalysisRequest(BaseModel):
    """Manual analysis request. If repo_url or commit_sha is omitted, uses the active project context."""
    repo_url: Optional[str] = Field(None, description="Repository URL (defaults to active architecture if omitted)")
    commit_sha: Optional[str] = Field(None, description="Commit SHA or branch reference (defaults to imported branch if omitted)")
    changed_files: Optional[List[str]] = Field(None, description="Optional manual list of changed files")

    @field_validator("repo_url")
    @classmethod
    def validate_repo_url(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        cleaned = v.strip()
        return cleaned or None

    @field_validator("commit_sha")
    @classmethod
    def validate_commit_sha(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        cleaned = v.strip()
        return cleaned or None


@router.post("/analyze", response_model=AnalysisResponse, summary="Trigger impact analysis for a commit")
async def analyze_impact(
    request: AnalysisRequest,
    current_user: Optional[UserOut] = Depends(get_current_user_optional)
) -> AnalysisResponse:
    """
    Trigger impact analysis for a commit.
    If changed_files is omitted, automatically detects all files in the commit.
    Also validates inter-service connections to flag broken endpoints.
    """
    try:
        active_context = RegistryManager.get_project_context()
        target_repo = request.repo_url or active_context.get("repo_url") or "https://github.com/kartick026/MDT"
        target_ref = request.commit_sha or active_context.get("branch") or "main"

        # Validate before fetching a commit, querying retrieval, or consulting
        # the graph. This is the hard boundary that prevents repository B
        # from inheriting repository A's mappings, smells, and recommendations.
        active_context = _ensure_active_project_matches(target_repo)

        # Resolve branch ref to exact commit SHA if needed
        resolved_sha = await git_analyzer.resolve_commit_sha(
            repo_url=target_repo,
            ref=target_ref
        )
        effective_commit_sha = resolved_sha or target_ref

        changes = await git_analyzer.analyze_push(
            repo_url=target_repo,
            commit_sha=effective_commit_sha,
            changed_files=request.changed_files
        )

        result = await engine.analyze_impact(changes, commit_sha=effective_commit_sha)

        # Validate connection integrity on changed files
        service_files = {}
        mappings = RegistryManager.get_file_mappings()
        for ch in changes:
            matched_svc = "unknown"
            for prefix, sname in sorted(mappings.items(), key=lambda x: len(x[0]), reverse=True):
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
            if structured_fixes:
                all_fixes = structured_fixes
            else:
                all_fixes = result.suggested_fixes
        except Exception as exc:
            logger.warning("Failed to generate structured fixes with edits: %s", exc)
            all_fixes = result.suggested_fixes

        is_sha = len(effective_commit_sha) == 40 and all(c in "0123456789abcdefABCDEF" for c in effective_commit_sha)
        display_commit = effective_commit_sha[:7] if is_sha else effective_commit_sha
        branch_ref = target_ref if target_ref != effective_commit_sha else (active_context.get("branch") or "main")
        sev_str = result.severity.value if hasattr(result.severity, "value") else str(result.severity)

        score_breakdown = ScoreBreakdown(
            file_count=len(result.affected_files),
            impacted_services=len(result.impacted_services),
            confidence=round(result.confidence * 100),
            connection_bugs=len(connection_bugs),
        )

        payload_dict = {
            "status": "success",
            "commit": display_commit,
            "commit_sha": effective_commit_sha,
            "branch_ref": branch_ref,
            "repo_url": target_repo,
            "project_context": active_context,
            "risk_score": result.risk_score,
            "severity": sev_str,
            "impacted_services": result.impacted_services,
            "confidence": result.confidence,
            "explanation": result.explanation,
            "suggested_fixes": all_fixes,
            "connection_bugs": [b.to_dict() for b in connection_bugs],
            "affected_files": [
                {
                    "path": f.path,
                    "change_type": f.change_type,
                    "lines_changed": f.lines_changed,
                    "additions": getattr(f, "additions", 0),
                    "deletions": getattr(f, "deletions", 0),
                }
                for f in result.affected_files
            ],
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "risk_level": sev_str.upper(),
            "service": result.impacted_services[0] if result.impacted_services else "unknown",
            "downstream_services": result.impacted_services,
            "score_breakdown": score_breakdown,
        }

        # Thread-safe insert into history
        await history_store.add(payload_dict)

        return AnalysisResponse(**payload_dict)

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Analysis failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history", response_model=HistoryResponse, summary="Return historical analysis results")
async def get_analysis_history(
    limit: int = Query(default=20, ge=1, le=200),
    service: Optional[str] = None
) -> HistoryResponse:
    """Return historical analysis results from the in-process store or Neo4j."""
    persisted = await graph.get_analysis_history(limit=limit, service=service)
    ctx = RegistryManager.get_project_context()
    if persisted:
        results = []
        for item in persisted:
            score = item.get("risk_score") or 0.0
            sev = (item.get("severity") or "LOW").upper()
            if score >= 75:
                sev = "CRITICAL"
            elif score >= 50:
                sev = "HIGH"
            elif score >= 25:
                sev = "MEDIUM"
            else:
                sev = "LOW"

            results.append({
                "commit": item["commit"][:7] if (item.get("commit") and len(item["commit"]) == 40) else item["commit"],
                "commit_sha": item["commit"],
                "repo_url": item.get("repo_url") or ctx.get("repo_url"),
                "branch_ref": item.get("branch_ref") or ctx.get("branch"),
                "risk_score": score,
                "severity": sev,
                "risk_level": sev,
                "service": item["services"][0] if item["services"] else "unknown",
                "downstream_services": item["services"],
                "affected_files": [
                    {"path": path, "change_type": "modified", "lines_changed": 0}
                    for path in item["changed_files"]
                ],
                "timestamp": item["timestamp"],
                "score_breakdown": {"file_count": len(item["changed_files"])},
            })
    else:
        results = await history_store.get_all(service=service)

    return HistoryResponse(
        analyses=results[:limit],
        total=len(results),
        limit=limit,
        service_filter=service,
    )


@router.get("/severity-thresholds", summary="Get current risk score severity thresholds")
async def get_severity_thresholds() -> Dict[str, Dict[str, Any]]:
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
    baseline_risk_score: Optional[float] = None


@router.post("/preview-fix", summary="Simulate graph edits in a sandbox transaction")
async def preview_fix(
    request: PreviewFixRequest,
    current_user: UserOut = Depends(require_admin),
) -> Dict[str, Any]:
    """
    Simulate graph edits in a sandbox transaction and return
    before/after risk comparison. The live graph is never modified.
    """
    try:
        simulator = RemediationSimulator()
        result = await simulator.simulate_fix(
            request.edits,
            baseline_risk_score=request.baseline_risk_score,
        )
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Preview fix simulation failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
