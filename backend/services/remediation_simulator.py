"""What-If Remediation Simulator — sandbox graph edits with rollback.

Executes structured graph edits (add_node, add_edge, remove_edge) inside a
Neo4j transaction, re-scores smells and risk, then unconditionally rolls back.
The live graph is **never** modified.

For local/test environments running MockNeo4jDriver the simulator falls back
to a deterministic in-memory estimation so the feature is always available.
"""
import asyncio
from collections import defaultdict
import logging
from typing import Any, Dict, List, Literal, Optional, Tuple

from pydantic import BaseModel

from core.config import settings
from core.database import get_neo4j_driver, MockNeo4jDriver

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

class GraphEdit(BaseModel):
    """A single graph mutation primitive."""
    action: Literal["remove_edge", "add_edge", "add_node"]
    from_service: Optional[str] = None
    to_service: Optional[str] = None
    relationship_type: str = "DEPENDS_ON"


# ---------------------------------------------------------------------------
# Inline smell-counting Cypher (runs on a tx, not through _run_query)
# ---------------------------------------------------------------------------

_SMELL_QUERIES: Dict[str, Dict[str, str]] = {
    "circular_dependency": {
        "query": """
            MATCH path = (s:Service)-[:DEPENDS_ON*2..8]->(s)
            WHERE NOT s.name ENDS WITH '_facade' AND NOT s.name ENDS WITH '_gateway' AND NOT s.name = 'event_broker'
              AND NONE(n IN nodes(path) WHERE n.name ENDS WITH '_facade' OR n.name ENDS WITH '_gateway' OR n.name = 'event_broker')
            WITH [node IN nodes(path) | node.name] AS cycle
            WITH cycle, apoc.coll.sort(apoc.coll.toSet(cycle)) AS key
            RETURN DISTINCT key, cycle
        """,
        # Fallback for environments without APOC
        "query_no_apoc": """
            MATCH path = (s:Service)-[:DEPENDS_ON*2..8]->(s)
            WHERE NOT s.name ENDS WITH '_facade' AND NOT s.name ENDS WITH '_gateway' AND NOT s.name = 'event_broker'
              AND NONE(n IN nodes(path) WHERE n.name ENDS WITH '_facade' OR n.name ENDS WITH '_gateway' OR n.name = 'event_broker')
            WITH [node IN nodes(path) | node.name] AS cycle
            RETURN DISTINCT cycle
        """,
    },
    "bottleneck_service": {
        "query": """
            MATCH (s:Service)
            WHERE NOT s.name ENDS WITH '_facade' AND NOT s.name ENDS WITH '_gateway' AND NOT s.name = 'event_broker'
              AND NOT toLower(s.name) CONTAINS 'postgres' AND NOT toLower(s.name) CONTAINS 'database' AND NOT toLower(s.name) CONTAINS 'db'
            OPTIONAL MATCH (incoming:Service)-[:DEPENDS_ON]->(s)
            WHERE incoming <> s AND NOT incoming.name ENDS WITH '_facade' AND NOT incoming.name ENDS WITH '_gateway' AND NOT incoming.name = 'event_broker'
            OPTIONAL MATCH (s)-[:DEPENDS_ON]->(outgoing:Service)
            WHERE outgoing <> s AND NOT outgoing.name ENDS WITH '_facade' AND NOT outgoing.name ENDS WITH '_gateway' AND NOT outgoing.name = 'event_broker'
            WITH s, count(DISTINCT incoming) AS inc, count(DISTINCT outgoing) AS out
            WHERE inc >= $inbound OR inc + out >= $total
            RETURN s.name AS name, inc, out
        """,
    },
    "high_coupling": {
        "query": """
            MATCH (s:Service)-[:DEPENDS_ON]->(dep:Service)
            WHERE dep <> s
              AND NOT s.name ENDS WITH '_facade' AND NOT s.name ENDS WITH '_gateway' AND NOT s.name = 'event_broker'
            WITH s, count(DISTINCT dep) AS dep_count
            WHERE dep_count >= $threshold
            RETURN s.name AS name, dep_count
        """,
    },
    "isolated_service": {
        "query": """
            MATCH (s:Service)
            WHERE NOT s.name ENDS WITH '_facade' AND NOT s.name ENDS WITH '_gateway' AND NOT s.name = 'event_broker'
              AND NOT (s)-[:DEPENDS_ON]->() AND NOT ()-[:DEPENDS_ON]->(s)
              AND (s.is_external IS NULL OR s.is_external = false OR NOT s.name STARTS WITH 'external-')
            RETURN s.name AS name
        """,
    },
    "shared_database": {
        "query": """
            MATCH (caller:Service)-[r:DEPENDS_ON]->(target)
            WHERE toLower(target.name) CONTAINS 'db'
               OR toLower(target.name) CONTAINS 'database'
               OR toLower(target.name) CONTAINS 'postgres'
               OR toLower(target.name) CONTAINS 'mysql'
               OR toLower(target.name) CONTAINS 'mongo'
               OR toLower(target.name) CONTAINS 'redis'
               OR toLower(coalesce(r.type, '')) IN ['database', 'db', 'sql', 'postgres', 'postgresql', 'mysql', 'mongodb']
               OR coalesce(r.endpoint, '') CONTAINS ':5432' OR coalesce(r.endpoint, '') CONTAINS ':3306'
               OR coalesce(r.endpoint, '') CONTAINS ':27017' OR coalesce(r.endpoint, '') CONTAINS ':6379'
            WITH toLower(target.name) AS db_target, count(DISTINCT caller) AS caller_count
            WHERE caller_count > 1
            RETURN db_target, caller_count
        """,
    },
    "chatty_communication": {
        "query": """
            MATCH (a:Service)-[:DEPENDS_ON]->(b:Service)
            WHERE a <> b AND (b)-[:DEPENDS_ON]->(a) AND a.name < b.name
              AND NOT a.name ENDS WITH '_facade' AND NOT a.name ENDS WITH '_gateway' AND NOT a.name = 'event_broker'
              AND NOT b.name ENDS WITH '_facade' AND NOT b.name ENDS WITH '_gateway' AND NOT b.name = 'event_broker'
            MATCH (x:Service)-[r:DEPENDS_ON]-(y:Service)
            WHERE (x = a AND y = b) OR (x = b AND y = a)
            WITH a.name AS a_name, b.name AS b_name, count(DISTINCT r) AS edge_count
            RETURN a_name, b_name, edge_count
        """,
    },
    "missing_circuit_breaker": {
        "query": """
            MATCH (all_s:Service)
            WHERE NOT all_s.name ENDS WITH '_facade' AND NOT all_s.name ENDS WITH '_gateway' AND NOT all_s.name = 'event_broker'
              AND NOT toLower(all_s.name) CONTAINS 'postgres' AND NOT toLower(all_s.name) CONTAINS 'database' AND NOT toLower(all_s.name) CONTAINS 'db'
            WITH count(DISTINCT all_s) AS total_services
            WITH total_services,
                 CASE 
                   WHEN total_services <= 2 THEN 2
                   ELSE toInteger(ceil(sqrt(total_services)))
                 END AS cb_threshold
            MATCH (s:Service)-[:DEPENDS_ON]->(dep:Service)
            WHERE dep <> s
              AND NOT s.name ENDS WITH '_facade' AND NOT s.name ENDS WITH '_gateway' AND NOT s.name = 'event_broker'
              AND NOT toLower(s.name) CONTAINS 'postgres' AND NOT toLower(s.name) CONTAINS 'database' AND NOT toLower(s.name) CONTAINS 'db'
              AND NOT dep.name ENDS WITH '_facade' AND NOT dep.name ENDS WITH '_gateway' AND NOT dep.name = 'event_broker'
              AND NOT toLower(dep.name) CONTAINS 'postgres' AND NOT toLower(dep.name) CONTAINS 'database' AND NOT toLower(dep.name) CONTAINS 'db'
              AND coalesce(s.has_circuit_breaker, false) = false AND coalesce(s.resilient, false) = false
            WITH s, cb_threshold, count(DISTINCT dep) AS fan_out
            WHERE fan_out >= cb_threshold
            RETURN s.name AS name, fan_out
        """,
    },
    "hub_and_spoke": {
        "query": """
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
                     WHEN (1.0 - 1.0/sqrt(total_services)) > 0.60 THEN (1.0 - 1.0/sqrt(total_services)) 
                     ELSE 0.60 
                   END * (total_services - 1)
                 )) AS min_hub_deg
            UNWIND svc_degrees AS item
            WITH item.service AS s, item.deg AS deg, total_services, avg_deg, min_hub_deg
            WHERE deg >= min_hub_deg AND deg > avg_deg
            RETURN s.name AS name, deg
        """,
    },
}


