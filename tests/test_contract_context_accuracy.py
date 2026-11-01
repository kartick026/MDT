"""Contract context, evidence admission and transport regression controls."""
import pytest
from api.projects import evaluate_job
from core.registry import RegistryManager
from services.git_analyzer import GitAnalyzer, GitHubAPIClient


MODEL = "from pydantic import BaseModel\nclass Item(BaseModel):\n    title: str\n"
ROUTE = "from .models import Item\n@app.post('/items', response_model=Item)\ndef create(body: Item):\n    return body\n"


def analyze(before, after, context=None):
    analyzer = GitAnalyzer()
    changes = analyzer.analyze_local_changes([
        {"file_path": "app/models.py", "old_content": before, "new_content": after}
    ], base_sha="a" * 40, commit_sha="b" * 40, source_context=context)
    return analyzer, changes[0]


@pytest.mark.asyncio
async def test_job_resolves_unchanged_consumers_and_exposes_evidence():
    graph = {"services": [{"name": "backend"}], "dependencies": [], "file_mappings": {"app": "backend"},
             "coverage": {"per_service_candidates": {"backend": 2}, "per_service_parsed": {"backend": 2}}}
    baseline = RegistryManager.load()
    result = await evaluate_job({"id": "context-regression", "payload": {
        "project": {"id": "context-regression", "repo_url": "https://github.com/example/sample", "branch": "main", "snapshot": graph},
        "input": {"source": "patch", "base_ref": "a" * 40, "head_ref": "b" * 40,
                  "before_files": {"app/models.py": MODEL, "app/routes.py": ROUTE},
                  "after_files": {"app/models.py": MODEL.replace("title: str", "title: int"), "app/routes.py": ROUTE}}}})
    assert len(result["affected_files"]) == 1
    schema = result["affected_files"][0]["schema_changes"]
    assert schema["compatibility"] == "breaking"
    assert schema["affected_routes"][0]["file_path"] == "app/routes.py"
    assert result["risk_score"] >= 30
    assert result["confidence_evidence"]["kind"] == "evidence_completeness"
    assert result["evidence"]["confidence_calibrated"] is False
    assert result["topology_coverage"] == graph["coverage"]
    assert result["coverage"] != result["topology_coverage"]
    assert RegistryManager.load() == baseline


def test_context_is_part_of_source_fingerprint():
    before, after = MODEL, MODEL.replace("title: str", "title: int")
    first, _ = analyze(before, after)
    second, _ = analyze(before, after, {"before": {"app/routes.py": ROUTE}, "after": {"app/routes.py": ROUTE}})
    assert first.last_extraction["snapshot_digest"] != second.last_extraction["snapshot_digest"]


def test_optional_response_field_is_not_claimed_backward_compatible():
    code = MODEL + "\n@app.get('/items', response_model=Item)\ndef get_item():\n    pass\n"
    _, item = analyze(code, code.replace("title: str", 'title: str = "fallback"'))
    assert item.ast_metadata["contract_changes"]["compatibility"] == "breaking"


def test_missing_model_source_does_not_invent_removed_contract():
    items = GitAnalyzer().analyze_local_changes([
        {"file_path": "app/models.py", "old_content": "", "new_content": MODEL,
         "extraction_warnings": ["old_source_unavailable"]},
        {"file_path": "app/routes.py", "old_content": ROUTE, "new_content": ROUTE + "# note\n"},
    ], base_sha="a" * 40, commit_sha="b" * 40)
    contract = items[1].ast_metadata["contract_changes"]
    assert not contract["added"] and not contract["removed"] and not contract["modified"]
    assert "Item" in contract["unresolved_models"]


def test_inherited_imported_fields_link_to_unchanged_route():
    base = "from pydantic import BaseModel\nclass Base(BaseModel):\n    title: str\n"
    child = "from .base import Base\nclass Item(Base):\n    pass\n"
    changes = GitAnalyzer().analyze_local_changes([
        {"file_path": "app/base.py", "old_content": base, "new_content": base.replace("str", "int")}
    ], base_sha="a" * 40, commit_sha="b" * 40, source_context={
        "before": {"app/models.py": child, "app/routes.py": ROUTE},
        "after": {"app/models.py": child, "app/routes.py": ROUTE}})
    assert changes[0].ast_metadata["schema_changes"]["affected_routes"][0]["compatibility"] == "breaking"


@pytest.mark.asyncio
async def test_transport_distinguishes_empty_file_from_missing_file(httpx_mock):
    client = GitHubAPIClient(token="test")
    httpx_mock.add_response(text="")
    httpx_mock.add_response(status_code=404)
    assert await client.get_file_content("o", "r", "empty.py", "a" * 40) == ""
    with pytest.raises(ValueError, match="404"):
        await client.get_file_content("o", "r", "missing.py", "a" * 40)


@pytest.mark.parametrize("before,after", [("{\"value\":true}", "{\"value\":1}"), ("{\"value\":1}", "{\"value\":1.0}")])
def test_json_types_are_not_collapsed_by_python_equality(before, after):
    change = GitAnalyzer()._build_change("config.json", "modified", before, after)
    assert change.ast_metadata["semantic_change"] is True
