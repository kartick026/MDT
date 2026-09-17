"""

HMDA - Hierarchical Microservice Drift Analysis

Deterministic + AI-assisted risk scoring engine

"""

import logging
import statistics
from collections import defaultdict
from typing import List, Dict, Any, Optional, Set
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

    schema_changes: bool = False

    config_changes: bool = False







class ImpactEngine:

    """

    HMDA - Hierarchical Microservice Drift Analysis



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



    async def analyze_impact(

        self, changes: List, commit_sha: Optional[str] = None

    ) -> ImpactResult:

        """

        Main entry point for impact analysis



        Args:

            changes: List of ChangeInfo from GitAnalyzer



        Returns:

            ImpactResult with risk score, severity, impacted services, etc.

        """

        logger.info(f"Analyzing impact for {len(changes)} file changes")



        # Step 1: Calculate deterministic risk (partial — depth filled in step 2)

        risk_factors = self._calculate_deterministic_risk(changes)



        # Step 2: Get impacted services + real dependency depth from graph

        impacted_services, max_depth = await self._get_impacted_services_with_depth(changes)

        risk_factors.dependency_depth = max_depth



        # Step 3: Retrieve relevant context from ChromaDB

        retrieved_context = await self._retrieve_context(changes)



        # Step 4: Calculate base risk score

        base_risk = self._compute_base_risk(risk_factors)



        # Step 5: Apply semantic boost

        semantic_boost = retrieved_context.get("risk_modifier", 0)

        final_risk = max(0.0, min(100.0, round(float(base_risk + semantic_boost), 1)))



        # Step 6: Determine severity

        severity = self._get_severity(final_risk)



        # Step 7: Generate explanation

        explanation = await self._generate_explanation(

            changes, impacted_services, final_risk, retrieved_context

        )



        # Step 8: Suggest fixes

        suggested_fixes = await self._suggest_fixes(impacted_services, changes)



        # Step 9: Confidence based on how much data we had

        confidence = self._compute_confidence(impacted_services, max_depth)



        # Step 10: Record analysis in graph for history

        if impacted_services:

            changed_files = [getattr(c, 'file_path', str(c)) for c in changes]

            await self._record_to_graph(

                impacted_services, changes, final_risk, severity,

                changed_files, commit_sha,

            )



        # Step 11: Index changed files into ChromaDB for future retrieval

        await self._index_changes(changes, final_risk)



        return ImpactResult(

            risk_score=round(final_risk, 1),

            severity=severity,

            impacted_services=impacted_services,

            confidence=confidence,

            explanation=explanation,

            suggested_fixes=suggested_fixes,

            affected_files=[DiffFile(

                path=c.file_path if hasattr(c, 'file_path') else str(c),

                change_type=getattr(c, 'change_type', 'modified'),

                lines_changed=getattr(c, 'lines_changed',

                               getattr(c, 'additions', 0) + getattr(c, 'deletions', 0)),

                additions=getattr(c, 'additions', 0),

                deletions=getattr(c, 'deletions', 0)

            ) for c in changes],

            dependency_chain=[]

        )



    def _calculate_deterministic_risk(self, changes: List) -> RiskFactors:

        """Calculate risk based on deterministic factors"""

        return RiskFactors(

            file_count=len(changes),

            core_service_impact=self._has_core_service_impact(changes),

            api_changes=self._has_api_changes(changes),

            dependency_depth=2,  # updated later by _get_real_depth()

            semantic_risk=0.0,

            schema_changes=self._has_schema_changes(changes),

            config_changes=self._has_config_changes(changes),

        )



    def _get_core_services(self) -> Set[str]:
        """
        Dynamically determine core architectural services based on in-degree centrality.
        A service is 'core' when other services genuinely depend on it heavily.
        Threshold is defined as mean + 1 standard deviation of in-degrees when variance
        is significant (std >= 1.0), falling back to round(mean) for small fleets with
        sub-integer variance, with a minimum in-degree of 2.
        """
        try:
            from core.registry import RegistryManager
            deps = RegistryManager.get_dependencies()
            in_degree = defaultdict(int)
            for d in deps:
                to_svc = d.get("to", "")
                from_svc = d.get("from", "")
                if to_svc and from_svc and to_svc != from_svc:
                    in_degree[to_svc] += 1
            if not in_degree:
                return set()

            degrees = list(in_degree.values())
            mean = statistics.mean(degrees)
            std = statistics.pstdev(degrees)
            # When standard deviation is >= 1.0 (typical in larger enterprise graphs),
            # strictly isolate top-tier hubs via mean + std. For small fleets with sub-integer
            # variance (std < 1.0), use round(mean) to avoid over-filtering primary orchestrators.
            target = mean + std if std >= 1.0 else mean
            threshold = max(2, round(target))
            core = {svc for svc, deg in in_degree.items() if deg >= threshold}
            if not core:
                core = {svc for svc, deg in in_degree.items() if deg >= 2}
            return core
        except Exception as exc:
            logger.debug("Failed to calculate core services from graph: %s", exc)
            return set()

    def _has_core_service_impact(self, changes: List) -> bool:
        """Check if any changed file belongs to a dynamically computed core service."""
        core_services = self._get_core_services()
        if not core_services:
            return False

        core_patterns = set()
        for svc in core_services:
            clean = svc.lower().strip()
            core_patterns.add(clean)
            core_patterns.add(clean.replace("-", "_"))
            core_patterns.add(clean.replace("_", "-"))

        for change in changes:
            fp = getattr(change, 'file_path', str(change)).lower().replace("\\", "/")
            if any(p in fp for p in core_patterns):
                return True
        return False



    def _has_api_changes(self, changes: List) -> bool:

        """Check if any changes are API-related files"""

        api_patterns = ['api', 'route', 'endpoint', 'controller', 'handler']

        for change in changes:

            file_path = getattr(change, 'file_path', str(change)).lower()

            if any(pattern in file_path for pattern in api_patterns):

                return True

        return False



    def _has_schema_changes(self, changes: List) -> bool:

        """Check if any changes contain database schema, migration, or DDL definitions"""

        schema_patterns = ['migration', '.sql', 'schema', 'alembic', 'flyway', 'prisma', 'db/migrate']

        for change in changes:

            file_path = getattr(change, 'file_path', str(change)).lower().replace("\\", "/")

            if any(pattern in file_path for pattern in schema_patterns):

                return True

        return False



    def _has_config_changes(self, changes: List) -> bool:

        """Check if changes touch deployment or infrastructure configuration"""

        config_patterns = [

            'docker-compose', '.env', 'helm', 'k8s', 'kubernetes', 'terraform',

            'settings.py', 'config.py', 'application.yml', 'application.yaml', 'values.yaml'

        ]

        for change in changes:

            file_path = getattr(change, 'file_path', str(change)).lower().replace("\\", "/")

            if any(pattern in file_path for pattern in config_patterns):

                return True

        return False





    async def _get_impacted_services_with_depth(

        self, changes: List

    ) -> tuple[List[str], int]:

        """

        Query dependency graph for impacted services AND the max dependency

        depth across all changed files.

        Returns (services_list, max_depth).

        """

        services: set = set()

        max_depth = 0



        for change in changes:

            file_path = getattr(change, 'file_path', str(change))

            impacted = await self.dep_graph.get_affected_services(file_path)

            services.update(impacted)



            # Get depth for each impacted service

            for svc in impacted:

                depth = await self.dep_graph.get_dependency_depth(svc)

                max_depth = max(max_depth, depth)



        return list(services), max_depth



    async def _get_impacted_services(self, changes: List) -> List[str]:

        """Legacy wrapper — used by tests."""

        services, _ = await self._get_impacted_services_with_depth(changes)

        return services



    def _compute_confidence(

        self, impacted_services: List[str], depth: int

    ) -> float:

        """

        Confidence score based on:

        - Whether we found real services (vs empty list = low confidence)

        - Whether depth came from Neo4j (real) or static map (medium)

        """

        if not impacted_services:

            return 0.5

        if depth > 0:

            return min(0.95, 0.75 + depth * 0.05)

        return 0.70



    async def _record_to_graph(

        self,

        impacted_services: List[str],

        changes: List,

        risk_score: float,

        severity,

        changed_files: List[str],

        commit_sha: Optional[str],

    ):

        """Persist analysis result to Neo4j for historical context."""

        try:

            import hashlib, json
            from core.registry import RegistryManager
            p_ctx = RegistryManager.get_project_context()

            analysis_id = commit_sha or hashlib.md5(

                json.dumps(changed_files, sort_keys=True).encode()

            ).hexdigest()[:12]

            await self.dep_graph.record_analysis(

                commit_sha=analysis_id,

                service_names=impacted_services,

                risk_score=risk_score,

                severity=severity.value if hasattr(severity, 'value') else str(severity),

                changed_files=changed_files,

                repo_url=p_ctx.get("repo_url"),

                branch_ref=p_ctx.get("branch"),

            )

        except Exception as exc:

            logger.debug("Failed to record analysis to graph: %s", exc)



    async def _retrieve_context(self, changes: List) -> Dict[str, Any]:
        """Retrieve relevant context from vector database"""
        from core.registry import RegistryManager
        repository_key = RegistryManager.get_project_context().get("repository_key", "")
        return await self.retrieval.retrieve_similar(changes, repository_key=repository_key)


    def _compute_base_risk(self, factors: RiskFactors) -> float:
        """Compute base risk score from deterministic factors"""
        score = 0.0

        # File count factor
        max_file_pts = getattr(settings, "HMDA_MAX_FILE_PTS", 30)
        weight_file = getattr(settings, "HMDA_WEIGHT_FILE", 5)
        score += min(max_file_pts, factors.file_count * weight_file)

        # API changes
        if factors.api_changes:
            score += getattr(settings, "HMDA_PTS_API_CHANGE", 25)

        # Core service impact
        if factors.core_service_impact:
            score += getattr(settings, "HMDA_PTS_CORE_SERVICE", 30)

        # Dependency depth
        max_depth_pts = getattr(settings, "HMDA_MAX_DEPTH_PTS", 15)
        weight_depth = getattr(settings, "HMDA_WEIGHT_DEPTH", 5)
        score += min(max_depth_pts, factors.dependency_depth * weight_depth)

        # Schema changes
        if getattr(factors, 'schema_changes', False):
            score += getattr(settings, "HMDA_PTS_SCHEMA_CHANGE", 15)

        # Config changes
        if getattr(factors, 'config_changes', False):
            score += getattr(settings, "HMDA_PTS_CONFIG_CHANGE", 10)

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



    async def _index_changes(self, changes: List, risk_score: float):

        """Index changed files into ChromaDB for future semantic retrieval."""

        try:

            from services.dependency_graph import _infer_service_from_path
            from core.registry import RegistryManager
            repository_key = RegistryManager.get_project_context().get("repository_key", "")
            for change in changes:

                fp = getattr(change, 'file_path', '')

                content = getattr(change, 'new_content', '') or getattr(change, 'old_content', '')

                if not content:

                    continue

                ast_meta = getattr(change, 'ast_metadata', {})

                service = _infer_service_from_path(fp) or "unknown"

                await self.retrieval.index_change(

                    file_path=fp,

                    content=content,

                    service=service,

                    change_type=getattr(change, 'change_type', 'modified'),

                    language=ast_meta.get('language', 'unknown'),

                    functions=ast_meta.get('functions', []),

                    classes=ast_meta.get('classes', []),
                    risk_score=risk_score,
                    repository_key=repository_key,
                )

        except Exception as exc:

            logger.debug("Indexing failed (non-fatal): %s", exc)



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


