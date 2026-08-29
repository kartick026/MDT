"""
Neo4j Dependency Graph Service — Phase 5 (Week 6)
===================================================
Manages the service dependency graph using Neo4j.

Graph schema
------------
Nodes:
  (:Service  {name, port, url, language, description, created_at})
  (:File     {path, service, language, functions[], classes[], last_seen})

Relationships:
  (:Service)-[:DEPENDS_ON {type, endpoint, created_at}]->(:Service)
  (:Service)-[:DEFINES_FILE]->(  :File)

Driver note
-----------
The neo4j Python driver ≥ 5.x exposes AsyncGraphDatabase for true async
sessions.  We use that when available and fall back to running sync
sessions in a thread-pool executor when the older sync driver is used.
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from core.config import settings
from core.database import get_neo4j_driver

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Known MDT demo services — used to seed the graph on first startup
# ---------------------------------------------------------------------------
KNOWN_SERVICES: List[Dict[str, Any]] = [
    {
        "name": "user-service",
        "port": 8001,
        "url": "http://user-service:8001",
        "language": "python",
        "description": "User management — CRUD for user accounts",
    },
    {
        "name": "order-service",
        "port": 8002,
        "url": "http://order-service:8002",
        "language": "python",
        "description": "Order processing — depends on user-service",
    },
    {
        "name": "payment-service",
        "port": 8003,
        "url": "http://payment-service:8003",
        "language": "python",
        "description": "Payment processing — depends on order-service",
    },
    {
        "name": "notification-service",
        "port": 8004,
        "url": "http://notification-service:8004",
        "language": "python",
        "description": "Notifications — depends on order-service and payment-service",
    },
]

# Real HTTP dependency edges between the demo services
KNOWN_DEPENDENCIES: List[Dict[str, str]] = [
    {"from": "order-service",        "to": "user-service",    "type": "http",
     "endpoint": "/users/{user_id}"},
    {"from": "payment-service",      "to": "order-service",   "type": "http",
     "endpoint": "/orders/{order_id}"},
    {"from": "notification-service", "to": "order-service",   "type": "http",
     "endpoint": "/orders/{order_id}"},
    {"from": "notification-service", "to": "payment-service", "type": "http",
     "endpoint": "/payments/{payment_id}"},
]

# Map file-path prefixes → owning service
FILE_SERVICE_MAP: Dict[str, str] = {
    "services/user_service":        "user-service",
    "services/order_service":       "order-service",
    "services/payment_service":     "payment-service",
    "services/notification_service":"notification-service",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _infer_service_from_path(file_path: str) -> Optional[str]:
    """Return the owning service name for a file path, or None."""
    for prefix, service in FILE_SERVICE_MAP.items():
        if file_path.replace("\\", "/").startswith(prefix):
            return service
    return None


# ---------------------------------------------------------------------------
# Async session helper
# ---------------------------------------------------------------------------

async def _run_query(driver, query: str, **params) -> List[Dict[str, Any]]:
    """
    Execute a Cypher query and return list of record dicts.
    Handles both AsyncDriver (neo4j ≥ 5 async) and sync Driver.
    """
    if driver is None:
        return []

    # Try async driver first (neo4j.AsyncGraphDatabase.driver)
    try:
        async with driver.session() as session:
            result = await session.run(query, **params)
            return await result.data()
    except TypeError:
        pass

    # Fallback: sync driver — run in thread executor
    def _sync():
        with driver.session() as session:
            result = session.run(query, **params)
            return [dict(r) for r in result]

    return await asyncio.to_thread(_sync)


# ---------------------------------------------------------------------------
# DependencyGraph
# ---------------------------------------------------------------------------

class DependencyGraph:
    """
    All Neo4j operations for MDT.
    Every method degrades gracefully when Neo4j is not connected.
    """

    def __init__(self):
        self.driver = get_neo4j_driver()

    def _refresh_driver(self):
        """Re-fetch driver in case it connected after this object was created."""
        if self.driver is None:
            self.driver = get_neo4j_driver()

    # ------------------------------------------------------------------ #
    #  Schema + seeding
    # ------------------------------------------------------------------ #

    async def init_schema(self):
        """Create constraints, indexes, and seed known services."""
        self._refresh_driver()
        if not self.driver:
            logger.warning("Neo4j not available — skipping schema init")
            return

        constraints = [
            "CREATE CONSTRAINT service_name IF NOT EXISTS "
            "FOR (s:Service) REQUIRE s.name IS UNIQUE",

            "CREATE CONSTRAINT file_path IF NOT EXISTS "
            "FOR (f:File) REQUIRE f.path IS UNIQUE",
        ]
        indexes = [
            "CREATE INDEX service_port IF NOT EXISTS "
            "FOR (s:Service) ON (s.port)",
        ]

        for cypher in constraints + indexes:
            try:
                await _run_query(self.driver, cypher)
            except Exception as exc:
                logger.debug("Schema statement skipped: %s", exc)

        logger.info("Neo4j schema initialised")
        await self.seed_known_services()

    async def seed_known_services(self):
        """
        Idempotently populate the graph with the 4 demo microservices
        and their dependency edges.  Safe to run on every startup.
        """
        self._refresh_driver()
        if not self.driver:
            return

        # Upsert service nodes
        for svc in KNOWN_SERVICES:
            await _run_query(
                self.driver,
                """
                MERGE (s:Service {name: $name})
                SET s.port        = $port,
                    s.url         = $url,
                    s.language    = $language,
                    s.description = $description,
                    s.updated_at  = $ts
                """,
                name=svc["name"],
                port=svc["port"],
                url=svc["url"],
                language=svc["language"],
                description=svc["description"],
                ts=_now_iso(),
            )

        # Upsert dependency edges
        for dep in KNOWN_DEPENDENCIES:
            await _run_query(
                self.driver,
                """
                MATCH (from:Service {name: $from_name})
                MATCH (to:Service   {name: $to_name})
                MERGE (from)-[r:DEPENDS_ON {type: $dep_type}]->(to)
                SET r.endpoint   = $endpoint,
                    r.updated_at = $ts
                """,
                from_name=dep["from"],
                to_name=dep["to"],
                dep_type=dep["type"],
                endpoint=dep.get("endpoint", ""),
                ts=_now_iso(),
            )

        logger.info("Graph seeded with %d services and %d dependency edges",
                    len(KNOWN_SERVICES), len(KNOWN_DEPENDENCIES))

    # ------------------------------------------------------------------ #
    #  Service node operations
    # ------------------------------------------------------------------ #

    async def add_service(self, name: str, metadata: Dict[str, Any]):
        """Upsert a service node."""
        self._refresh_driver()
        if not self.driver:
            return
        await _run_query(
            self.driver,
            """
            MERGE (s:Service {name: $name})
            SET s += $metadata, s.updated_at = $ts
            """,
            name=name, metadata=metadata, ts=_now_iso(),
        )

    async def add_dependency(
        self,
        from_service: str,
        to_service: str,
        dependency_type: str = "http",
        endpoint: str = "",
    ):
        """Create or update a DEPENDS_ON edge."""
        self._refresh_driver()
        if not self.driver:
            return
        await _run_query(
            self.driver,
            """
            MATCH (from:Service {name: $from_name})
            MATCH (to:Service   {name: $to_name})
            MERGE (from)-[r:DEPENDS_ON {type: $dep_type}]->(to)
            SET r.endpoint = $endpoint, r.updated_at = $ts
            """,
            from_name=from_service,
            to_name=to_service,
            dep_type=dependency_type,
            endpoint=endpoint,
            ts=_now_iso(),
        )

    # ------------------------------------------------------------------ #
    #  File node operations
    # ------------------------------------------------------------------ #

    async def add_file(self, path: str, service: str, metadata: Dict[str, Any]):
        """Upsert a File node and link it to its owning Service."""
        self._refresh_driver()
        if not self.driver:
            return
        await _run_query(
            self.driver,
            """
            MATCH (s:Service {name: $service})
            MERGE (f:File {path: $path})
            SET f += $metadata,
                f.service    = $service,
                f.last_seen  = $ts
            MERGE (s)-[:DEFINES_FILE]->(f)
            """,
            path=path, service=service, metadata=metadata, ts=_now_iso(),
        )

    # ------------------------------------------------------------------ #
    #  Impact queries
    # ------------------------------------------------------------------ #

    async def get_affected_services(self, file_path: str) -> List[str]:
        """
        Given a changed file path, return all services that could be
        affected — i.e. the owning service PLUS any service that directly
        or transitively depends on it (up to 4 hops).

        Fall-through strategy:
          1. Look up the file in Neo4j → find owning service → find dependants
          2. Infer owning service from path prefix (no Neo4j lookup)
          3. Return all 4 services as a safe maximum (Neo4j unavailable)
        """
        self._refresh_driver()

        if self.driver:
            # Step 1 — graph-aware traversal
            records = await _run_query(
                self.driver,
                """
                MATCH (f:File {path: $path})<-[:DEFINES_FILE]-(owner:Service)
                OPTIONAL MATCH (upstream:Service)-[:DEPENDS_ON*1..4]->(owner)
                WITH owner, collect(DISTINCT upstream.name) AS upstream_names
                RETURN [owner.name] + upstream_names AS affected
                """,
                path=file_path,
            )
            if records and records[0].get("affected"):
                return list(set(records[0]["affected"]))

        # Step 2 — path-prefix inference (no Neo4j needed)
        owner = _infer_service_from_path(file_path)
        if owner:
            return self._get_dependants_from_static_map(owner)

        # Step 3 — safe maximum fallback
        logger.debug("Cannot determine service for %s — returning all services", file_path)
        return [s["name"] for s in KNOWN_SERVICES]

    def _get_dependants_from_static_map(self, service_name: str) -> List[str]:
        """
        Using the hardcoded KNOWN_DEPENDENCIES, return the given service
        plus every service that transitively depends on it.
        """
        affected = {service_name}
        changed = True
        while changed:
            changed = False
            for dep in KNOWN_DEPENDENCIES:
                if dep["to"] in affected and dep["from"] not in affected:
                    affected.add(dep["from"])
                    changed = True
        return list(affected)

    async def get_dependency_chain(
        self, service_name: str, depth: int = 4
    ) -> List[Dict[str, Any]]:
        """
        Return a list of dependency path dicts for a service.
        Each dict: {from, to, type, endpoint}
        """
        self._refresh_driver()
        if not self.driver:
            return self._static_dependency_chain(service_name)

        records = await _run_query(
            self.driver,
            f"""
            MATCH (s:Service {{name: $name}})-[r:DEPENDS_ON*1..{depth}]->(dep:Service)
            UNWIND r AS rel
            WITH startNode(rel) AS from_node, endNode(rel) AS to_node, rel
            RETURN from_node.name AS from,
                   to_node.name   AS to,
                   rel.type       AS type,
                   rel.endpoint   AS endpoint
            """,
            name=service_name,
        )
        return records if records else self._static_dependency_chain(service_name)

    def _static_dependency_chain(self, service_name: str) -> List[Dict[str, Any]]:
        """Return dependency chain from the static map (no Neo4j)."""
        return [
            {"from": d["from"], "to": d["to"],
             "type": d["type"], "endpoint": d.get("endpoint", "")}
            for d in KNOWN_DEPENDENCIES
            if d["from"] == service_name
        ]

    async def get_all_services(self) -> List[Dict[str, Any]]:
        """Return all Service nodes from the graph."""
        self._refresh_driver()
        if not self.driver:
            return KNOWN_SERVICES

        records = await _run_query(
            self.driver,
            "MATCH (s:Service) RETURN s.name AS name, s.port AS port, "
            "s.url AS url, s.description AS description, "
            "s.risk_score AS risk_score, s.risk_level AS risk_level "
            "ORDER BY s.port",
        )
        return records if records else KNOWN_SERVICES

    async def get_service_info(self, name: str) -> Optional[Dict[str, Any]]:
        """Return a single service node's properties."""
        self._refresh_driver()
        if not self.driver:
            return next((s for s in KNOWN_SERVICES if s["name"] == name), None)

        records = await _run_query(
            self.driver,
            "MATCH (s:Service {name: $name}) "
            "RETURN s.name AS name, s.port AS port, s.url AS url, "
            "s.description AS description",
            name=name,
        )
        return records[0] if records else None

    async def get_dependency_depth(self, service_name: str) -> int:
        """
        Return the maximum dependency depth for a service.
        Used by ImpactEngine to score depth-based risk.
        """
        self._refresh_driver()
        if not self.driver:
            # Static calculation
            chain = self._static_dependency_chain(service_name)
            return len(chain)

        records = await _run_query(
            self.driver,
            """
            MATCH (s:Service {name: $name})-[:DEPENDS_ON*]->(dep:Service)
            RETURN count(DISTINCT dep) AS depth
            """,
            name=service_name,
        )
        return records[0]["depth"] if records and records[0].get("depth") else 0

    async def record_analysis(
        self,
        commit_sha: str,
        service_names: List[str],
        risk_score: float,
        severity: str,
        changed_files: List[str],
    ):
        """
        Persist one analysis event linked to every affected service.
        Gives the graph a history of past analyses for future RAG retrieval.
        """
        self._refresh_driver()
        if not self.driver:
            return

        await _run_query(
            self.driver,
            """
            CREATE (a:Analysis {
                commit_sha:    $commit,
                risk_score:    $risk,
                severity:      $severity,
                changed_files: $files,
                created_at:    $ts
            })
            WITH a
            UNWIND $services AS service_name
            MATCH (s:Service {name: service_name})
            CREATE (s)-[:HAS_ANALYSIS]->(a)
            SET s.risk_score       = $risk,
                s.risk_level       = $severity,
                s.last_analyzed_at = $ts
            """,
            services=service_names,
            commit=commit_sha,
            risk=risk_score,
            severity=severity,
            files=changed_files,
            ts=_now_iso(),
        )
        logger.debug("Recorded analysis for %s commit=%s", service_names, commit_sha)

    async def get_analysis_history(
        self, limit: int = 20, service: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Return persisted analysis events, newest first."""
        self._refresh_driver()
        if not self.driver:
            return []

        return await _run_query(
            self.driver,
            """
            MATCH (s:Service)-[:HAS_ANALYSIS]->(a:Analysis)
            WITH a, collect(s.name) AS services
            WHERE $service IS NULL OR $service IN services
            RETURN a.commit_sha AS commit,
                   a.risk_score AS risk_score,
                   a.severity AS severity,
                   a.changed_files AS changed_files,
                   a.created_at AS timestamp,
                   services
            ORDER BY timestamp DESC
            LIMIT $limit
            """,
            limit=limit,
            service=service,
        )
