"""Behavioral regressions derived from the ten pinned public imports."""
from unittest.mock import AsyncMock
import pytest

from core.registry import RegistryManager
from domain.architecture import GraphSnapshot, detect_smells
from domain.relations import dependency_depth
from services.aspire_discovery import discover_aspire
from services.connection_validator import ConnectionValidator
from services.dependency_graph import DependencyGraph
from services.deployment_evidence import compose_ports, compose_references, merge_source_calls, dotenv_literals, compose_env_files
from services.repo_onboarding import RepoOnboarder


def test_declarations_do_not_prove_chatter_missing_resilience_or_shared_database():
    nodes = [{"name": name} for name in ("app", "b", "c", "d")] + [{"name": "db", "node_type": "database"}]
    edges = [{"from": "app", "to": name, "type": "startup"} for name in ("b", "c", "d", "db")]
    edges += [{"from": "b", "to": "db", "type": "startup"}]
    edges += [{"from": "app", "to": "b", "type": "http", "endpoint": f"/{i}",
               "evidence_kind": "compose_env_reference"} for i in range(4)]
    graph = GraphSnapshot.from_data({"services": nodes, "dependencies": edges, "project": {"source": "repository"}})
    assert not {f["type"] for f in detect_smells(graph)} & {
        "Chatty Communication", "Missing Circuit Breaker", "Shared Database", "High Coupling", "Dead / Isolated Service"}
    assert graph.to_data()["dependencies"][-1].get("type")
    assert any(e.get("evidence_kind") == "compose_env_reference" for e in graph.to_data()["dependencies"])


def test_imported_missing_resilience_is_unknown_even_with_actual_static_calls():
    data = {"services": [{"name": n} for n in ("app", "b", "c", "d")],
            "dependencies": [{"from": "app", "to": n, "type": "http", "evidence_kind": "source_inferred"}
                             for n in ("b", "c", "d")], "project": {"source": "repository"}}
    assert "Missing Circuit Breaker" not in {f["type"] for f in detect_smells(GraphSnapshot.from_data(data))}
    data["services"][0].update(has_circuit_breaker=False, resilient=False)
    assert "Missing Circuit Breaker" in {f["type"] for f in detect_smells(GraphSnapshot.from_data(data))}


def test_callback_configuration_cycle_is_not_a_synchronous_call_cycle():
    graph = GraphSnapshot.from_data({"services": [{"name": "identity"}, {"name": "web"}],
        "dependencies": [{"from": a, "to": b, "type": "declared", "evidence_kind": "aspire_endpoint_reference"}
                         for a, b in (("identity", "web"), ("web", "identity"))],
        "project": {"source": "repository"}})
    assert not any(f["type"] == "Circular Dependency" for f in detect_smells(graph))


def test_zero_observed_debt_retains_insufficient_communication_evidence():
    from services.remediation_simulator import compute_architecture_health, breakdown_smells
    graph = GraphSnapshot.from_data({"services": [{"name": "a"}, {"name": "b"}],
        "dependencies": [{"from": "a", "to": "b", "type": "startup"}], "project": {"source": "repository"}})
    result = compute_architecture_health(breakdown_smells(detect_smells(graph)), graph)
    assert result["score"] == 0
    assert result["assessment_status"] == "insufficient_communication_evidence"
    assert result["evidence"]["startup_relations"] == 1


def test_source_calls_preserve_parallel_paths_and_startup_type():
    services = [{"name": "web"}, {"name": "api", "port": 8080}]
    original = {"from": "web", "to": "api", "type": "startup", "endpoint": "", "evidence_kind": "compose_startup_order"}
    code = 'import requests\nrequests.get("http://api:8080/one")\nrequests.get("http://api:8080/two")\nrequests.get("http://api:8080/one")'
    edges = merge_source_calls(services, {"web": {"web/main.py": code}}, [original.copy()], ConnectionValidator)
    assert edges[0] == original
    assert {edge["endpoint"] for edge in edges[1:]} == {"/one", "/two"}
    assert len(edges) == 3
    assert all(e["type"] == "http" and e["source_file"] == "web/main.py" for e in edges[1:])


@pytest.mark.parametrize("ports,expose,expected", [
    (["127.0.0.1:8081:80/tcp"], [], (80, 8081)),
    ([{"target": 5432, "published": "15432", "host_ip": "127.0.0.1"}], [], (5432, 15432)),
    (["80"], [], (80, None)),
    ([], ["9090/tcp"], (9090, None)),
    (["${PORT}:8000"], [], (8000, None)),
    (["8000-8005:80-85"], [], (None, None)),
])
def test_compose_port_forms_do_not_invent_host_port(ports, expose, expected):
    assert compose_ports({"ports": ports, "expose": expose}) == expected


def test_literal_configuration_references_are_sanitized_and_unresolved_values_ignored():
    configs = {"a": {"environment": {"DATABASE_URL": "postgresql://user:secret@db:5432/catalog?password=hidden",
                                     "HOST": "db", "DYNAMIC_URL": "http://${SERVICE}:80/path",
                                     "EXTERNAL_URL": "https://db.example.org/path"}}, "db": {"image": "postgres"}}
    edges = compose_references(configs, "compose.yaml")
    assert len(edges) == 2 and all(edge["to"] == "db" for edge in edges)
    assert {edge["type"] for edge in edges} == {"postgresql", "declared"}
    assert all(word not in str(edges) for word in ("secret", "hidden", "example.org", "${"))


