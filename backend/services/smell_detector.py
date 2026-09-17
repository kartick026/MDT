"""Evidence-backed architectural-smell detection for the service graph."""
import hashlib
import logging
import asyncio
import math
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

import httpx

from core.config import settings
from core.database import get_neo4j_driver
from core.utils import now_iso
from services.dependency_graph import _run_query

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return now_iso()


def calculate_circuit_breaker_threshold(
    total_services: int, outbound_counts: Optional[List[int]] = None
) -> int:
    """
    Dynamically calculate missing circuit breaker threshold using graph vulnerability percolation:
    In dependency networks, systemic cascading failure risk transitions when a node's
    unshielded fan-out exceeds the sub-linear network percolation scale:
        theta_percolation = max(2, ceil(sqrt(N)))
    When outbound counts across the fleet are available, modulates against statistical outlier bounds:
        theta_stat = ceil(mean + std)
        threshold = min(theta_percolation, max(2, theta_stat))
    """
    if total_services <= 2:
        return 2
    percolation_threshold = max(2, math.ceil(math.sqrt(total_services)))
    if outbound_counts and len(outbound_counts) > 1:
        mean_deg = sum(outbound_counts) / len(outbound_counts)
        variance = sum((x - mean_deg) ** 2 for x in outbound_counts) / len(outbound_counts)
        std_deg = math.sqrt(variance)
        stat_threshold = max(2, math.ceil(mean_deg + std_deg))
        return min(percolation_threshold, stat_threshold)
    return percolation_threshold


