"""Evidence-backed architectural-smell detection for the service graph."""
import hashlib
import logging
import asyncio
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List

import httpx

from core.config import settings
from core.database import get_neo4j_driver
from core.utils import now_iso
from services.dependency_graph import _run_query

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return now_iso()


class SmellDetector:
    """Detect structural smells across 10 architectural heuristics."""

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
        # A snapshot represents a topology version, not an application start.
        # Keeping one per signature makes drift comparison meaningful and
        # prevents the graph growing forever on unchanged deployments.
        await _run_query(
            self.driver,
            """
            MERGE (snapshot:DependencySnapshot {signature: $signature})
            ON CREATE SET snapshot.edges = $edges, snapshot.created_at = $timestamp
            """,
            signature=signature,
            edges=edges,
            timestamp=timestamp,
        )

        services = await _run_query(
            self.driver,
            "MATCH (s:Service) RETURN s.name AS name, s.url AS url",
        )
        # Probe all services concurrently.  Service URLs can legitimately be
        # unavailable during startup, so these must not delay API readiness.
        async with httpx.AsyncClient(timeout=0.75) as client:
            endpoint_sets = await asyncio.gather(
                *(self._fetch_openapi_endpoints(client, service.get("url")) for service in services),
                return_exceptions=True,
            )

        for service, endpoints in zip(services, endpoint_sets):
            if isinstance(endpoints, BaseException) or endpoints is None:
                continue
            endpoint_signature = hashlib.sha256("\n".join(endpoints).encode()).hexdigest()
            await _run_query(
                self.driver,
                """
                MERGE (snapshot:ApiSnapshot {service: $service, signature: $signature})
                ON CREATE SET snapshot.endpoints = $endpoints, snapshot.created_at = $timestamp
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
            *await self._detect_shared_database(),
            *await self._detect_chatty_communication(),
            *await self._detect_missing_circuit_breaker(),
            *await self._detect_hub_and_spoke(),
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
            if not cycle or len(cycle) < 3:
                continue
            cycle_nodes = cycle[:-1]
            # Must be an elementary cycle: no intermediate node visited more than once
            if len(cycle_nodes) != len(set(cycle_nodes)) or len(cycle_nodes) < 2:
                continue
            # Canonical rotation: rotate so lexicographically smallest service is first
            min_idx = cycle_nodes.index(min(cycle_nodes))
            canonical = cycle_nodes[min_idx:] + cycle_nodes[:min_idx]
            key = tuple(canonical)
            if key not in seen:
                seen.add(key)
                canonical_path = canonical + [canonical[0]]
                services = sorted(key)
                findings.append({
                    "type": "Circular Dependency",
                    "severity": "CRITICAL",
                    "confidence": "high",
                    "services": services,
                    "evidence": {"cycle": canonical_path},
                    "description": f"Circular dependency detected: {' → '.join(canonical_path)}.",
                })
        return findings

    async def _detect_bottleneck_services(self) -> List[Dict[str, Any]]:
        if not self.driver:
            return []
        records = await _run_query(self.driver, """
            MATCH (s:Service)
            WHERE NOT s.name ENDS WITH '_facade' AND NOT s.name ENDS WITH '_gateway' AND NOT s.name = 'event_broker'
            OPTIONAL MATCH (incoming:Service)-[:DEPENDS_ON]->(s)
            WHERE incoming <> s
            OPTIONAL MATCH (s)-[:DEPENDS_ON]->(outgoing:Service)
            WHERE outgoing <> s
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
            WHERE dependency <> s
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

    async def _detect_shared_database(self) -> List[Dict[str, Any]]:
        """Detect services sharing the same database target (violates microservice isolation)."""
        findings = []
        try:
            from core.registry import RegistryManager
            deps = RegistryManager.get_dependencies()
            db_targets = defaultdict(list)
            for d in deps:
                target = d.get("to", "").lower()
                dtype = d.get("type", "").lower()
                endpoint = d.get("endpoint", "").lower()
                if (
                    dtype in ("database", "db", "sql", "postgres", "mysql", "mongodb")
                    or any(db_kw in target for db_kw in ("db", "database", "postgres", "mysql", "mongo", "redis"))
                    or any(db_port in endpoint for db_port in (":5432", ":3306", ":27017", ":6379"))
                ):
                    db_targets[d["to"]].append(d["from"])

            for target, callers in db_targets.items():
                unique_callers = sorted(set(callers))
                if len(unique_callers) > 1:
                    findings.append({
                        "type": "Shared Database",
                        "severity": "HIGH",
                        "confidence": "high",
                        "services": unique_callers,
                        "evidence": {"shared_target": target, "sharing_services": unique_callers},
                        "description": f"Shared database anti-pattern: services {', '.join(unique_callers)} directly share database target '{target}'.",
                    })
        except Exception as exc:
            logger.debug("Shared database detection failed: %s", exc)
        return findings

    async def _detect_chatty_communication(self) -> List[Dict[str, Any]]:
        """Detect mutual bidirectional calls or excessive fine-grained calls between two services."""
        findings = []
        try:
            from core.registry import RegistryManager
            deps = RegistryManager.get_dependencies()
            pair_counts = defaultdict(int)
            edges = set()
            for d in deps:
                src, tgt = d.get("from", ""), d.get("to", "")
                if src and tgt and src != tgt:
                    edges.add((src, tgt))
                    sorted_pair = tuple(sorted([src, tgt]))
                    pair_counts[sorted_pair] += 1

            seen_pairs = set()
            # Bidirectional calls: A->B and B->A
            for (src, tgt) in edges:
                if src != tgt and (tgt, src) in edges:
                    pair = tuple(sorted([src, tgt]))
                    if pair not in seen_pairs:
                        seen_pairs.add(pair)
                        findings.append({
                            "type": "Chatty Communication",
                            "severity": "MEDIUM",
                            "confidence": "high",
                            "services": list(pair),
                            "evidence": {"bidirectional": True, "pair": list(pair)},
                            "description": f"Chatty communication: cyclic request chatter between '{pair[0]}' and '{pair[1]}'.",
                        })

            # Excessive endpoint dependencies (> 2 dependencies between same pair)
            for pair, count in pair_counts.items():
                if count >= 3 and pair not in seen_pairs:
                    seen_pairs.add(pair)
                    findings.append({
                        "type": "Chatty Communication",
                        "severity": "MEDIUM",
                        "confidence": "medium",
                        "services": list(pair),
                        "evidence": {"edge_count": count, "pair": list(pair)},
                        "description": f"High communication chatter: {count} distinct dependency connections between '{pair[0]}' and '{pair[1]}'.",
                    })
        except Exception as exc:
            logger.debug("Chatty communication detection failed: %s", exc)
        return findings

    async def _detect_missing_circuit_breaker(self) -> List[Dict[str, Any]]:
        """Detect services with high outbound fan-out (>= 3 targets) without resilience patterns."""
        findings = []
        try:
            from core.registry import RegistryManager
            deps = RegistryManager.get_dependencies()
            outbound_map = defaultdict(set)
            for d in deps:
                src, tgt = d.get("from", ""), d.get("to", "")
                if src and tgt and src != tgt:
                    outbound_map[src].add(tgt)

            for src, targets in outbound_map.items():
                if any(exempt in src.lower() for exempt in ("gateway", "facade", "broker", "event")):
                    continue
                if len(targets) >= 3:
                    findings.append({
                        "type": "Missing Circuit Breaker",
                        "severity": "MEDIUM",
                        "confidence": "medium",
                        "services": [src],
                        "evidence": {"fan_out_count": len(targets), "targets": sorted(targets)},
                        "description": f"Fragile fan-out: '{src}' synchronously calls {len(targets)} downstream services ({', '.join(sorted(targets))}) without a circuit breaker.",
                    })
        except Exception as exc:
            logger.debug("Missing circuit breaker detection failed: %s", exc)
        return findings

    async def _detect_hub_and_spoke(self) -> List[Dict[str, Any]]:
        """Detect microservice monolith / central hub connected to >= 60% of all services."""
        findings = []
        try:
            from core.registry import RegistryManager
            services = RegistryManager.get_services()
            deps = RegistryManager.get_dependencies()
            total_services = len(services)
            if total_services < 3:
                return []

            degree_map = defaultdict(set)
            for d in deps:
                src, tgt = d.get("from", ""), d.get("to", "")
                if src and tgt and src != tgt:
                    degree_map[src].add(tgt)
                    degree_map[tgt].add(src)

            threshold = max(2, int((total_services - 1) * 0.6))
            for svc_name, neighbors in degree_map.items():
                if any(exempt in svc_name.lower() for exempt in ("gateway", "facade", "broker")):
                    continue
                if len(neighbors) >= threshold:
                    ratio = round(len(neighbors) / (total_services - 1), 2)
                    findings.append({
                        "type": "Hub-and-Spoke Centralization",
                        "severity": "HIGH",
                        "confidence": "high",
                        "services": [svc_name],
                        "evidence": {"connected_count": len(neighbors), "total_services": total_services, "ratio": ratio},
                        "description": f"Hub-and-spoke centralization: '{svc_name}' directly connects to {len(neighbors)}/{total_services - 1} ({int(ratio*100)}%) of services, creating a single point of failure.",
                    })
        except Exception as exc:
            logger.debug("Hub and spoke detection failed: %s", exc)
        return findings
