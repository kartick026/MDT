"""Analysis results schemas"""
from pydantic import BaseModel
from typing import List, Optional
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
    lines_changed: int
    additions: int
    deletions: int


class DependencyInfo(BaseModel):
    """Service dependency information"""
    service: str
    dependency_type: str
    api_endpoints: List[str]


class ImpactResult(BaseModel):
    """Impact analysis result"""
    risk_score: float  # 0-100
    severity: SeverityLevel
    impacted_services: List[str]
    confidence: float  # 0-1
    explanation: Optional[str] = None
    suggested_fixes: List[str] = []
    affected_files: List[DiffFile] = []
    dependency_chain: List[DependencyInfo] = []