def _count_smells_on_tx(tx) -> Dict[str, int]:
    """Run lightweight smell-counting queries on an open transaction.

    Returns a dict like ``{"circular_dependency": 1, "bottleneck_service": 0, ...}``.
    """
    counts: Dict[str, int] = {}
    two_node_cycles: set = set()

    # --- Circular dependencies ---
    try:
        result = tx.run(_SMELL_QUERIES["circular_dependency"]["query_no_apoc"])
        records = [dict(r) for r in result]
        seen: set = set()
        unique = 0
        for rec in records:
            cycle = rec.get("cycle", [])
            if not cycle or len(cycle) < 3:
                continue
            cycle_nodes = cycle[:-1]
            if len(cycle_nodes) != len(set(cycle_nodes)) or len(cycle_nodes) < 2:
                continue
            if any(n.endswith("_facade") or n.endswith("_gateway") or n == "event_broker" for n in cycle_nodes):
                continue
            min_idx = cycle_nodes.index(min(cycle_nodes))
            canonical = cycle_nodes[min_idx:] + cycle_nodes[:min_idx]
            key = tuple(canonical)
            if len(cycle_nodes) == 2:
                two_node_cycles.add(tuple(sorted([cycle_nodes[0], cycle_nodes[1]])))
            if key not in seen:
                seen.add(key)
                unique += 1
        counts["circular_dependency"] = unique
    except Exception as exc:
        logger.debug("Cycle query failed: %s", exc)
        counts["circular_dependency"] = 0

    # --- Bottleneck services ---
    try:
        result = tx.run(
            _SMELL_QUERIES["bottleneck_service"]["query"],
            inbound=settings.SMELL_BOTTLENECK_INBOUND_THRESHOLD,
            total=settings.SMELL_BOTTLENECK_TOTAL_DEGREE_THRESHOLD,
        )
        counts["bottleneck_service"] = len([dict(r) for r in result])
    except Exception as exc:
        logger.debug("Bottleneck query failed: %s", exc)
        counts["bottleneck_service"] = 0

    # --- High coupling ---
    try:
        result = tx.run(
            _SMELL_QUERIES["high_coupling"]["query"],
            threshold=settings.SMELL_HIGH_COUPLING_THRESHOLD,
        )
        counts["high_coupling"] = len([dict(r) for r in result])
    except Exception as exc:
        logger.debug("Coupling query failed: %s", exc)
        counts["high_coupling"] = 0

    # --- Isolated services ---
    try:
        result = tx.run(_SMELL_QUERIES["isolated_service"]["query"])
        counts["isolated_service"] = len([dict(r) for r in result])
    except Exception as exc:
        logger.debug("Isolation query failed: %s", exc)
        counts["isolated_service"] = 0

    if counts["isolated_service"] == 0:
        # Fallback to in-memory registry check if isolated nodes were not in Neo4j
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
            isolated_cnt = 0
            for svc in services:
                name = svc.get("name")
                if not name or name in connected:
                    continue
                if svc.get("is_external") and name.startswith("external-"):
                    continue
                if name.endswith("_facade") or name.endswith("_gateway") or name == "event_broker":
                    continue
                isolated_cnt += 1
            if isolated_cnt > 0:
                counts["isolated_service"] = isolated_cnt
        except Exception as exc:
            logger.debug("In-memory isolated service fallback failed: %s", exc)

    # --- Shared database ---
    try:
        result = tx.run(_SMELL_QUERIES["shared_database"]["query"])
        counts["shared_database"] = len([dict(r) for r in result])
    except Exception as exc:
        logger.debug("Shared DB query failed: %s", exc)
        counts["shared_database"] = 0

    if counts["shared_database"] == 0:
        # Fallback to in-memory registry check if database nodes were not in Neo4j
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
            shared_cnt = sum(1 for callers in db_targets.values() if len(set(callers)) > 1)
            if shared_cnt > 0:
                counts["shared_database"] = shared_cnt
        except Exception as exc:
            logger.debug("In-memory shared database fallback failed: %s", exc)

    # --- Chatty communication ---
    try:
        result = tx.run(_SMELL_QUERIES["chatty_communication"]["query"])
        records = [dict(r) for r in result]
        chatty_count = 0
        for rec in records:
            pair = tuple(sorted([rec.get("a_name", ""), rec.get("b_name", "")]))
            edge_count = rec.get("edge_count", 2)
            # Match smell_detector: if this pair is a 2-node cycle, require >= 3 edges to count as chatty
            if pair in two_node_cycles and edge_count < 3:
                continue
            chatty_count += 1
        counts["chatty_communication"] = chatty_count
    except Exception as exc:
        logger.debug("Chatty query failed: %s", exc)
        counts["chatty_communication"] = 0

    # --- Missing circuit breaker ---
    try:
        result = tx.run(_SMELL_QUERIES["missing_circuit_breaker"]["query"])
        counts["missing_circuit_breaker"] = len([dict(r) for r in result])
    except Exception as exc:
        logger.debug("Circuit breaker query failed: %s", exc)
        counts["missing_circuit_breaker"] = 0

    # --- Hub and spoke ---
    try:
        result = tx.run(_SMELL_QUERIES["hub_and_spoke"]["query"])
        counts["hub_and_spoke"] = len([dict(r) for r in result])
    except Exception as exc:
        logger.debug("Hub and spoke query failed: %s", exc)
        counts["hub_and_spoke"] = 0

    # --- Snapshot-based trend smells on transaction ---
    from core.registry import RegistryManager, LOCAL_DEMO_SMELL_HISTORY
    context = RegistryManager.get_project_context()
    is_demo = context.get("source") == "local_demo"
    active_services = {s["name"] for s in RegistryManager.get_services()}

    try:
        snap_res = tx.run("""
            MATCH (snapshot:DependencySnapshot)
            RETURN snapshot.edges AS edges, snapshot.created_at AS created_at
            ORDER BY created_at DESC
        """)
        snap_records = [dict(r) for r in snap_res]
        if len(snap_records) < 2:
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
                    snap_records = sorted(raw_snapshots, key=lambda s: s.get("created_at", ""), reverse=True)
            except Exception as exc:
                logger.debug("In-memory dependency snapshot fallback failed: %s", exc)

        if len(snap_records) >= 2:
            filtered_snaps = []
            for rec in snap_records:
                edges = [
                    e for e in rec.get("edges", [])
                    if "->" in e and e.split("->", 1)[0] in active_services
                ]
                if edges or is_demo:
                    filtered_snaps.append(edges if active_services else rec.get("edges", []))
            if len(filtered_snaps) >= 2:
                current = set(filtered_snaps[0])
                prev_edges = None
                for pe in filtered_snaps[1:]:
                    pe_set = set(pe)
                    if pe_set != current:
                        prev_edges = pe_set
                        break
                if prev_edges is not None:
                    added = current - prev_edges
                    counts["dependency_explosion"] = 1 if len(added) >= settings.SMELL_DEPENDENCY_GROWTH_THRESHOLD else 0
                else:
                    counts["dependency_explosion"] = 0
            else:
                counts["dependency_explosion"] = 0
        else:
            counts["dependency_explosion"] = 0
    except Exception as exc:
        logger.debug("Snapshot growth query failed: %s", exc)
        counts["dependency_explosion"] = 0

    try:
        api_res = tx.run("""
            MATCH (snapshot:ApiSnapshot)
            RETURN snapshot.service AS service, snapshot.endpoints AS endpoints,
                   snapshot.created_at AS created_at
            ORDER BY service, created_at DESC
        """)
        api_records = [dict(r) for r in api_res]
        if not api_records:
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
                    api_records = sorted(raw_snaps, key=lambda s: s.get("created_at", ""), reverse=True)
            except Exception as exc:
                logger.debug("In-memory API snapshot fallback failed: %s", exc)

        if active_services:
            api_records = [r for r in api_records if r.get("service") in active_services]

        api_snapshots: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for r in api_records:
            svc = r.get("service")
            if svc and len(api_snapshots[svc]) < 2:
                api_snapshots[svc].append(r)
        instability_count = 0
        for svc, vals in api_snapshots.items():
            if len(vals) >= 2:
                curr, prev = set(vals[0].get("endpoints") or []), set(vals[1].get("endpoints") or [])
                removed = prev - curr
                churn = len(removed) + len(curr - prev)
                if removed or churn >= settings.SMELL_API_CHURN_THRESHOLD:
                    instability_count += 1
        counts["api_instability"] = instability_count
    except Exception as exc:
        logger.debug("Api snapshot query failed: %s", exc)
        counts["api_instability"] = 0

    return counts


