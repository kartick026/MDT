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
    from domain.architecture import circuit_breaker_threshold
    return circuit_breaker_threshold(total_services, outbound_counts)


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
    from domain.architecture import hub_threshold
    return hub_threshold(total_services)


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

    def current_snapshot(self):
        from domain.architecture import registry_snapshot
        return registry_snapshot()

    async def detect_all_smells(self, snapshot=None) -> List[Dict[str, Any]]:
        """Read-only evaluation of one immutable snapshot in every runtime mode."""
        from domain.architecture import detect_smells, configured_thresholds
        return detect_smells(snapshot or self.current_snapshot(), configured_thresholds())

    async def _detect_category(self, category):
        return [finding for finding in await self.detect_all_smells() if finding["type"] == category]

    async def _detect_circular_dependencies(self):
        return await self._detect_category("Circular Dependency")

    async def _detect_bottleneck_services(self):
        return await self._detect_category("God / Bottleneck Service")

    async def _detect_high_coupling(self):
        return await self._detect_category("High Coupling")

    async def _detect_isolated_services(self):
        return await self._detect_category("Dead / Isolated Service")

    async def _detect_dependency_explosion(self):
        return await self._detect_category("Dependency Explosion")

    async def _detect_api_instability(self):
        return await self._detect_category("API Instability")

    async def _detect_shared_database(self):
        return await self._detect_category("Shared Database")

    async def _detect_chatty_communication(self, exclude_pairs=None):
        # Deduplication against two-node cycles is part of the canonical detector.
        findings = await self._detect_category("Chatty Communication")
        if exclude_pairs:
            findings = [f for f in findings if tuple(sorted(f["services"])) not in exclude_pairs
                        or f["evidence"].get("edge_count", 0) >= 3]
        return findings

    async def _detect_missing_circuit_breaker(self):
        return await self._detect_category("Missing Circuit Breaker")

    async def _detect_hub_and_spoke(self):
        return await self._detect_category("Hub-and-Spoke Centralization")
