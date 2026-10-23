"""Discovery regressions: deployed topology must have evidence and bounded source coverage."""
from unittest.mock import AsyncMock

import pytest

from services.repo_onboarding import RepoOnboarder


@pytest.mark.asyncio
async def test_shared_compose_context_maps_nested_dockerfile_and_repairs_declared_directory():
    onboarder = RepoOnboarder()
    services, dependencies, mappings = onboarder._parse_compose("""
services:
  backend:
    build:
      context: .
      dockerfile: backend/Dockerfile
  worker:
    build: .
  frontend:
    build: frontend
  proxy:
    image: nginx
""")
    assert mappings == {"backend": "backend", "frontend": "frontend"}
    services, _, mappings = await onboarder._infer_from_file_tree("owner", "repo", "sha",
        tree=["backend/Dockerfile", "backend/app/main.py", "backend/app/models.py", "worker/main.py", "frontend/src/main.tsx"],
        existing_services=services, existing_dependencies=dependencies, existing_mappings=mappings)
    assert mappings["worker"] == "worker"
    assert next(service for service in services if service["name"] == "backend")["language"] == "python"
    assert next(service for service in services if service["name"] == "proxy")["source_expected"] is False


def test_compose_source_context_never_collapses_parent_or_remote_path_into_repo():
    onboarder = RepoOnboarder()
    _, _, mappings = onboarder._parse_compose("""
services:
  escape:
    build: ../secret
  remote:
    build: https://github.com/example/project.git
  api:
    build: ./api
""")
    assert mappings == {"api": "api"}


@pytest.mark.asyncio
async def test_large_frontend_does_not_starve_backend_source():
    files = {f"frontend/f{index:03d}.js": "export const value = 1;" for index in range(140)}
    files.update({f"backend/f{index:03d}.py": "value = 1" for index in range(60)})
    getter = AsyncMock(side_effect=lambda path: files[path])
    _, coverage = await RepoOnboarder()._collect_service_sources(
        [{"name": "frontend", "language": "javascript"}, {"name": "backend", "language": "python"}],
        {"frontend": "frontend", "backend": "backend"}, list(files), getter)
    assert coverage["per_service"] == {"frontend": 50, "backend": 50}
    assert coverage["per_service_candidates"] == {"frontend": 140, "backend": 60}
    assert getter.await_count == coverage["files_attempted"] == 100
    assert coverage["partial"] is True


@pytest.mark.asyncio
async def test_empty_module_counts_as_read_and_missing_source_is_not_infra():
    _, coverage = await RepoOnboarder()._collect_service_sources(
        [{"name": "api", "source_expected": True, "language": "python"},
         {"name": "missing", "source_expected": True}, {"name": "proxy", "source_expected": False}],
        {"api": "api"}, ["api/__init__.py"], AsyncMock(return_value=""))
    assert coverage["per_service"] == {"api": 1, "missing": 0, "proxy": 0}
    assert coverage["missing_source_services"] == ["missing"]
    assert "empty_or_unavailable_source:api/__init__.py" not in coverage["warnings"]


@pytest.mark.asyncio
@pytest.mark.parametrize("tree", [
    ["package.json", "index.js", "lib/application.js", "examples/hello-world/index.js"],
    ["pyproject.toml", "fastapi/routing.py", "docs_src/app/main.py", "docs_src/tutorial001.py"],
    ["packages/tool/package.json", "packages/tool/index.js", "docs/main.py"],
])
async def test_libraries_and_tutorials_do_not_establish_deployment(tree):
    services, dependencies, mappings = await RepoOnboarder()._infer_from_file_tree("owner", "library", "sha", tree=tree)
    assert (services, dependencies, mappings) == ([], [], {})


@pytest.mark.asyncio
async def test_directory_names_do_not_invent_frontend_backend_edge():
    services, dependencies, _ = await RepoOnboarder()._infer_from_file_tree("owner", "application", "sha",
        tree=["frontend/Dockerfile", "frontend/index.js", "backend/main.py"])
    assert {service["name"] for service in services} == {"frontend", "backend"}
    assert dependencies == []


@pytest.mark.asyncio
async def test_vite_application_discovered_but_email_template_package_excluded():
    services, _, mappings = await RepoOnboarder()._infer_from_file_tree("owner", "app", "sha",
        tree=["frontend/package.json", "frontend/src/main.tsx", "packages/react-email/package.json",
              "packages/react-email/emails/welcome.tsx"])
    assert [service["name"] for service in services] == ["frontend"]
    assert mappings == {"frontend": "frontend"}


KUBERNETES = """
apiVersion: apps/v1
kind: Deployment
metadata: {name: checkout}
spec:
  template:
    metadata: {labels: {app: checkout}}
    spec:
      containers:
      - name: app
        image: demo/checkout
        ports: [{containerPort: 5050}]
        env:
        - {name: PAYMENT_ADDR, value: 'payment-service:50051'}
        - {name: DYNAMIC_ADDR, valueFrom: {secretKeyRef: {name: config, key: address}}}
---
apiVersion: apps/v1
kind: Deployment
metadata: {name: payment}
spec:
  template:
    metadata: {labels: {app: payment}}
    spec:
      containers:
      - name: app
        image: demo/payment
        ports: [{containerPort: 50051}]
---
apiVersion: v1
kind: Service
metadata: {name: payment-service}
spec:
  selector: {app: payment}
  ports: [{port: 50051}]
"""


@pytest.mark.asyncio
async def test_kubernetes_services_use_selectors_and_only_explicit_endpoint_references():
    onboarder = RepoOnboarder()
    tree = ["kubernetes-manifests/app.yaml", "src/checkout/main.go", "src/payment/main.go", "proto/service.proto",
            "src/optional-service/Dockerfile", "src/optional-service/main.py"]
    services, dependencies, mappings, metadata = await onboarder._discover_kubernetes(tree, AsyncMock(return_value=KUBERNETES))
    services, dependencies, mappings = await onboarder._infer_from_file_tree("owner", "shop", "sha", tree=tree,
        existing_services=services, existing_dependencies=dependencies, existing_mappings=mappings)
    assert {service["name"] for service in services} == {"checkout", "payment"}
    assert mappings == {"src/checkout": "checkout", "src/payment": "payment"}
    assert len(dependencies) == 1
    assert dependencies[0]["from"] == "checkout" and dependencies[0]["to"] == "payment"
    assert dependencies[0]["type"] == "declared"
    assert dependencies[0]["evidence_kind"] == "kubernetes_env_reference"
    assert "grpc_contracts_unresolved" in metadata["warnings"]
    assert "kubernetes_environment_unresolved:checkout:DYNAMIC_ADDR" in metadata["warnings"]
    _, coverage = await onboarder._collect_service_sources(services, mappings, tree, AsyncMock(return_value="package main"))
    assert coverage["unsupported_contract_services"] == ["checkout", "payment"]


@pytest.mark.asyncio
async def test_kubernetes_manifest_budget_and_templates_are_explicit():
    getter = AsyncMock(return_value="kind: Deployment\nmetadata: {name: '{{ .Values.name }}'}")
    services, dependencies, _, metadata = await RepoOnboarder()._discover_kubernetes(
        [f"k8s/{index:02d}.yaml" for index in range(40)], getter)
    assert services == dependencies == []
    assert getter.await_count == 32
    assert "kubernetes_manifest_file_limit_reached" in metadata["warnings"]
    assert any(item.startswith("kubernetes_template_unresolved:") for item in metadata["warnings"])