def _apply_edits_on_tx(tx, edits: List[GraphEdit]) -> None:
    """Execute GraphEdit primitives as Cypher mutations on ``tx``."""
    for edit in edits:
        if edit.action == "add_node" and edit.from_service:
            tx.run(
                "MERGE (s:Service {name: $name}) "
                "SET s.has_circuit_breaker = true, s.resilient = true",
                name=edit.from_service,
            )

        elif edit.action == "add_edge" and edit.from_service and edit.to_service:
            tx.run(
                "MERGE (a:Service {name: $from_}) "
                "MERGE (b:Service {name: $to_}) "
                "MERGE (a)-[r:DEPENDS_ON {type: $rel}]->(b)",
                from_=edit.from_service,
                to_=edit.to_service,
                rel=edit.relationship_type,
            )
            # Remove any internal self-loop on the target service to eliminate cyclic loops
            tx.run(
                "MATCH (target:Service {name: $to_})-[self_r:DEPENDS_ON]->(target) "
                "DELETE self_r",
                to_=edit.to_service,
            )
            # Ingress facade / bottleneck: reroute external incoming callers through the facade
            if "_facade" in edit.from_service:
                tx.run(
                    "MATCH (facade:Service {name: $from_}) "
                    "MATCH (caller:Service)-[r:DEPENDS_ON]->(target:Service {name: $to_}) "
                    "WHERE caller.name <> $from_ AND caller.name <> $to_ "
                    "MERGE (caller)-[:DEPENDS_ON {type: 'FACADE_ROUTED'}]->(facade) "
                    "DELETE r",
                    from_=edit.from_service,
                    to_=edit.to_service,
                )
                tx.run(
                    "MATCH (s:Service {name: $to_}) "
                    "SET s.has_circuit_breaker = true, s.resilient = true",
                    to_=edit.to_service,
                )
            # Egress gateway / coupling: rewire downstream calls through the gateway to decouple
            if "_gateway" in edit.from_service:
                tx.run(
                    "MATCH (gateway:Service {name: $from_}) "
                    "MATCH (target:Service {name: $to_})-[r:DEPENDS_ON]->(downstream:Service) "
                    "WHERE downstream.name <> $from_ AND downstream.name <> $to_ "
                    "MERGE (gateway)-[:DEPENDS_ON {type: 'GATEWAY_DECOUPLED'}]->(downstream) "
                    "DELETE r",
                    from_=edit.from_service,
                    to_=edit.to_service,
                )
                tx.run(
                    "MATCH (s:Service {name: $to_}) "
                    "SET s.has_circuit_breaker = true, s.resilient = true",
                    to_=edit.to_service,
                )
            if "_gateway" in edit.to_service or "_facade" in edit.to_service:
                tx.run(
                    "MATCH (target:Service {name: $from_}) "
                    "MATCH (gateway:Service {name: $to_}) "
                    "MATCH (target)-[r:DEPENDS_ON]->(downstream:Service) "
                    "WHERE downstream.name <> $to_ AND downstream.name <> $from_ "
                    "MERGE (gateway)-[:DEPENDS_ON {type: 'GATEWAY_ROUTED'}]->(downstream) "
                    "DELETE r",
                    from_=edit.from_service,
                    to_=edit.to_service,
                )
                tx.run(
                    "MATCH (s:Service {name: $from_}) "
                    "SET s.has_circuit_breaker = true, s.resilient = true",
                    from_=edit.from_service,
                )

        elif edit.action == "remove_edge" and edit.from_service and edit.to_service:
            tx.run(
                "MATCH (a:Service {name: $from_})-[r:DEPENDS_ON]->"
                "(b:Service {name: $to_}) DELETE r",
                from_=edit.from_service,
                to_=edit.to_service,
            )


