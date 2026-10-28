"""Independent diagnostic controls for semantic and contract accuracy.

These small, hand-labeled cases were authored separately from the production
implementation. They are regression checks, not a calibrated accuracy dataset.
No repository source, network connection or user project is required.
"""
import pytest

from core.registry import RegistryManager
from services.git_analyzer import GitAnalyzer
from services.impact_engine import ImpactEngine


def change(path, before, after, **extra):
    return GitAnalyzer().analyze_local_changes([
        {"file_path": path, "old_content": before, "new_content": after, **extra}
    ], base_sha="a" * 40, commit_sha="b" * 40)[0]


@pytest.mark.parametrize("path,before,after", [
    ("service/api/controller.py", 'def load():\n    return "# significant"\n',
     '# comment\ndef load():\n    return "# significant"  # comment\n'),
    ("service/api/controller.ts", 'export const value = "http://example.invalid";\n',
     '// app.delete("/fake", handler)\nexport const value = "http://example.invalid"; /* comment */\n'),
    ("service/config.py", 'TIMEOUT = 30\n', 'TIMEOUT = 30  # only explanatory\n'),
    ("docker-compose.yaml", 'services:\n  api:\n    image: acme/api:1\n',
     '# configuration explanation\nservices:\n  api:\n    image: acme/api:1 # same image\n'),
    ("service/settings.json", '{"timeout":30,"url":"http://example.invalid"}',
     '{\n  "url": "http://example.invalid",\n  "timeout": 30\n}'),
    ("service/pyproject.toml", '[settings]\ntimeout = 30\n',
     '# explanatory\n[settings]\ntimeout = 30 # unchanged\n'),
])
def test_comments_and_formatting_do_not_create_risk(path, before, after):
    item = change(path, before, after)
    assert item.ast_metadata["semantic_change"] is False
    assert item.ast_metadata["semantic_status"] == "equivalent"
    snapshot = {"services": [], "dependencies": [], "file_mappings": {}}
    with RegistryManager.use_snapshot(snapshot, "accuracy-controls"):
        engine = ImpactEngine()
        factors = engine._calculate_deterministic_risk([item])
        factors.dependency_depth = 0
        assert not factors.api_changes and not factors.schema_changes and not factors.config_changes
        assert engine._compute_base_risk(factors) == 0


@pytest.mark.parametrize("path,before,after", [
    ("api.py", '@app.get("/value")\ndef value():\n    return 1\n',
     '@app.get("/value")\ndef value():\n    return 2\n'),
    ("routes.js", 'app.get("/value", (req, res) => res.send("one"));',
     'app.get("/value", (req, res) => res.send("two"));'),
    ("routes.ts", 'const url = "http://one.invalid";', 'const url = "http://two.invalid";'),
])
def test_runtime_edits_remain_changes_without_inventing_contract_changes(path, before, after):
    item = change(path, before, after)
    assert item.ast_metadata["semantic_change"] is True
    assert not ImpactEngine()._has_api_changes([item])


def test_deployment_value_edit_is_not_suppressed_as_comment():
    item = change("docker-compose.yaml", 'services:\n  api:\n    image: acme/api:1\n',
                  'services:\n  api:\n    image: acme/api:2\n')
    assert item.ast_metadata["semantic_change"] is True
    assert ImpactEngine()._has_config_changes([item])


def test_missing_source_is_unknown_not_equivalent():
    item = change("api/controller.py", "", "", extraction_warnings=["old_source_unavailable", "new_source_unavailable"])
    assert item.ast_metadata["semantic_change"] is None
    assert item.ast_metadata["semantic_status"] == "unknown"
    assert item.extraction_status == "partial"


def test_invalid_source_cannot_be_a_safe_noop():
    item = change("api/controller.py", "def broken(:", "def broken(:")
    assert item.ast_metadata["semantic_change"] is None
    assert item.extraction_status == "partial"


SCHEMA = 'from pydantic import BaseModel\nclass CreateWidget(BaseModel):\n    label: str\n'
ROUTE = ('from .models import CreateWidget\n'
         '@app.post("/widgets")\ndef create(body: CreateWidget):\n    return {"created": True}\n')


@pytest.mark.parametrize("after,expected", [
    (SCHEMA + "    note: str | None = None\n", "additive"),
    (SCHEMA + "    quantity: int\n", "breaking"),
    (SCHEMA.replace("label: str", "label: int"), "breaking"),
    (SCHEMA.replace("label: str", "pass"), "breaking"),
])
def test_imported_request_model_compatibility_is_not_just_a_filename(after, expected):
    analyzer = GitAnalyzer()
    changes = analyzer.analyze_local_changes([
        {"file_path": "service/models.py", "old_content": SCHEMA, "new_content": after},
        {"file_path": "service/routes.py", "old_content": ROUTE, "new_content": ROUTE},
    ], base_sha="a" * 40, commit_sha="b" * 40,
       source_context={"before": {"service/models.py": SCHEMA, "service/routes.py": ROUTE},
                       "after": {"service/models.py": after, "service/routes.py": ROUTE}})
    schema = next(item for item in changes if item.file_path.endswith("models.py"))
    route = next(item for item in changes if item.file_path.endswith("routes.py"))
    assert schema.ast_metadata["schema_changes"]["compatibility"] == expected
    assert route.ast_metadata["contract_changes"]["compatibility"] == expected
    assert ImpactEngine()._has_api_changes(changes)


def test_model_requiredness_relaxation_is_additive():
    item = change("service/models.py", SCHEMA, SCHEMA.replace("label: str", 'label: str = "default"'))
    assert item.ast_metadata["schema_changes"]["compatibility"] == "additive"


def test_model_requiredness_tightening_is_breaking():
    item = change("service/models.py", SCHEMA.replace("label: str", 'label: str = "default"'), SCHEMA)
    assert item.ast_metadata["schema_changes"]["compatibility"] == "breaking"


def test_unrelated_helper_class_is_not_invented_as_public_schema():
    item = change("service/schema_helpers.py", 'class Cache:\n    size: int\n', 'class Cache:\n    size: str\n')
    assert item.ast_metadata["semantic_change"] is True
    assert item.ast_metadata["schema_changes"]["compatibility"] == "unchanged"
    assert not ImpactEngine()._has_api_changes([item])


def test_literal_route_addition_and_removal_are_distinguished():
    source = '@app.get("/widgets")\ndef widgets():\n    return []\n'
    added = change("service/main.py", "", source)
    removed = change("service/main.py", source, "")
    assert added.ast_metadata["contract_changes"]["compatibility"] == "additive"
    assert removed.ast_metadata["contract_changes"]["compatibility"] == "breaking"


def test_type_widening_is_not_automatically_declared_compatible():
    item = change("service/models.py", SCHEMA, SCHEMA.replace("label: str", "label: str | int"))
    # Static annotation changes need directional protocol reasoning. An explicit
    # warning is safer than claiming a backward-compatible public contract.
    assert item.ast_metadata["schema_changes"]["compatibility"] in {"breaking", "uncertain"}
