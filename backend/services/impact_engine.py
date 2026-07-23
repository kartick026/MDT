"""
HMDA - Hybrid Microservice Drift Algorithm
Deterministic + AI-assisted risk scoring engine
"""
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
import asyncio

from schemas.analysis import ImpactResult, SeverityLevel, DiffFile, DependencyInfo
from services.dependency_graph import DependencyGraph
from services.retrieval import RetrievalEngine
from services.llm_explainer import LLMExplainer
from core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class RiskFactors:
    """Risk factors for scoring"""
    file_count: int
    core_service_impact: bool
    api_changes: bool
    dependency_depth: int
    semantic_risk: float


class ImpactEngine:
    """
    HMDA - Hybrid Microservice Drift Algorithm

    Combines:
    - Deterministic risk scoring (file count, change type, dependency depth)
    - Semantic risk assessment (ChromaDB retrieval)
    - AI-assisted reasoning (LLM explanation)
    """

    def __init__(self):
        self.dep_graph = DependencyGraph()
        self.retrieval = RetrievalEngine()
        self.explainer = LLMExplainer()
        self._thresholds = {
            "low": settings.RISK_LOW,
            "medium": settings.RISK_MEDIUM,
            "high": settings.RISK_HIGH
        }

    async def analyze_impact(self, changes: List) -> ImpactResult:
        """
        Main entry point for impact analysis

        Args:
            changes: List of ChangeInfo from GitAnalyzer

        Returns:
            ImpactResult with risk score, severity, impacted services, etc.
        """
        logger.info(f"Analyzing impact for {len(changes)} file changes")

        # Step 1: Calculate deterministic risk
        risk_factors = self._calculate_deterministic_risk(changes)

        # Step 2: Get impacted services from dependency graph
        impacted_services = await self._get_impacted_services(changes)

        # Step 3: Retrieve relevant context from ChromaDB
        retrieved_context = await self._retrieve_context(changes)

        # Step 4: Calculate base risk score
        base_risk = self._compute_base_risk(risk_factors)

        # Step 5: Apply semantic boost
        semantic_boost = retrieved_context.get("risk_modifier", 0)
        final_risk = min(100, base_risk + semantic_boost)

        # Step 6: Determine severity
        severity = self._get_severity(final_risk)

        # Step 7: Generate explanation
        explanation = await self._generate_explanation(
            changes, impacted_services, final_risk, retrieved_context
        )

        # Step 8: Suggest fixes
        suggested_fixes = await self._suggest_fixes(impacted_services, changes)

        return ImpactResult(
            risk_score=final_risk,
            severity=severity,
            impacted_services=impacted_services,
            confidence=0.85,  # Placeholder confidence
            explanation=explanation,
            suggested_fixes=suggested_fixes,
            affected_files=[DiffFile(
                path=c.file_path if hasattr(c, 'file_path') else str(c),
                change_type=getattr(c, 'change_type', 'modified'),
                lines_changed=getattr(c, 'additions', 0) + getattr(c, 'deletions', 0),
                additions=getattr(c, 'additions', 0),
                deletions=getattr(c, 'deletions', 0)
            ) for c in changes],
            dependency_chain=[]
        )

    def _calculate_deterministic_risk(self, changes: List) -> RiskFactors:
        """Calculate risk based on deterministic factors"""
        return RiskFactors(
            file_count=len(changes),
            core_service_impact=False,  # Would check against known core files
            api_changes=self._has_api_changes(changes),
            dependency_depth=2,  # Default depth
            semantic_risk=0.0
        )

    def _has_api_changes(self, changes: List) -> bool:
        """Check if any changes are API-related files"""
        api_patterns = ['api', 'route', 'endpoint', 'controller', 'handler']
        for change in changes:
            file_path = getattr(change, 'file_path', str(change)).lower()
            if any(pattern in file_path for pattern in api_patterns):
                return True
        return False

    async def _get_impacted_services(self, changes: List) -> List[str]:
        """Query dependency graph for impacted services"""
        services = []
        for change in changes:
            file_path = getattr(change, 'file_path', str(change))
            impacted = await self.dep_graph.get_affected_services(file_path)
            services.extend(impacted)
        return list(set(services))  # Deduplicate

    async def _retrieve_context(self, changes: List) -> Dict[str, Any]:
        """Retrieve relevant context from vector database"""
        return await self.retrieval.retrieve_similar(changes)

    def _compute_base_risk(self, factors: RiskFactors) -> float:
        """Compute base risk score from deterministic factors"""
        score = 0.0

        # File count factor (up to 30 points)
        score += min(30, factors.file_count * 5)

        # API changes (adds 25 points)
        if factors.api_changes:
            score += 25

        # Core service impact (adds 30 points)
        if factors.core_service_impact:
            score += 30

        # Dependency depth (up to 15 points)
        score += min(15, factors.dependency_depth * 5)

        return min(100, score)

    def _get_severity(self, risk_score: float) -> SeverityLevel:
        """Map risk score to severity level"""
        if risk_score >= self._thresholds["high"]:
            return SeverityLevel.CRITICAL
        elif risk_score >= self._thresholds["medium"]:
            return SeverityLevel.HIGH
        elif risk_score >= self._thresholds["low"]:
            return SeverityLevel.MEDIUM
        else:
            return SeverityLevel.LOW

    async def _generate_explanation(
        self,
        changes: List,
        impacted_services: List[str],
        risk_score: float,
        retrieved_context: Dict
    ) -> str:
        """Generate human-readable explanation using LLM"""
        return await self.explainer.explain(
            changes=changes,
            impacted_services=impacted_services,
            risk_score=risk_score,
            context=retrieved_context
        )

    async def _suggest_fixes(
        self,
        impacted_services: List[str],
        changes: List
    ) -> List[str]:
        """Suggest remediation actions"""
        fixes = []

        if impacted_services:
            fixes.append(
                f"Review changes in services: {', '.join(impacted_services)}"
            )

        if self._has_api_changes(changes):
            fixes.append("Update API documentation for affected endpoints")
            fixes.append("Notify downstream service owners of API changes")

        fixes.append("Run integration tests for affected services")

        return fixes[:5]  # Limit to top 5 suggestions