def _compute_score_from_smells(smell_counts: Dict[str, int]) -> float:
    """Derive a normalized architectural risk score from smell counts [0.0, 100.0).

    Synchronized with _compute_uncapped_score_from_smells and _normalize_score.
    """
    return _normalize_score(_compute_uncapped_score_from_smells(smell_counts))


def _get_severity(score: float) -> str:
    if score >= settings.RISK_HIGH:
        return "CRITICAL"
    elif score >= settings.RISK_MEDIUM:
        return "HIGH"
    elif score >= settings.RISK_LOW:
        return "MEDIUM"
    return "LOW"


# ---------------------------------------------------------------------------
# Dynamic remediation target finder
# ---------------------------------------------------------------------------

def _find_best_remediation_target(exclude_service: str) -> str:
    """Dynamically select a hub or active non-isolated service to re-link an isolated service."""
    try:
        from core.registry import RegistryManager
        registered = [
            s["name"] for s in RegistryManager.get_services()
            if s.get("name") and s.get("name") != exclude_service
        ]
        if not registered:
            return ""

        # Check degree in existing dependencies
        deps = RegistryManager.get_dependencies()
        degree: Dict[str, int] = {s: 0 for s in registered}
        for d in deps:
            src = d.get("from")
            dst = d.get("to")
            if src in degree:
                degree[src] += 1
            if dst in degree:
                degree[dst] += 1

        sorted_by_degree = sorted(degree.items(), key=lambda x: x[1], reverse=True)
        return sorted_by_degree[0][0]
    except Exception as exc:
        logger.debug("Failed to find dynamic remediation target from registry: %s", exc)
        return ""


