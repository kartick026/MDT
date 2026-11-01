"""Regression coverage using real temporary Git histories and submitted snapshots."""
import importlib.util
import io
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from git import Repo

from services.git_analyzer import GitAnalyzer, MAX_SOURCE_BYTES
from services.repo_onboarding import RepoOnboarder
from services.impact_engine import ImpactEngine


@pytest.fixture
def history(tmp_path):
    repo = Repo.init(tmp_path)
    with repo.config_writer() as config:
        config.set_value("user", "name", "MDT Test")
        config.set_value("user", "email", "mdt-test@example.invalid")
    repo.create_remote("origin", "https://github.com/example/sample")
    (tmp_path / "routes.py").write_text('def old_route():\n    return 1\n', encoding="utf-8")
    repo.index.add(["routes.py"])
    first = repo.index.commit("first")
    (tmp_path / "routes.py").write_text('def new_route():\n    return 2\n', encoding="utf-8")
    repo.index.add(["routes.py"])
    second = repo.index.commit("second")
    (tmp_path / "worker.py").write_text('def work():\n    return 3\n', encoding="utf-8")
    repo.index.add(["worker.py"])
    third = repo.index.commit("third")
    return repo, first, second, third


def test_two_commit_range_reads_both_full_snapshots(history):
    repo, first, _, third = history
    analyzer = GitAnalyzer()
    changes = analyzer._analyze_git_snapshots(repo, third.hexsha, base_sha=first.hexsha)
    assert {c.file_path for c in changes} == {"routes.py", "worker.py"}
    route = next(c for c in changes if c.file_path == "routes.py")
    assert "old_route" in route.ast_metadata["old"]["functions"]
    assert "new_route" in route.ast_metadata["new"]["functions"]
    assert route.base_sha == first.hexsha
    assert route.extraction_status == "complete"


def test_rename_and_deletion_preserve_old_source(history):
    repo, _, _, third = history
    repo.git.mv("routes.py", "renamed.py")
    repo.index.remove(["worker.py"], working_tree=True)
    fourth = repo.index.commit("rename and remove")
    changes = GitAnalyzer()._analyze_git_snapshots(repo, fourth.hexsha, base_sha=third.hexsha)
    renamed = next(c for c in changes if c.change_type == "renamed")
    assert renamed.previous_path == "routes.py"
    assert renamed.old_content == renamed.new_content
    deleted = next(c for c in changes if c.change_type == "deleted")
    assert "def work" in deleted.old_content and not deleted.new_content


def test_unknown_sha_fails_instead_of_safe_empty_analysis(history):
    with pytest.raises(ValueError, match="unavailable"):
        GitAnalyzer()._analyze_git_snapshots(history[0], "a" * 40)


def test_submitted_changed_endpoint_is_not_remote_head():
    analyzer = GitAnalyzer()
    changes = analyzer.analyze_local_changes([{"file_path": "routes.py", "change_type": "modified",
        "old_content": "def existing():\n    pass\n", "new_content": "def staged_endpoint():\n    pass\n"}],
        base_sha="a" * 40, commit_sha="b" * 40)
    assert changes[0].ast_metadata["new"]["functions"] == ["staged_endpoint"]
    assert "staged_endpoint" in changes[0].diff_content


def test_oversized_and_invalid_python_are_explicitly_partial():
    analyzer = GitAnalyzer()
    big = analyzer._build_change("routes.py", "modified", "", "x" * (MAX_SOURCE_BYTES + 1))
    assert big.extraction_status == "partial" and not big.new_content
    invalid = analyzer._build_change("routes.py", "modified", "", "def broken(:")
    assert invalid.parser_coverage == "failed"
    assert "new_source_parse_failed" in invalid.extraction_warnings
    with pytest.raises(ValueError, match="relative"):
        analyzer.analyze_local_changes([{"file_path": "../secret", "old_content": "", "new_content": "x"}],
                                       base_sha="a" * 40, commit_sha="b" * 40)


@pytest.mark.asyncio
async def test_api_non_entrypoint_reads_old_and_new_source():
    analyzer = GitAnalyzer()
    analyzer._gh.get_file_content = AsyncMock(side_effect=["def before(): pass", "def after(): pass"])
    change = await analyzer._build_change_info_from_api("owner", "repo", "nested/routes.py", "head", "base", "@@ -1 +1 @@\n-old\n+new")
    assert change.ast_metadata["old"]["functions"] == ["before"]
    assert change.ast_metadata["new"]["functions"] == ["after"]
    assert analyzer._gh.get_file_content.call_count == 2


