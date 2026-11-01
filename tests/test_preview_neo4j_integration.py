"""Opt-in real Neo4j invariance checks; no test transaction is committed.

Set MDT_LIVE_NEO4J_URI/USER/PASSWORD to a test database. Every proposal uses a
unique temporary service and is rolled back on success and injected failure.
"""
import asyncio
import json
import os
import uuid
from unittest.mock import patch

import pytest

from domain.architecture import snapshot_from_transaction
from services.remediation_simulator import GraphEdit, RemediationSimulator

pytestmark = pytest.mark.skipif(not os.getenv("MDT_LIVE_NEO4J_URI"), reason="Explicit live Neo4j test database not configured")


@pytest.fixture
def live_driver():
    from neo4j import GraphDatabase
    driver = GraphDatabase.driver(os.environ["MDT_LIVE_NEO4J_URI"], auth=(
        os.getenv("MDT_LIVE_NEO4J_USER", "neo4j"), os.environ["MDT_LIVE_NEO4J_PASSWORD"]))
    driver.verify_connectivity()
    yield driver
    driver.close()


def capture(driver):
    with driver.session() as session:
        tx = session.begin_transaction()
        try:
            snapshot = snapshot_from_transaction(tx)
            nodes = [dict(r) for r in tx.run("MATCH (n) RETURN elementId(n) AS id, labels(n) AS labels, properties(n) AS props ORDER BY id")]
            edges = [dict(r) for r in tx.run("MATCH (a)-[r]->(b) RETURN elementId(r) AS id, elementId(a) AS src, elementId(b) AS dst, type(r) AS type, properties(r) AS props ORDER BY id")]
            return snapshot, json.dumps([nodes, edges], sort_keys=True, default=str)
        finally:
            tx.rollback()


def cycle_proposal():
    name = "mdt-preview-test-" + uuid.uuid4().hex
    return [GraphEdit(action="add_node", from_service=name), GraphEdit(action="add_edge", from_service=name, to_service=name)]


@pytest.mark.asyncio
async def test_live_transaction_matches_copy_and_preserves_entire_graph(live_driver):
    from services.remediation_simulator import apply_snapshot_edits
    baseline, fingerprint = capture(live_driver)
    with patch("services.remediation_simulator.get_neo4j_driver", return_value=live_driver):
        simulator = RemediationSimulator()
    edits = cycle_proposal()
    result = await simulator._simulate_live(edits, snapshot=baseline)
    after, removed = apply_snapshot_edits(baseline, edits)
    expected = simulator._result(baseline, after, edits, removed, None, None, "snapshot")
    assert result["before"] == expected["before"]
    assert result["after"] == expected["after"]
    assert result["findings"] == expected["findings"]
    assert result["after"]["smells"]["circular_dependency"] == result["before"]["smells"]["circular_dependency"] + 1
    assert result["evaluation_mode"] == "neo4j_transaction"
    assert capture(live_driver)[1] == fingerprint


@pytest.mark.asyncio
async def test_real_transaction_rolls_back_when_evaluation_raises(live_driver):
    baseline, fingerprint = capture(live_driver)
    with patch("services.remediation_simulator.get_neo4j_driver", return_value=live_driver):
        simulator = RemediationSimulator()
    with patch.object(simulator, "_result", side_effect=RuntimeError("injected after graph mutations")):
        with pytest.raises(RuntimeError, match="injected"):
            await simulator._simulate_live(cycle_proposal(), snapshot=baseline)
    assert capture(live_driver)[1] == fingerprint


@pytest.mark.asyncio
async def test_concurrent_real_previews_do_not_leak_each_others_changes(live_driver):
    baseline, fingerprint = capture(live_driver)
    with patch("services.remediation_simulator.get_neo4j_driver", return_value=live_driver):
        simulator = RemediationSimulator()
    one, two = await asyncio.gather(
        simulator._simulate_live(cycle_proposal(), snapshot=baseline),
        simulator._simulate_live(cycle_proposal(), snapshot=baseline),
    )
    assert one["before"] == two["before"]
    assert one["after"] == two["after"]
    assert one["after"]["smells"]["circular_dependency"] == one["before"]["smells"]["circular_dependency"] + 1
    assert capture(live_driver)[1] == fingerprint