def generate_edits_for_smells(smells: List[Dict[str, Any]]) -> List[GraphEdit]:
    """
    Deterministic rule-based mapping from detected smells to graph edits.

    - Circular: remove the back-edge that closes the cycle.
    - God/Bottleneck: insert a facade node and rewire callers.
    - High Coupling: insert a gateway facade.
    - Dead/Isolated: reconnect the isolated node to an active hub service.
    """
    edits: List[GraphEdit] = []

    for smell in smells:
        stype = smell.get("type", "")
        services = smell.get("services", [])

        if "Circular" in stype:
            cycle = smell.get("evidence", {}).get("cycle", [])
            if len(cycle) >= 2:
                edits.append(GraphEdit(
                    action="remove_edge",
                    from_service=cycle[-2],
                    to_service=cycle[-1] if cycle[-1] != cycle[-2] else cycle[0],
                ))
            elif len(services) >= 2:
                edits.append(GraphEdit(
                    action="remove_edge",
                    from_service=services[1],
                    to_service=services[0],
                ))

        elif "Bottleneck" in stype or "God" in stype:
            if services:
                target = services[0]
                facade_name = f"{target}_facade"
                edits.append(GraphEdit(action="add_node", from_service=facade_name))
                edits.append(GraphEdit(
                    action="add_edge",
                    from_service=facade_name,
                    to_service=target,
                ))

        elif "Coupling" in stype:
            if services:
                coupled = services[0]
                facade_name = f"{coupled}_gateway"
                edits.append(GraphEdit(action="add_node", from_service=facade_name))
                edits.append(GraphEdit(
                    action="add_edge",
                    from_service=facade_name,
                    to_service=coupled,
                ))

        elif "Dead" in stype or "Isolated" in stype:
            if services:
                isolated = services[0]
                target_hub = _find_best_remediation_target(isolated)
                if target_hub:
                    edits.append(GraphEdit(
                        action="add_edge",
                        from_service=target_hub,
                        to_service=isolated,
                    ))

        elif "Shared Database" in stype:
            target = smell.get("evidence", {}).get("shared_target", "")
            if target and len(services) >= 2:
                facade = f"{services[0]}_data_facade"
                edits.append(GraphEdit(action="add_node", from_service=facade))
                edits.append(GraphEdit(action="add_edge", from_service=services[1], to_service=facade))
                edits.append(GraphEdit(action="remove_edge", from_service=services[1], to_service=target))

        elif "Chatty" in stype:
            if len(services) >= 2:
                broker = "event_broker"
                edits.append(GraphEdit(action="add_node", from_service=broker))
                edits.append(GraphEdit(action="add_edge", from_service=services[0], to_service=broker))
                edits.append(GraphEdit(action="add_edge", from_service=services[1], to_service=broker))
                edits.append(GraphEdit(action="remove_edge", from_service=services[1], to_service=services[0]))

        elif "Circuit Breaker" in stype:
            if services:
                src = services[0]
                gateway_name = f"{src}_gateway"
                edits.append(GraphEdit(action="add_node", from_service=gateway_name))
                edits.append(GraphEdit(action="add_edge", from_service=gateway_name, to_service=src))

        elif "Hub-and-Spoke" in stype or "Hub and Spoke" in stype:
            if services:
                hub = services[0]
                broker = "event_broker"
                edits.append(GraphEdit(action="add_node", from_service=broker))
                edits.append(GraphEdit(action="add_edge", from_service=hub, to_service=broker))

    return edits



def _compute_uncapped_score_from_smells(smell_counts: Dict[str, int]) -> float:
    """Calculate raw sum of smell weights without capping at 100.
    
    Weights mirror relative severities across all 10 architectural smell types:
      - circular_dependency: 30 (CRITICAL)
      - shared_database: 20 (HIGH)
      - hub_and_spoke: 20 (HIGH)
      - bottleneck_service: 20 (HIGH)
      - dependency_explosion: 20 (HIGH)
      - high_coupling: 15 (MEDIUM)
      - api_instability: 15 (MEDIUM)
      - chatty_communication: 12 (MEDIUM)
      - missing_circuit_breaker: 12 (MEDIUM)
      - isolated_service: 5 (LOW)
    """
    score = 0.0
    score += smell_counts.get("circular_dependency", 0) * 30      # CRITICAL
    score += smell_counts.get("shared_database", 0) * 20          # HIGH
    score += smell_counts.get("hub_and_spoke", 0) * 20            # HIGH
    score += smell_counts.get("bottleneck_service", 0) * 20       # HIGH
    score += smell_counts.get("dependency_explosion", 0) * 20     # HIGH
    score += smell_counts.get("high_coupling", 0) * 15            # MEDIUM
    score += smell_counts.get("api_instability", 0) * 15          # MEDIUM
    score += smell_counts.get("chatty_communication", 0) * 12     # MEDIUM
    score += smell_counts.get("missing_circuit_breaker", 0) * 12  # MEDIUM
    score += smell_counts.get("isolated_service", 0) * 5          # LOW
    return score


