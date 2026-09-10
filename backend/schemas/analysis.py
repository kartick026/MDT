"""Analysis results schemas"""
from pydantic import BaseModel, Field
from typing import List, Optional, Union, Dict, Any
from enum import Enum


class SeverityLevel(str, Enum):
    """Risk severity levels"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class DiffFile(BaseModel):
    """Changed file information"""
    path: str
    change_type: str  # added, modified, deleted
    lines_changed: int = 0
    additions: int = 0
    deletions: int = 0


class DependencyInfo(BaseModel):
    """Service dependency information"""
    service: str
    dependency_type: str
    api_endpoints: List[str] = []


class SuggestedFix(BaseModel):
    """Structured suggested fix containing human explanation and simulated edits"""
    text: str
    edits: Optional[List[Dict[str, Any]]] = None


class ScoreBreakdown(BaseModel):
    """Component breakdown of calculated risk score"""
    file_count: int = 0
    impacted_services: int = 0
    confidence: int = 0
    connection_bugs: int = 0


class ImpactResult(BaseModel):
    """Impact analysis result from ImpactEngine"""
    risk_score: float  # 0-100
    severity: SeverityLevel
    impacted_services: List[str] = []
    confidence: float  # 0-1
    explanation: Optional[str] = None
    suggested_fixes: List[str] = []
    affected_files: List[DiffFile] = []
    dependency_chain: List[DependencyInfo] = []


class AnalysisResponse(BaseModel):
    """Complete API response for /analysis/analyze"""
    status: str = "success"
    commit: str
    commit_sha: str
    branch_ref: Optional[str] = None
    repo_url: str
    project_context: Dict[str, Any] = {}
    risk_score: float
    severity: str
    impacted_services: List[str] = []
    confidence: float
    explanation: Optional[str] = None
    suggested_fixes: List[Union[SuggestedFix, Dict[str, Any], str]] = []
    connection_bugs: List[Dict[str, Any]] = []
    affected_files: List[Dict[str, Any]] = []
    timestamp: str
    risk_level: str
    service: str
    downstream_services: List[str] = []
    score_breakdown: ScoreBreakdown


class HistoryEntry(BaseModel):
    """Individual entry in analysis history"""
    commit: Optional[str] = None
    commit_sha: Optional[str] = None
    branch_ref: Optional[str] = None
    repo_url: Optional[str] = None
    risk_score: float
    severity: Optional[str] = None
    risk_level: Optional[str] = None
    service: Optional[str] = None
    downstream_services: List[str] = []
    impacted_services: Optional[List[str]] = None
    explanation: Optional[str] = None
    affected_files: List[Dict[str, Any]] = []
    timestamp: str
    score_breakdown: Optional[Dict[str, Any]] = None


class HistoryResponse(BaseModel):
    """Response shape for /analysis/history"""
    analyses: List[Dict[str, Any]]
    total: int
    limit: int
    service_filter: Optional[str] = None