@pytest.mark.asyncio
async def test_onboarding_reads_nested_router_and_preserves_file_evidence():
    onboarder = RepoOnboarder()
    files = {"svc/main.py": "app = FastAPI()", "svc/api/orders.py": '@app.get("/orders")\ndef orders(): pass',
             "svc/client.py": 'client.get("http://payments:8000/pay")', "svc/node_modules/lib.js": "ignored"}
    content = AsyncMock(side_effect=lambda path: files[path])
    result, coverage = await onboarder._collect_service_sources([{"name": "orders"}], {"svc": "orders"}, list(files), content)
    assert set(result["orders"]) == {"svc/main.py", "svc/api/orders.py", "svc/client.py"}
    assert coverage["files_read"] == 3 and not coverage["warnings"]


def test_core_service_counts_distinct_callers_not_routes():
    services = [{"name": name} for name in ("a", "b", "target")]
    dependencies = [{"from": "a", "to": "target", "endpoint": f"/{i}"} for i in range(10)]
    with patch("core.registry.RegistryManager.get_services", return_value=services), patch("core.registry.RegistryManager.get_dependencies", return_value=dependencies):
        assert "target" not in ImpactEngine()._get_core_services()
    dependencies.append({"from": "b", "to": "target"})
    with patch("core.registry.RegistryManager.get_services", return_value=services), patch("core.registry.RegistryManager.get_dependencies", return_value=dependencies):
        assert "target" in ImpactEngine()._get_core_services()


@pytest.fixture
def hook():
    spec = importlib.util.spec_from_file_location("mdt_check_test", Path(__file__).parents[1] / "mdt-hook" / "mdt_check.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_hook_staged_uses_index_and_working_uses_actual_worktree(history, monkeypatch, hook):
    repo, _, _, third = history
    monkeypatch.chdir(repo.working_tree_dir)
    file = Path(repo.working_tree_dir) / "routes.py"
    file.write_text("def staged(): pass\n", encoding="utf-8")
    repo.index.add(["routes.py"])
    file.write_text("def unstaged(): pass\n", encoding="utf-8")
    staged = hook._build_payload("staged")
    working = hook._build_payload("working")
    assert "def staged" in staged["local_changes"][0]["new_content"]
    assert "def unstaged" in working["local_changes"][0]["new_content"]
    assert staged["base_sha"] == third.hexsha


def test_pre_push_reads_supplied_full_ref_range(history, monkeypatch, hook):
    repo, first, _, third = history
    monkeypatch.chdir(repo.working_tree_dir)
    line = f"refs/heads/main {third.hexsha} refs/heads/main {first.hexsha}\n"
    payload = list(hook._pre_push_payloads(io.StringIO(line)))[0]
    assert set(payload["changed_files"]) == {"routes.py", "worker.py"}
    assert payload["base_sha"] == first.hexsha


def test_hook_error_blocks_unless_explicit_warn(hook):
    with patch.object(hook, "_build_payload", side_effect=ValueError("API unavailable")):
        assert hook.main(["--staged"]) == 2
        assert hook.main(["--staged", "--on-error", "warn"]) == 0


def test_route_removal_in_main_file_triggers_api_change_risk():
    change = GitAnalyzer()._build_change("main.py", "modified",
        '@app.get("/removed")\ndef handler(): pass\n', 'def helper(): pass\n')
    assert ImpactEngine()._has_api_changes([change])


@pytest.mark.asyncio
async def test_scoped_impact_explanation_does_not_call_llm():
    engine = ImpactEngine()
    engine.explainer.explain = AsyncMock()
    with patch("services.impact_engine.current_project_id", return_value="private-project"):
        result = await engine._generate_explanation([], [], 0, {})
    assert "not sent to an LLM" in result
    engine.explainer.explain.assert_not_called()


def test_http_method_change_same_path_is_contract_change():
    change = GitAnalyzer()._build_change("main.py", "modified",
        '@app.get("/orders")\ndef handler(): pass\n', '@app.post("/orders")\ndef handler(): pass\n')
    assert change.ast_metadata["contract_changes"]["removed"][0]["method"] == "GET"
    assert change.ast_metadata["contract_changes"]["added"][0]["method"] == "POST"
    assert ImpactEngine()._has_api_changes([change])