# Deliberately chosen anchor point: a single critical circular dependency (raw=30)
# corresponds to a moderate MEDIUM risk score of 45.0 on the 0-100 scale.
# Solving: 45 = 100 * (30 / (30 + k)) => 45 * 30 + 45 * k = 3000 => k = 1650 / 45 = 110 / 3 ≈ 36.6667
SATURATION_CONSTANT_K: float = 110.0 / 3.0


def _normalize_score(raw: float, k: float = SATURATION_CONSTANT_K) -> float:
    """Monotonically map an unbounded non-negative raw smell score to [0.0, 100.0).

    Uses a saturating rational function S(R) = 100 * R / (R + k).
    Ensures that distinct raw smell values strictly produce distinct normalized scores,
    preventing score ties when raw debt exceeds 100.
    """
    if raw <= 0.0:
        return 0.0
    return round((100.0 * raw) / (raw + k), 1)


def compute_architecture_health(smell_counts: Dict[str, int]) -> Dict[str, Any]:
    """Single canonical function to calculate the Architecture Health score and severity from smell counts.

    Used by both the main Architecture Health dial and the Simulator Before/After gauges
    to guarantee 100% mathematical and topological parity across the entire application.
    """
    raw = _compute_uncapped_score_from_smells(smell_counts)
    score = _normalize_score(raw)
    severity = _get_severity(score)
    return {
        "score": score,
        "severity": severity,
        "raw_score": raw,
        "total_smells": sum(smell_counts.values()),
        "smells": smell_counts,
    }


def breakdown_smells(smells: List[Dict[str, Any]]) -> Dict[str, int]:
    """Map a list of detected smell findings to canonical smell count keys."""
    counts: Dict[str, int] = {
        "circular_dependency": 0,
        "shared_database": 0,
        "hub_and_spoke": 0,
        "bottleneck_service": 0,
        "dependency_explosion": 0,
        "high_coupling": 0,
        "api_instability": 0,
        "chatty_communication": 0,
        "missing_circuit_breaker": 0,
        "isolated_service": 0,
    }
    for s in smells:
        stype = s.get("type", "")
        if "Circular" in stype:
            counts["circular_dependency"] += 1
        elif "Shared Database" in stype:
            counts["shared_database"] += 1
        elif "Hub-and-Spoke" in stype or "Hub and Spoke" in stype:
            counts["hub_and_spoke"] += 1
        elif "Bottleneck" in stype or "God" in stype:
            counts["bottleneck_service"] += 1
        elif "Dependency Explosion" in stype:
            counts["dependency_explosion"] += 1
        elif "API Instability" in stype:
            counts["api_instability"] += 1
        elif "Coupling" in stype:
            counts["high_coupling"] += 1
        elif "Chatty" in stype:
            counts["chatty_communication"] += 1
        elif "Circuit Breaker" in stype:
            counts["missing_circuit_breaker"] += 1
        elif "Isolated" in stype or "Dead" in stype:
            counts["isolated_service"] += 1
    return counts