def test_recorded_compose_defaults_resolve_references_without_using_host_environment(monkeypatch):
    monkeypatch.setenv("TARGET", "outside")
    defaults = dotenv_literals('PORT=8080\nTARGET=api\nSECRET=$(shell command)\nQUOTED="literal"\n')
    assert "SECRET" not in defaults
    nodes, edges, _ = RepoOnboarder()._parse_compose('''services:
  web:
    environment:
      API_URL: http://${TARGET}:${PORT}/v1
      UNKNOWN_URL: http://${MISSING}:123/
  api:
    ports: ["${HOST_PORT:-9000}:${PORT}"]
''', defaults=defaults)
    assert len(edges) == 1 and edges[0]["to"] == "api" and edges[0]["endpoint"] == "/v1"
    assert nodes[1]["port"] == 8080 and nodes[1]["host_port"] == 9000


@pytest.mark.asyncio
async def test_compose_env_file_precedence_passthrough_and_bounded_safe_reads():
    defaults = dotenv_literals('PORT=8080\nADDR=api:${PORT}\n')
    content = '''services:
  web:
    env_file: [common.env, override.env, ../outside.env]
    environment: [ADDR, TARGET=http://api:8080/final]
  api: {image: company/api}
'''
    files = {"common.env": "TARGET=http://other:8080\n", "override.env": "TARGET=http://api:8080/override\n"}
    getter = AsyncMock(side_effect=lambda path: files[path])
    environments, warnings = await compose_env_files(content, "compose.yml", set(files), getter, defaults)
    assert getter.await_count == 2 and warnings == ["compose_env_file_unavailable:web"]
    nodes, edges, _ = RepoOnboarder()._parse_compose(content, defaults=defaults, file_environments=environments)
    assert len(nodes) == 2
    assert {edge["endpoint"] for edge in edges} == {"", "/final"}
    assert all(edge["to"] == "api" for edge in edges)


@pytest.mark.asyncio
async def test_library_with_same_name_as_infrastructure_is_not_source_ownership():
    nodes, _, mappings = await RepoOnboarder()._infer_from_file_tree("owner", "repo", "sha",
        tree=["src/EventBus/EventBus.csproj", "src/EventBus/Events.cs"],
        existing_services=[{"name": "eventbus", "node_type": "broker", "discovery_kind": "aspire"}])
    assert mappings == {} and len(nodes) == 1


@pytest.mark.asyncio
async def test_project_depth_is_distance_not_fanout_or_disabled_shared_database():
    data = {"services": [{"name": n} for n in ("a", "b", "c", "d", "e")],
            "dependencies": [{"from": "a", "to": "b"}, {"from": "b", "to": "c"},
                             {"from": "c", "to": "a"}, {"from": "a", "to": "d"},
                             {"from": "e", "to": "a", "type": "startup"}],
            "file_mappings": {"src/c": "c"}}
    with RegistryManager.use_snapshot(data, "evidence-test"):
        graph = DependencyGraph()
        assert await graph.get_dependency_depth("a") == 2
        assert set(await graph.get_affected_services("src/c/main.py")) == {"a", "b", "c"}
        assert "e" not in await graph.get_affected_services("src/c/main.py")
    assert dependency_depth("a", [{"from": "a", "to": str(i)} for i in range(100)]) == 1
    assert dependency_depth("0", [{"from": str(i), "to": str(i+1)} for i in range(20)]) == 8


@pytest.mark.asyncio
async def test_canonical_kubernetes_manifest_precedes_optional_monitoring_budget():
    tree = [f"deploy/kubernetes/monitoring/{i}.yaml" for i in range(40)] + ["deploy/kubernetes/application.yaml"]
    getter = AsyncMock(return_value="""kind: Deployment
metadata: {name: checkout}
spec:
  template:
    spec:
      containers: [{name: app, image: company/checkout}]
""")
    services, _, _, metadata = await RepoOnboarder()._discover_kubernetes(tree, getter)
    assert [s["name"] for s in services] == ["checkout"]
    assert getter.await_count == 1
    assert metadata["selected_manifest_files"] == ["deploy/kubernetes/application.yaml"]
    assert metadata["alternative_manifest_files_excluded"] == 40


@pytest.mark.asyncio
async def test_aspire_literal_topology_is_generic_and_does_not_execute_helpers():
    code = '''var builder = DistributedApplication.CreateBuilder(args);
var server = builder.AddPostgres("storage");
var database = server.AddDatabase("records");
var api = builder.AddDotnetProject("catalog", "../Catalog.API").WithReference(database).WaitFor(database);
var address = api.GetEndpoint("http");
builder.AddDotnetProject("web", "../Web").WithEnvironment("API_URL", address);
if (enabled) { var optional = builder.AddRedis("conditional"); }
// builder.AddRedis("comment");
var text = "builder.AddRedis(\\"string\\");";
void Helper() { builder.AddRedis("helper"); }
'''
    nodes, edges, mappings, meta = await discover_aspire(
        ["src/Demo.AppHost/AppHost.cs", "src/Catalog.API/Catalog.API.csproj", "src/Web/Web.csproj"], AsyncMock(return_value=code))
    assert {node["name"] for node in nodes} == {"storage", "records", "catalog", "web"}
    assert mappings == {"src/Catalog.API": "catalog", "src/Web": "web"}
    assert {(e["from"], e["to"], e["type"]) for e in edges} == {
        ("catalog", "records", "declared"), ("catalog", "records", "startup"), ("web", "catalog", "declared")}
    assert meta["warnings"] and all(node["port"] is None for node in nodes)


@pytest.mark.asyncio
async def test_aspire_ambiguous_apphosts_abstain():
    getter = AsyncMock()
    nodes, _, _, meta = await discover_aspire(["A.AppHost/AppHost.cs", "B.AppHost/Program.cs"], getter)
    assert nodes == [] and "aspire_multiple_apphosts_require_selection" in meta["warnings"]
    getter.assert_not_called()