def calculate_hub_and_spoke_threshold(total_services: int) -> int:
    """
    Dynamically calculate the hub-and-spoke centralization threshold based on
    Freeman network degree centrality with an upper cap:
      tau(N) = min(0.85, max(0.60, 1.0 - 1.0 / sqrt(N)))
      threshold = max(2, ceil(tau(N) * (N - 1)))

    The 0.85 cap prevents the threshold from becoming unreachable at scale.
    Without it, tau(200) = 0.929 demands 185/199 connectivity (93%) — a service
    would need to connect to nearly every other service to be flagged. With the
    cap, the threshold stays at ~85% of the fleet, still strict but reachable
    by genuine central hubs.
    """
    if total_services < 3:
        return 0  # A hub-and-spoke star requires at least 3 nodes to form
    ratio = min(0.85, max(0.60, 1.0 - (1.0 / math.sqrt(total_services))))
    return max(2, math.ceil(ratio * (total_services - 1)))


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

    def _is_mock(self) -> bool:
        from core.database import MockNeo4jDriver
        return isinstance(self.driver, MockNeo4jDriver) or self.driver is None

    async def detect_all_smells(self) -> List[Dict[str, Any]]:
        self._refresh_driver()
        try:
            from core.registry import RegistryManager
            reg = RegistryManager.get_services()
            if reg and self.driver and not self._is_mock():
                dep_nodes = [d["to"] for d in RegistryManager.get_dependencies() if d.get("to")] + [d["from"] for d in RegistryManager.get_dependencies() if d.get("from")]
                active = list(set([s["name"] for s in reg] + dep_nodes))
                await _run_query(
                    self.driver,
                    """
                    MATCH (s:Service)
                    WHERE NOT (s.name IN $active)
                      AND NOT toLower(s.name) CONTAINS 'postgres'
                      AND NOT toLower(s.name) CONTAINS 'database'
                      AND NOT toLower(s.name) CONTAINS 'db'
                    DETACH DELETE s
                    """,
                    active=active,
                )
        except Exception as exc:
            logger.debug("Active services sync cleanup failed: %s", exc)

        cycles = await self._detect_circular_dependencies()
        cycle_pairs = {tuple(sorted(f["services"])) for f in cycles if len(f.get("services", [])) == 2}
        return [
            *cycles,
            *await self._detect_bottleneck_services(),
            *await self._detect_high_coupling(),
            *await self._detect_isolated_services(),
            *await self._detect_dependency_explosion(),
            *await self._detect_api_instability(),
            *await self._detect_shared_database(),
            *await self._detect_chatty_communication(exclude_pairs=cycle_pairs),
            *await self._detect_missing_circuit_breaker(),
            *await self._detect_hub_and_spoke(),
        ]

    async def _detect_circular_dependencies(self) -> List[Dict[str, Any]]:
        records = []
        if self.driver and not self._is_mock():
            try:
                records = await _run_query(self.driver, """
                    MATCH path = (s:Service)-[:DEPENDS_ON*2..8]->(s)
                    WITH [node IN nodes(path) | node.name] AS cycle
                    RETURN DISTINCT cycle
                """)
            except Exception as exc:
                logger.debug("Cypher circular dependency query failed: %s", exc)

        if not records:
            try:
                from core.registry import RegistryManager
                deps = RegistryManager.get_dependencies()
                adj = defaultdict(set)
                for d in deps:
                    src, tgt = d.get("from"), d.get("to")
                    if src and tgt and src != tgt:
                        adj[src].add(tgt)

                detected_cycles = []
                all_nodes = sorted(adj.keys())

                def dfs(start_node, curr_node, path, visited):
                    if len(path) > 8:
                        return
                    for neighbor in adj.get(curr_node, []):
                        if neighbor == start_node and len(path) >= 2:
                            detected_cycles.append(list(path) + [start_node])
                        elif neighbor not in visited and neighbor > start_node:
                            visited.add(neighbor)
                            dfs(start_node, neighbor, path + [neighbor], visited)
                            visited.remove(neighbor)

                for node in all_nodes:
                    dfs(node, node, [node], {node})

                records = [{"cycle": c} for c in detected_cycles]
            except Exception as exc:
                logger.debug("In-memory circular dependency fallback failed: %s", exc)

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
        records = []
        if self.driver and not self._is_mock():
            try:
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
            except Exception as exc:
                logger.debug("Cypher bottleneck detection failed: %s", exc)

        if not records:
            try:
                from core.registry import RegistryManager
                services = RegistryManager.get_services()
                deps = RegistryManager.get_dependencies()
                inbound_map = defaultdict(set)
                outbound_map = defaultdict(set)
                for d in deps:
                    src, tgt = d.get("from"), d.get("to")
                    if src and tgt and src != tgt:
                        inbound_map[tgt].add(src)
                        outbound_map[src].add(tgt)

                for svc in services:
                    name = svc.get("name")
                    if not name or name.endswith("_facade") or name.endswith("_gateway") or name == "event_broker":
                        continue
                    in_count = len(inbound_map.get(name, set()))
                    out_count = len(outbound_map.get(name, set()))
                    if in_count >= settings.SMELL_BOTTLENECK_INBOUND_THRESHOLD or (in_count + out_count) >= settings.SMELL_BOTTLENECK_TOTAL_DEGREE_THRESHOLD:
                        records.append({"name": name, "incoming_count": in_count, "outgoing_count": out_count})
            except Exception as exc:
                logger.debug("In-memory bottleneck detection failed: %s", exc)

        return [{
            "type": "God / Bottleneck Service", "severity": "HIGH",
            "confidence": "medium", "services": [record["name"]],
            "evidence": {"incoming": record["incoming_count"], "outgoing": record["outgoing_count"]},
            "description": f"{record['name']} is a dependency bottleneck "
                           f"(incoming: {record['incoming_count']}, outgoing: {record['outgoing_count']}).",
        } for record in records]

    async def _detect_high_coupling(self) -> List[Dict[str, Any]]:
        records = []
        if self.driver and not self._is_mock():
            try:
                records = await _run_query(self.driver, """
                    MATCH (s:Service)-[:DEPENDS_ON]->(dependency:Service)
                    WHERE dependency <> s
                    WITH s, count(DISTINCT dependency) AS dependency_count
                    WHERE dependency_count >= $threshold
                    RETURN s.name AS name, dependency_count
                """, threshold=settings.SMELL_HIGH_COUPLING_THRESHOLD)
            except Exception as exc:
                logger.debug("Cypher high coupling detection failed: %s", exc)

        if not records:
            try:
                from core.registry import RegistryManager
                deps = RegistryManager.get_dependencies()
                outbound_map = defaultdict(set)
                for d in deps:
                    src, tgt = d.get("from"), d.get("to")
                    if src and tgt and src != tgt:
                        outbound_map[src].add(tgt)
                for name, targets in outbound_map.items():
                    if len(targets) >= settings.SMELL_HIGH_COUPLING_THRESHOLD:
                        records.append({"name": name, "dependency_count": len(targets)})
            except Exception as exc:
                logger.debug("In-memory high coupling detection failed: %s", exc)

        return [{
            "type": "High Coupling", "severity": "MEDIUM", "confidence": "high",
            "services": [record["name"]],
            "evidence": {"direct_dependencies": record["dependency_count"]},
            "description": f"{record['name']} has {record['dependency_count']} direct dependencies.",
        } for record in records]

    async def _detect_isolated_services(self) -> List[Dict[str, Any]]:
        records = []
        if self.driver and not self._is_mock():
            try:
                records = await _run_query(self.driver, """
                    MATCH (s:Service)
                    WHERE NOT (s)-[:DEPENDS_ON]->() AND NOT ()-[:DEPENDS_ON]->(s)
                      AND NOT s.name ENDS WITH '_facade' AND NOT s.name ENDS WITH '_gateway'
                      AND NOT s.name = 'event_broker'
                      AND (s.is_external IS NULL OR s.is_external = false OR NOT s.name STARTS WITH 'external-')
                    RETURN s.name AS name
                """)
            except Exception as exc:
                logger.debug("Cypher isolated service detection failed: %s", exc)

        if not records:
            try:
                from core.registry import RegistryManager
                services = RegistryManager.get_services()
                deps = RegistryManager.get_dependencies()
                connected = set()
                for d in deps:
                    src, tgt = d.get("from"), d.get("to")
                    if src:
                        connected.add(src)
                    if tgt:
                        connected.add(tgt)
                for svc in services:
                    name = svc.get("name")
                    if not name or name in connected:
                        continue
                    # Skip externally-imported third-party services — they are not "dead", just not yet connected
                    if svc.get("is_external") and name.startswith("external-"):
                        continue
                    # Skip architectural infrastructure names (matches Cypher query behavior)
                    if name.endswith("_facade") or name.endswith("_gateway") or name == "event_broker":
                        continue
                    records.append({"name": name})
            except Exception as exc:
                logger.debug("In-memory isolated service detection failed: %s", exc)

        return [{
            "type": "Dead / Isolated Service", "severity": "LOW", "confidence": "medium",
            "services": [record["name"]], "evidence": {"degree": 0},
            "description": f"{record['name']} has no dependency-graph callers or dependencies.",
        } for record in records]

    async def _detect_dependency_explosion(self) -> List[Dict[str, Any]]:
        from core.registry import RegistryManager, LOCAL_DEMO_SMELL_HISTORY
        context = RegistryManager.get_project_context()
        is_demo = context.get("source") == "local_demo"
        active_services = {s["name"] for s in RegistryManager.get_services()}

        records = []
        if self.driver and not self._is_mock():
            try:
                records = await _run_query(self.driver, """
                    MATCH (snapshot:DependencySnapshot)
                    RETURN snapshot.edges AS edges, snapshot.created_at AS created_at
                    ORDER BY created_at DESC
                """)
            except Exception as exc:
                logger.debug("Cypher dependency snapshot query failed: %s", exc)

        if not records:
            try:
                data = RegistryManager.load()
                if is_demo:
                    raw_snapshots = (
                        data.get("dependency_snapshots")
                        or data.get("snapshots")
                        or LOCAL_DEMO_SMELL_HISTORY.get("dependency_snapshots", [])
                    )
                else:
                    raw_snapshots = data.get("dependency_snapshots") or data.get("snapshots") or []

                if raw_snapshots:
                    sorted_snaps = sorted(raw_snapshots, key=lambda s: s.get("created_at", ""), reverse=True)
                    records = sorted_snaps
            except Exception as exc:
                logger.debug("In-memory dependency snapshot fallback failed: %s", exc)

        if len(records) < 2:
            return []

        # Filter foreign demo fleet edges if an external repository is active
        if not is_demo and active_services:
            demo_services = {"order-service", "user-service", "payment-service", "notification-service"}
            foreign_demo = demo_services - active_services
            if foreign_demo:
                filtered_records = []
                for rec in records:
                    valid_edges = [
                        e for e in rec.get("edges", [])
                        if "->" in e and e.split("->", 1)[0] not in foreign_demo
                    ]
                    filtered_records.append({
                        "edges": valid_edges,
                        "created_at": rec.get("created_at", "")
                    })
                records = filtered_records

        if len(records) < 2:
            return []

        current = set(records[0]["edges"])
        previous_record = None
        for prev in records[1:]:
            if set(prev["edges"]) != current:
                previous_record = prev
                break

        if not previous_record:
            return []

        previous = set(previous_record["edges"])
        added = sorted(current - previous)
        if len(added) < settings.SMELL_DEPENDENCY_GROWTH_THRESHOLD:
            return []
        by_service: Dict[str, List[str]] = defaultdict(list)
        for edge in added:
            by_service[edge.split("->", 1)[0]].append(edge)
        return [{
            "type": "Dependency Explosion", "severity": "HIGH", "confidence": "high",
            "services": sorted(by_service),
            "evidence": {"added_edges": added, "previous_snapshot": previous_record["created_at"], "current_snapshot": records[0]["created_at"]},
            "description": f"{len(added)} dependencies were added since the previous topology snapshot.",
        }]

    async def _detect_api_instability(self) -> List[Dict[str, Any]]:
        from core.registry import RegistryManager, LOCAL_DEMO_SMELL_HISTORY
        context = RegistryManager.get_project_context()
        is_demo = context.get("source") == "local_demo"
        active_services = {s["name"] for s in RegistryManager.get_services()}

        records = []
        if self.driver and not self._is_mock():
            try:
                records = await _run_query(self.driver, """
                    MATCH (snapshot:ApiSnapshot)
                    RETURN snapshot.service AS service, snapshot.endpoints AS endpoints,
                           snapshot.created_at AS created_at
                    ORDER BY service, created_at DESC
                """)
            except Exception as exc:
                logger.debug("Cypher API snapshot query failed: %s", exc)

        if not records:
            try:
                data = RegistryManager.load()
                if is_demo:
                    raw_snaps = (
                        data.get("api_snapshots")
                        or LOCAL_DEMO_SMELL_HISTORY.get("api_snapshots", [])
                    )
                else:
                    raw_snaps = data.get("api_snapshots") or []

                if raw_snaps:
                    records = sorted(raw_snaps, key=lambda s: s.get("created_at", ""), reverse=True)
            except Exception as exc:
                logger.debug("In-memory API snapshot fallback failed: %s", exc)

        # Filter foreign demo fleet services if an external repository is active
        if not is_demo and active_services:
            demo_services = {"order-service", "user-service", "payment-service", "notification-service"}
            foreign_demo = demo_services - active_services
            if foreign_demo:
                records = [r for r in records if r.get("service") not in foreign_demo]

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
                    dtype in ("database", "db", "sql", "postgres", "postgresql", "mysql", "mongodb")
                    or any(db_kw in target for db_kw in ("db", "database", "postgres", "mysql", "mongo", "redis"))
                    or any(db_port in endpoint for db_port in (":5432", ":3306", ":27017", ":6379"))
                ):
                    db_targets[target].append(d["from"])

            seen_targets = set()
            for target, callers in db_targets.items():
                unique_callers = sorted(set(callers))
                if len(unique_callers) > 1 and target not in seen_targets:
                    seen_targets.add(target)
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

    async def _detect_chatty_communication(
        self, exclude_pairs: Optional[Set[Tuple[str, str]]] = None
    ) -> List[Dict[str, Any]]:
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
                        if exclude_pairs and pair in exclude_pairs and pair_counts.get(pair, 0) < 3:
                            continue
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
        """Detect services with high outbound fan-out exceeding the dynamic percolation threshold without resilience patterns."""
        findings = []
        try:
            from core.registry import RegistryManager
            reg_services = RegistryManager.get_services()
            service_names = {s.get("name") for s in reg_services if s.get("name")}
            services = {s.get("name"): s for s in reg_services if s.get("name")}
            deps = RegistryManager.get_dependencies()
            outbound_map = defaultdict(set)
            for d in deps:
                src, tgt = d.get("from", ""), d.get("to", "")
                if src and tgt and src != tgt and tgt in service_names:
                    outbound_map[src].add(tgt)

            total_services = len(service_names)
            all_fan_outs = [len(outbound_map.get(s, set())) for s in service_names if s != "event_broker"]
            threshold = calculate_circuit_breaker_threshold(total_services, all_fan_outs)

            for src, targets in outbound_map.items():
                svc_meta = services.get(src, {})
                if svc_meta.get("has_circuit_breaker") or svc_meta.get("resilient"):
                    continue
                if src == "event_broker":
                    continue
                if len(targets) >= threshold:
                    fan_out_ratio = round(len(targets) / max(1, total_services - 1), 2)
                    findings.append({
                        "type": "Missing Circuit Breaker",
                        "severity": "MEDIUM",
                        "confidence": "high" if fan_out_ratio >= 0.5 else "medium",
                        "services": [src],
                        "evidence": {
                            "fan_out_count": len(targets),
                            "targets": sorted(targets),
                            "dynamic_threshold": threshold,
                            "fan_out_ratio": fan_out_ratio,
                            "total_services": total_services,
                        },
                        "description": f"Fragile fan-out: '{src}' synchronously calls {len(targets)} downstream services ({', '.join(sorted(targets))}) without a circuit breaker (dynamic percolation threshold: {threshold}).",
                    })
        except Exception as exc:
            logger.debug("Missing circuit breaker detection failed: %s", exc)
        return findings

    async def _detect_hub_and_spoke(self) -> List[Dict[str, Any]]:
        """Detect microservice monolith / central hub using Freeman degree centrality and asymmetry ratio."""
        records = []
        if self.driver and not self._is_mock():
            try:
                records = await _run_query(self.driver, """
                    MATCH (all_s:Service)
                    WHERE NOT all_s.name ENDS WITH '_facade' AND NOT all_s.name ENDS WITH '_gateway' AND NOT all_s.name = 'event_broker'
                      AND NOT toLower(all_s.name) CONTAINS 'postgres' AND NOT toLower(all_s.name) CONTAINS 'database' AND NOT toLower(all_s.name) CONTAINS 'db'
                    WITH collect(DISTINCT all_s) AS fleet, count(DISTINCT all_s) AS total_services
                    WHERE total_services >= 3
                    UNWIND fleet AS s
                    OPTIONAL MATCH (s)-[:DEPENDS_ON]-(neighbor:Service)
                    WHERE neighbor IN fleet AND neighbor <> s
                    WITH fleet, total_services, s, count(DISTINCT neighbor) AS deg
                    WITH total_services,
                         collect({service: s, deg: deg}) AS svc_degrees,
                         avg(deg) AS avg_deg,
                         toInteger(ceil(
                           CASE 
                             WHEN (1.0 - 1.0/sqrt(total_services)) > 0.85 THEN 0.85
                             WHEN (1.0 - 1.0/sqrt(total_services)) > 0.60 THEN (1.0 - 1.0/sqrt(total_services)) 
                             ELSE 0.60 
                           END * (total_services - 1)
                         )) AS min_hub_deg
                    UNWIND svc_degrees AS item
                    WITH item.service AS s, item.deg AS deg, total_services, avg_deg, min_hub_deg
                    WHERE deg >= min_hub_deg AND deg > avg_deg
                    RETURN s.name AS name, deg, total_services, avg_deg, min_hub_deg
                """)
            except Exception as exc:
                logger.debug("Cypher hub and spoke detection failed: %s", exc)

        if records:
            findings = []
            for r in records:
                svc_name = r["name"]
                deg = r["deg"]
                total_services = r["total_services"]
                avg_deg = r["avg_deg"]
                threshold = r["min_hub_deg"]
                ratio = round(deg / (total_services - 1), 2) if total_services > 1 else 1.0
                findings.append({
                    "type": "Hub-and-Spoke Centralization",
                    "severity": "HIGH",
                    "confidence": "high",
                    "services": [svc_name],
                    "evidence": {
                        "connected_count": deg,
                        "total_services": total_services,
                        "ratio": ratio,
                        "dynamic_threshold": threshold,
                        "average_degree": round(avg_deg, 2),
                    },
                    "description": f"Hub-and-spoke centralization: '{svc_name}' directly connects to {deg}/{total_services - 1} ({int(ratio*100)}%) of services (dynamic threshold: {threshold}, avg degree: {round(avg_deg, 1)}), creating a single point of failure.",
                })
            return findings

        findings = []
        try:
            from core.registry import RegistryManager
            services = RegistryManager.get_services()
            service_names = {s.get("name") for s in services if s.get("name") and s.get("name") != "event_broker"}
            total_services = len(service_names)
            if total_services < 3:
                return []

            deps = RegistryManager.get_dependencies()
            degree_map = defaultdict(set)
            for d in deps:
                src, tgt = d.get("from", ""), d.get("to", "")
                if src and tgt and src != tgt and src in service_names and tgt in service_names:
                    degree_map[src].add(tgt)
                    degree_map[tgt].add(src)

            degrees = [len(degree_map.get(s, set())) for s in service_names]
            avg_deg = sum(degrees) / len(degrees) if degrees else 0.0
            threshold = calculate_hub_and_spoke_threshold(total_services)

            for svc_name in sorted(service_names):
                neighbors = degree_map.get(svc_name, set())
                deg = len(neighbors)
                # Must meet dynamic centralization threshold and exhibit topological dominance (deg > avg_deg)
                if deg >= threshold and deg > avg_deg:
                    ratio = round(deg / (total_services - 1), 2)
                    findings.append({
                        "type": "Hub-and-Spoke Centralization",
                        "severity": "HIGH",
                        "confidence": "high",
                        "services": [svc_name],
                        "evidence": {
                            "connected_count": deg,
                            "total_services": total_services,
                            "ratio": ratio,
                            "dynamic_threshold": threshold,
                            "average_degree": round(avg_deg, 2),
                        },
                        "description": f"Hub-and-spoke centralization: '{svc_name}' directly connects to {deg}/{total_services - 1} ({int(ratio*100)}%) of services (dynamic threshold: {threshold}, avg degree: {round(avg_deg, 1)}), creating a single point of failure.",
                    })
        except Exception as exc:
            logger.debug("Hub and spoke detection failed: %s", exc)
        return findings