def _calculate_simulation_metrics(
    before_smells: Dict[str, int],
    after_smells: Dict[str, int],
    edits: List[GraphEdit],
) -> Tuple[float, float, float, bool, str]:
    """Calculate before_score, after_score, point_reduction, measurable_change, and message for pure architectural smell risk."""
    before_health = compute_architecture_health(before_smells)
    after_health = compute_architecture_health(after_smells)

    before_score = before_health["score"]
    before_total = before_health["total_smells"]
    after_total = after_health["total_smells"]
    smells_resolved = max(0, before_total - after_total)

    cycles_resolved = max(0, before_smells.get("circular_dependency", 0) - after_smells.get("circular_dependency", 0))
    shared_db_resolved = max(0, before_smells.get("shared_database", 0) - after_smells.get("shared_database", 0))
    hub_resolved = max(0, before_smells.get("hub_and_spoke", 0) - after_smells.get("hub_and_spoke", 0))
    bottlenecks_resolved = max(0, before_smells.get("bottleneck_service", 0) - after_smells.get("bottleneck_service", 0))
    coupling_resolved = max(0, before_smells.get("high_coupling", 0) - after_smells.get("high_coupling", 0))
    chatty_resolved = max(0, before_smells.get("chatty_communication", 0) - after_smells.get("chatty_communication", 0))
    cb_resolved = max(0, before_smells.get("missing_circuit_breaker", 0) - after_smells.get("missing_circuit_breaker", 0))
    isolated_resolved = max(0, before_smells.get("isolated_service", 0) - after_smells.get("isolated_service", 0))
    dep_growth_resolved = max(0, before_smells.get("dependency_explosion", 0) - after_smells.get("dependency_explosion", 0))
    api_instability_resolved = max(0, before_smells.get("api_instability", 0) - after_smells.get("api_instability", 0))

    after_score = after_health["score"]
    point_reduction = round(before_score - after_score, 1)

    smells_changed = any(before_smells.get(k, 0) != after_smells.get(k, 0) for k in set(before_smells) | set(after_smells))
    measurable_change = (point_reduction != 0.0) or (smells_resolved > 0) or (after_total != before_total) or smells_changed

    details = []
    if cycles_resolved > 0:
        details.append(f"{cycles_resolved} circular dependency resolved")
    if shared_db_resolved > 0:
        details.append(f"{shared_db_resolved} shared database resolved")
    if hub_resolved > 0:
        details.append(f"{hub_resolved} hub-and-spoke resolved")
    if bottlenecks_resolved > 0:
        details.append(f"{bottlenecks_resolved} bottleneck resolved")
    if coupling_resolved > 0:
        details.append(f"{coupling_resolved} coupling resolved")
    if chatty_resolved > 0:
        details.append(f"{chatty_resolved} chatty communication resolved")
    if cb_resolved > 0:
        details.append(f"{cb_resolved} missing circuit breaker resolved")
    if isolated_resolved > 0:
        details.append(f"{isolated_resolved} isolated service resolved")
    if dep_growth_resolved > 0:
        details.append(f"{dep_growth_resolved} dependency explosion resolved")
    if api_instability_resolved > 0:
        details.append(f"{api_instability_resolved} API instability resolved")
    if not details and point_reduction > 0:
        details.append("architectural remediation applied")

    if point_reduction > 0:
        if details:
            message = f"Risk reduction verified: {', '.join(details)} (-{point_reduction} pts smell risk)"
        else:
            message = f"Risk reduction verified: -{point_reduction} pts smell risk"
    elif point_reduction < 0:
        point_increase = abs(point_reduction)
        smells_added = max(0, after_total - before_total)
        if smells_added > 0:
            message = f"Warning: Proposed edit increases architectural risk by +{point_increase} pts ({smells_added} new smell(s) introduced)"
        else:
            message = f"Warning: Proposed edit increases architectural risk by +{point_increase} pts"
    elif measurable_change:
        message = "Smell reduction verified"
    else:
        message = "No measurable change in tracked architectural smells"

    return before_score, after_score, point_reduction, measurable_change, message




# ---------------------------------------------------------------------------
# Main Simulator
# ---------------------------------------------------------------------------

