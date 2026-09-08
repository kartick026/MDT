"""Evidence-backed architectural-smell detection for the service graph."""
import hashlib
import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List

import httpx

from core.config import settings
from core.database import get_neo4j_driver
from services.dependency_graph import _run_query

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class SmellDetector:
    """Detect structural smells and compare persisted topology/API snapshots."""

    def __init__(self):
        self.driver = get_neo4j_driver()

    def _refresh_driver(self):
        if self.driver is None:
            self.driver = get_neo4j_driver()

    async def snapshot_current_state(self) -> None:
        """Persist a topology and OpenAPI snapshot for later trend detection."""
        self._refresh_driver()
        if not self.driver:
            return

        timestamp = _now_iso()
        edge_records = await _run_query(
            self.driver,
            """
            MATCH (from:Service)-[:DEPENDS_ON]->(to:Service)
            RETURN from.name AS source, to.name AS target
            ORDER BY source, target
            """,
        )
        edges = [f"{record['source']}->{record['target']}" for record in edge_records]
        signature = hashlib.sha256("\n".join(edges).encode()).hexdigest()
        await _run_query(
            self.driver,
            "CREATE (:DependencySnapshot {signature: $signature, edges: $edges, created_at: $timestamp})",
            signature=signature,
            edges=edges,
            timestamp=timestamp,
        )

        services = await _run_query(
            self.driver,
            "MATCH (s:Service) RETURN s.name AS name, s.url AS url",
        )
        async with httpx.AsyncClient(timeout=3.0) as client:
            for service in services:
                endpoints = await self._fetch_openapi_endpoints(client, service.get("url"))
                if endpoints is None:
                    continue
                endpoint_signature = hashlib.sha256("\n".join(endpoints).encode()).hexdigest()
                await _run_query(
                    self.driver,
                    """
                    CREATE (:ApiSnapshot {
                        service: $service, signature: $signature,
                        endpoints: $endpoints, created_at: $timestamp
                    })
                    """,
                    service=service["name"],
                    signature=endpoint_signature,
                    endpoints=endpoints,
                    timestamp=timestamp,
                )

    async def _fetch_openapi_endpoints(
        self, client: httpx.AsyncClient, base_url: str | None
    ) -> List[str] | None:
        if not base_url:
            return None
        try:
            response = await client.get(f"{base_url.rstrip('/')}/openapi.json")
            response.raise_for_status()
            paths = response.json().get("paths", {})
            return sorted(
                f"{method.upper()} {path}"
                for path, operations in paths.items()
                for method in operations
                if method.lower() in {"get", "post", "put", "patch", "delete", "head", "options"}
            )
        except (httpx.HTTPError, ValueError) as exc:
            logger.debug("OpenAPI snapshot unavailable for %s: %s", base_url, exc)
            return None

    async def detect_all_smells(self) -> List[Dict[str, Any]]:
        self._refresh_driver()
        try:
            from core.registry import RegistryManager
            reg = RegistryManager.get_services()
            if reg and self.driver:
                active = [s["name"] for s in reg]
                await _run_query(
                    self.driver,
                    "MATCH (s:Service) WHERE NOT (s.name IN $active) DETACH DELETE s",
                    active=active,
                )
        except Exception:
            pass

        return [
            *await self._detect_circular_dependencies(),
            *await self._detect_bottleneck_services(),
            *await self._detect_high_coupling(),
            *await self._detect_isolated_services(),
            *await self._detect_dependency_explosion(),
            *await self._detect_api_instability(),
        ]

    async def _detect_circular_dependencies(self) -> List[Dict[str, Any]]:
        if not self.driver:
            return []
        records = await _run_query(self.driver, """
            MATCH path = (s:Service)-[:DEPENDS_ON*2..8]->(s)
            WITH [node IN nodes(path) | node.name] AS cycle
            RETURN DISTINCT cycle
        """)
        findings, seen = [], set()
        for record in records:
            cycle = record.get("cycle", [])
            services = sorted(set(cycle))
            key = tuple(services)
            if len(services) > 1 and key not in seen:
                seen.add(key)
                findings.append({
                    "type": "Circular Dependency", "severity": "CRITICAL",
                    "confidence": "high", "services": services,
                    "evidence": {"cycle": cycle},
                    "description": f"Circular dependency detected: {' → '.join(cycle)}.",
                })
        return findings

    async def _detect_bottleneck_services(self) -> List[Dict[str, Any]]:
        if not self.driver:
            return []
        records = await _run_query(self.driver, """
            MATCH (s:Service)
            WHERE NOT s.name ENDS WITH '_facade' AND NOT s.name ENDS WITH '_gateway' AND NOT s.name = 'event_broker'
            OPTIONAL MATCH (incoming:Service)-[:DEPENDS_ON]->(s)
            OPTIONAL MATCH (s)-[:DEPENDS_ON]->(outgoing:Service)
            WITH s, count(DISTINCT incoming) AS incoming_count,
                 count(DISTINCT outgoing) AS outgoing_count
            WHERE incoming_count >= $inbound OR incoming_count + outgoing_count >= $total
            RETURN s.name AS name, incoming_count, outgoing_count
        """, inbound=settings.SMELL_BOTTLENECK_INBOUND_THRESHOLD,
             total=settings.SMELL_BOTTLENECK_TOTAL_DEGREE_THRESHOLD)
        return [{
            "type": "God / Bottleneck Service", "severity": "HIGH",
            "confidence": "medium", "services": [record["name"]],
            "evidence": {"incoming": record["incoming_count"], "outgoing": record["outgoing_count"]},
            "description": f"{record['name']} is a dependency bottleneck "
                           f"(incoming: {record['incoming_count']}, outgoing: {record['outgoing_count']}).",
        } for record in records]

    async def _detect_high_coupling(self) -> List[Dict[str, Any]]:
        if not self.driver:
            return []
        records = await _run_query(self.driver, """
            MATCH (s:Service)-[:DEPENDS_ON]->(dependency:Service)
            WITH s, count(DISTINCT dependency) AS dependency_count
            WHERE dependency_count >= $threshold
            RETURN s.name AS name, dependency_count
        """, threshold=settings.SMELL_HIGH_COUPLING_THRESHOLD)
        return [{
            "type": "High Coupling", "severity": "MEDIUM", "confidence": "high",
            "services": [record["name"]],
            "evidence": {"direct_dependencies": record["dependency_count"]},
            "description": f"{record['name']} has {record['dependency_count']} direct dependencies.",
        } for record in records]

    async def _detect_isolated_services(self) -> List[Dict[str, Any]]:
        if not self.driver:
            return []
        records = await _run_query(self.driver, """
            MATCH (s:Service)
            WHERE NOT (s)-[:DEPENDS_ON]->() AND NOT ()-[:DEPENDS_ON]->(s)
            RETURN s.name AS name
        """)
        return [{
            "type": "Dead / Isolated Service", "severity": "LOW", "confidence": "medium",
            "services": [record["name"]], "evidence": {"degree": 0},
            "description": f"{record['name']} has no dependency-graph callers or dependencies.",
        } for record in records]

    async def _detect_dependency_explosion(self) -> List[Dict[str, Any]]:
        if not self.driver:
            return []
        records = await _run_query(self.driver, """
            MATCH (snapshot:DependencySnapshot)
            RETURN snapshot.edges AS edges, snapshot.created_at AS created_at
            ORDER BY created_at DESC LIMIT 2
        """)
        if len(records) < 2:
            return []
        current, previous = set(records[0]["edges"]), set(records[1]["edges"])
        added = sorted(current - previous)
        if len(added) < settings.SMELL_DEPENDENCY_GROWTH_THRESHOLD:
            return []
        by_service: Dict[str, List[str]] = defaultdict(list)
        for edge in added:
            by_service[edge.split("->", 1)[0]].append(edge)
        return [{
            "type": "Dependency Explosion", "severity": "HIGH", "confidence": "high",
            "services": sorted(by_service),
            "evidence": {"added_edges": added, "previous_snapshot": records[1]["created_at"], "current_snapshot": records[0]["created_at"]},
            "description": f"{len(added)} dependencies were added since the previous topology snapshot.",
        }]

    async def _detect_api_instability(self) -> List[Dict[str, Any]]:
        if not self.driver:
            return []
        records = await _run_query(self.driver, """
            MATCH (snapshot:ApiSnapshot)
            RETURN snapshot.service AS service, snapshot.endpoints AS endpoints,
                   snapshot.created_at AS created_at
            ORDER BY service, created_at DESC
        """)
        snapshots: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for record in records:
            if len(snapshots[record["service"]]) < 2:
                snapshots[record["service"]].append(record)
        findings = []
        for service, values in snapshots.items():
            if len(values) < 2:
                continue
            current, previous = set(values[0]["endpoints"]), set(values[1]["endpoints"])
            removed, added = sorted(previous - current), sorted(current - previous)
            churn = len(removed) + len(added)
            if removed or churn >= settings.SMELL_API_CHURN_THRESHOLD:
                findings.append({
                    "type": "API Instability", "severity": "HIGH" if removed else "MEDIUM",
                    "confidence": "high", "services": [service],
                    "evidence": {"removed_endpoints": removed, "added_endpoints": added,
                                 "previous_snapshot": values[1]["created_at"], "current_snapshot": values[0]["created_at"]},
                    "description": f"{service} changed {churn} OpenAPI endpoint definitions since the previous snapshot.",
                })
        return findings
