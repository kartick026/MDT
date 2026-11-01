"""

HMDA - Hierarchical Microservice Drift Analysis

Deterministic + AI-assisted risk scoring engine

"""

import logging
import math
from typing import List, Dict, Any, Optional, Set
from dataclasses import dataclass
import asyncio



from schemas.analysis import ImpactResult, SeverityLevel, DiffFile, DependencyInfo

from services.dependency_graph import DependencyGraph

from services.retrieval import RetrievalEngine

from services.llm_explainer import LLMExplainer

from core.config import settings
from core.registry import current_project_id



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

        effective_changes = [c for c in changes if getattr(c, "ast_metadata", {}).get("semantic_change") is not False]
        risk_factors = self._calculate_deterministic_risk(effective_changes)



        # Step 2: Get impacted services + real dependency depth from graph

        impacted_services, max_depth = await self._get_impacted_services_with_depth(effective_changes)

        risk_factors.dependency_depth = max_depth



        # Step 3: Retrieve relevant context from ChromaDB

        retrieved_context = await self._retrieve_context(effective_changes) if effective_changes else {}



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

        from core.registry import RegistryManager
        from services.analysis_evidence import assess_evidence
        confidence, assessment_status, confidence_evidence = assess_evidence(changes, RegistryManager.load())
        if assessment_status in {"insufficient_evidence", "partial"}:
            explanation = (explanation or "") + " Evidence coverage is incomplete; the risk score is provisional."




        # Step 10: Record analysis in graph for history

        if impacted_services:

            changed_files = [getattr(c, 'file_path', str(c)) for c in changes]

            await self._record_to_graph(

                impacted_services, changes, final_risk, severity,

                changed_files, commit_sha,

            )



        # Step 11: Index changed files into ChromaDB for future retrieval

        await self._index_changes(effective_changes, final_risk)



        return ImpactResult(

            risk_score=round(final_risk, 1),

            severity=severity,

            impacted_services=impacted_services,

            confidence=confidence,
            assessment_status=assessment_status,
            confidence_evidence=confidence_evidence,

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

        changes = [c for c in changes if getattr(c, "ast_metadata", {}).get("semantic_change") is not False]
        return RiskFactors(

            file_count=len(changes),

            core_service_impact=self._has_core_service_impact(changes),

            api_changes=self._has_breaking_api_changes(changes),

            dependency_depth=2,  # updated later by _get_real_depth()

            semantic_risk=0.0,

            schema_changes=self._has_schema_changes(changes),

            config_changes=self._has_config_changes(changes),

        )



    def _get_core_services(self) -> Set[str]:
        """
        Dynamically determine core architectural services based on in-degree centrality.
        A service is 'core' when other services genuinely depend on it heavily.
        Count distinct inbound peer services, including zero-degree services in the
        fleet mean. Core threshold is max(2, ceil(mean distinct in-degree)).
        """
        try:
            from core.registry import RegistryManager
            deps = RegistryManager.get_dependencies()
            services = {svc["name"] for svc in RegistryManager.get_services()}
            inbound = {name: set() for name in services}
            for dependency in deps:
                from domain.relations import is_startup
                if is_startup(dependency):
                    continue
                source, target = dependency.get("from"), dependency.get("to")
                if source in services and target in services and source != target:
                    inbound[target].add(source)
            if not inbound:
                return set()
            in_degree = {name: len(peers) for name, peers in inbound.items()}
            threshold = max(2, math.ceil(sum(in_degree.values()) / len(in_degree)))
            core = {name for name, degree in in_degree.items() if degree >= threshold}
            return core
        except Exception as exc:
            logger.debug("Failed to calculate core services from graph: %s", exc)
            return set()

    def _has_core_service_impact(self, changes: List) -> bool:
        """Check if any changed file belongs to a dynamically computed core service."""
        core_services = self._get_core_services()
        if not core_services:
            return False

        from services.dependency_graph import _infer_service_from_path
        return any(_infer_service_from_path(getattr(change, "file_path", str(change))) in core_services
                   or _infer_service_from_path(getattr(change, "previous_path", "") or "") in core_services
                   for change in changes)




    def _has_api_changes(self, changes: List) -> bool:
        """Require extracted contract evidence; file names alone prove nothing."""
        for change in changes:
            metadata = getattr(change, "ast_metadata", {})
            if metadata.get("semantic_change") is False:
                continue
            delta = metadata.get("contract_changes", {})
            if any(delta.get(key) for key in ("added", "removed", "modified")):
                return True
            schema = metadata.get("schema_changes", {})
            if schema.get("compatibility") == "breaking" or schema.get("affected_routes"):
                return True
        return False

    def _has_breaking_api_changes(self, changes: List) -> bool:
        for change in changes:
            metadata = getattr(change, "ast_metadata", {})
            if metadata.get("semantic_change") is False:
                continue
            delta = metadata.get("contract_changes", {})
            schema = metadata.get("schema_changes", {})
            if schema.get("compatibility") == "breaking":
                return True
            if (delta.get("removed") or delta.get("modified")) and delta.get("compatibility") != "additive":
                return True
        return False

    def _has_schema_changes(self, changes: List) -> bool:

        """Check if any changes contain database schema, migration, or DDL definitions"""

        schema_patterns = ['migration', '.sql', 'schema', 'alembic', 'flyway', 'prisma', 'db/migrate']

        for change in changes:

            metadata = getattr(change, "ast_metadata", {})
            if metadata.get("semantic_change") is False:
                continue
            file_path = getattr(change, 'file_path', str(change)).lower().replace("\\", "/")

            schema = metadata.get("schema_changes", {})
            if any(schema.get(key) for key in ("added", "removed", "modified")):
                return True
            if any(pattern in file_path for pattern in schema_patterns):

                return True

        return False



    def _has_config_changes(self, changes: List) -> bool:

        """Check if changes touch deployment or infrastructure configuration"""

        config_patterns = [

            'docker-compose', 'compose.yml', 'compose.yaml', '.env', 'helm', 'k8s', 'kubernetes', 'terraform',

            'settings.py', 'config.py', 'application.yml', 'application.yaml', 'values.yaml'

        ]

        for change in changes:

            metadata = getattr(change, "ast_metadata", {})
            if metadata.get("semantic_change") is False:
                continue
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
        checked_services = set()



        for change in changes:

            file_path = getattr(change, 'file_path', str(change))

            impacted = await self.dep_graph.get_affected_services(file_path)

            services.update(impacted)



            # Get depth for each impacted service

            for svc in set(impacted) - checked_services:

                depth = await self.dep_graph.get_dependency_depth(svc)

                max_depth = max(max_depth, depth)
                checked_services.add(svc)



        return list(services), max_depth



    async def _get_impacted_services(self, changes: List) -> List[str]:

        """Legacy wrapper — used by tests."""

        services, _ = await self._get_impacted_services_with_depth(changes)

        return services



    def _compute_confidence(self, impacted_services, depth, *, changes=None) -> float:
        """Compatibility wrapper: graph depth does not establish confidence."""
        from core.registry import RegistryManager
        from services.analysis_evidence import assess_evidence
        return assess_evidence(changes or [], RegistryManager.load())[0]

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
        revisions = {getattr(change, "commit_sha", "") for change in changes}
        timestamps = [getattr(change, "commit_timestamp", None) for change in changes]
        timestamp = min(timestamps) if timestamps and all(t is not None for t in timestamps) else None
        return await self.retrieval.retrieve_similar(changes, repository_key=repository_key,
            project_id=current_project_id() or "", target_commit_sha=next(iter(revisions)) if len(revisions) == 1 else "",
            before_timestamp=timestamp)


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

        if current_project_id() or getattr(settings, "RUNTIME_PROFILE", "local") == "hosted":
            partial = any(getattr(c, "extraction_status", "complete") != "complete" for c in changes)
            return (f"Deterministic analysis of {len(changes)} changed files identifies "
                    f"{len(impacted_services)} affected services and a heuristic risk score of {risk_score}/100. "
                    + ("Source extraction is partial; review the coverage warnings before relying on this result. " if partial else "")
                    + "This score is not a measured failure probability. Source content was not sent to an LLM.")
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
                    project_id=current_project_id() or "",
                    commit_sha=getattr(change, "commit_sha", ""),
                    commit_timestamp=getattr(change, "commit_timestamp", None),
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