class RemediationSimulator:
    """Execute what-if graph edits in a sandboxed Neo4j transaction."""

    def __init__(self):
        self.driver = get_neo4j_driver()

    def _is_mock(self) -> bool:
        return isinstance(self.driver, MockNeo4jDriver) or self.driver is None

    # ------------------------------------------------------------------ #
    #  Public API
    # ------------------------------------------------------------------ #

    async def simulate_fix(
        self,
        edits: List[GraphEdit],
        baseline_risk_score: Optional[float] = None,
        affected_files_count: Optional[int] = None,
        baseline_smells: Optional[Dict[str, int]] = None,
    ) -> Dict[str, Any]:
        """Run edits in a sandbox and return before/after comparison.

        Returns a dict with keys: before, after, delta, commit_risk, sandbox.
        """
        if self._is_mock():
            return await self._simulate_mock(
                edits,
                baseline_risk_score=baseline_risk_score,
                affected_files_count=affected_files_count,
                baseline_smells=baseline_smells,
            )
        return await self._simulate_live(
            edits,
            baseline_risk_score=baseline_risk_score,
            affected_files_count=affected_files_count,
            baseline_smells=baseline_smells,
        )


    # ------------------------------------------------------------------ #
    #  Live Neo4j mode
    # ------------------------------------------------------------------ #

    async def _simulate_live(
        self,
        edits: List[GraphEdit],
        baseline_risk_score: Optional[float] = None,
        affected_files_count: Optional[int] = None,
        baseline_smells: Optional[Dict[str, int]] = None,
    ) -> Dict[str, Any]:
        """Transactional simulation on a real Neo4j instance."""

        def _run_in_tx():
            assert self.driver is not None
            with self.driver.session() as session:
                tx = session.begin_transaction()
                try:
                    # 1. Use the canonical baseline smells already computed by SmellDetector
                    if baseline_smells:
                        before_smells = dict(baseline_smells)
                    else:
                        before_smells = _count_smells_on_tx(tx)

                    # 2. Apply edits
                    _apply_edits_on_tx(tx, edits)

                    # 3. Measure AFTER state: evaluate structural changes on tx and preserve baseline historical smells
                    tx_smells = _count_smells_on_tx(tx)
                    after_smells = dict(before_smells)
                    structural_keys = [
                        "circular_dependency", "bottleneck_service", "high_coupling",
                        "chatty_communication", "missing_circuit_breaker", "hub_and_spoke",
                        "shared_database", "isolated_service"
                    ]
                    for k in structural_keys:
                        after_smells[k] = tx_smells.get(k, 0)

                    return before_smells, after_smells
                finally:
                    # ALWAYS rollback — the graph is never mutated
                    tx.rollback()

        before_smells, after_smells = await asyncio.to_thread(_run_in_tx)

        before_score, after_score, point_reduction, measurable_change, message = _calculate_simulation_metrics(
            before_smells, after_smells, edits
        )

        before_total = sum(before_smells.values())
        after_total = sum(after_smells.values())

        commit_risk = None
        if baseline_risk_score is not None:
            base_score = round(float(baseline_risk_score), 1)
            sev = _get_severity(base_score)
            files_desc = (
                f"{affected_files_count} source file{'s' if affected_files_count != 1 else ''}"
                if affected_files_count
                else "modified source files"
            )
            commit_risk = {
                "score": base_score,
                "severity": sev,
                "files_count": affected_files_count,
                "message": (
                    f"Git Commit Risk remains {base_score}/100 ({sev}) because deployment blast radius "
                    f"is driven by {files_desc} and core configurations."
                ),
            }

        return {
            "before": {
                "score": round(before_score, 1),
                "severity": _get_severity(before_score),
                "smells": before_smells,
                "total_smells": before_total,
            },
            "after": {
                "score": round(after_score, 1),
                "severity": _get_severity(after_score),
                "smells": after_smells,
                "total_smells": after_total,
            },
            "delta": {
                "score_reduction": round(point_reduction, 1),
                "smells_resolved": max(0, before_total - after_total),
                "measurable_change": measurable_change,
                "message": message,
            },
            "commit_risk": commit_risk,
            "measurable_change": measurable_change,
            "metric": "Architectural Smell Risk",
            "description": "Evaluates architectural anti-patterns (cycles, bottlenecks, coupling, isolation) on the dependency graph.",
            "sandbox": True,
        }

    # ------------------------------------------------------------------ #
    #  Mock / fallback mode
    # ------------------------------------------------------------------ #

    async def _simulate_mock(
        self,
        edits: List[GraphEdit],
        baseline_risk_score: Optional[float] = None,
        affected_files_count: Optional[int] = None,
        baseline_smells: Optional[Dict[str, int]] = None,
    ) -> Dict[str, Any]:
        """Heuristic estimation when Neo4j is unavailable."""
        if baseline_smells:
            before_counts = dict(baseline_smells)
        else:
            from services.smell_detector import SmellDetector

            detector = SmellDetector()
            try:
                current_smells = await detector.detect_all_smells()
            except Exception:
                current_smells = []

            before_counts = breakdown_smells(current_smells)

        # Estimate after: each edit targets its corresponding smell type
        after_counts = dict(before_counts)
        for edit in edits:
            if edit.action == "remove_edge":
                if after_counts["circular_dependency"] > 0:
                    after_counts["circular_dependency"] -= 1
                elif after_counts["chatty_communication"] > 0:
                    after_counts["chatty_communication"] -= 1
                elif after_counts["shared_database"] > 0:
                    after_counts["shared_database"] -= 1
            elif edit.action == "add_node":
                from_svc = edit.from_service or ""
                if "_facade" in from_svc or "_gateway" in from_svc:
                    if after_counts["bottleneck_service"] > 0:
                        after_counts["bottleneck_service"] = max(0, after_counts["bottleneck_service"] - 1)
                    if after_counts["high_coupling"] > 0:
                        after_counts["high_coupling"] = max(0, after_counts["high_coupling"] - 1)
                    if after_counts["missing_circuit_breaker"] > 0:
                        after_counts["missing_circuit_breaker"] = max(0, after_counts["missing_circuit_breaker"] - 1)
                    if after_counts["shared_database"] > 0:
                        after_counts["shared_database"] = max(0, after_counts["shared_database"] - 1)
                elif "broker" in from_svc:
                    if after_counts["hub_and_spoke"] > 0:
                        after_counts["hub_and_spoke"] = max(0, after_counts["hub_and_spoke"] - 1)
                    if after_counts["chatty_communication"] > 0:
                        after_counts["chatty_communication"] = max(0, after_counts["chatty_communication"] - 1)
            elif edit.action == "add_edge":
                if after_counts["isolated_service"] > 0:
                    after_counts["isolated_service"] -= 1

        before_score, after_score, point_reduction, measurable_change, message = _calculate_simulation_metrics(
            before_counts, after_counts, edits
        )

        before_total = sum(before_counts.values())
        after_total = sum(after_counts.values())

        commit_risk = None
        if baseline_risk_score is not None:
            base_score = round(float(baseline_risk_score), 1)
            sev = _get_severity(base_score)
            files_desc = (
                f"{affected_files_count} source file{'s' if affected_files_count != 1 else ''}"
                if affected_files_count
                else "modified source files"
            )
            commit_risk = {
                "score": base_score,
                "severity": sev,
                "files_count": affected_files_count,
                "message": (
                    f"Git Commit Risk remains {base_score}/100 ({sev}) because deployment blast radius "
                    f"is driven by {files_desc} and core configurations."
                ),
            }

        return {
            "before": {
                "score": round(before_score, 1),
                "severity": _get_severity(before_score),
                "smells": before_counts,
                "total_smells": before_total,
            },
            "after": {
                "score": round(after_score, 1),
                "severity": _get_severity(after_score),
                "smells": after_counts,
                "total_smells": after_total,
            },
            "delta": {
                "score_reduction": round(point_reduction, 1),
                "smells_resolved": max(0, before_total - after_total),
                "measurable_change": measurable_change,
                "message": message,
            },
            "commit_risk": commit_risk,
            "measurable_change": measurable_change,
            "metric": "Architectural Smell Risk",
            "description": "Evaluates architectural anti-patterns (cycles, bottlenecks, coupling, isolation) on the dependency graph.",
            "sandbox": True,
        }

