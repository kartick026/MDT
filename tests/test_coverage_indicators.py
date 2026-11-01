"""Source bytes, parser outcomes and runtime evidence are different measurements."""
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from core.config import Settings, settings
from core.registry import RegistryManager
from services.analysis_evidence import assess_evidence
from services.coverage_indicators import coverage_indicators
from services.git_analyzer import GitAnalyzer, GitHubRateLimitError, MAX_SOURCE_BYTES
from services.repo_onboarding import RepoOnboarder


async def collect(files, services=None, mappings=None, getter=None):
    return await RepoOnboarder()._collect_service_sources(
        services or [{"name": "api", "language": "python"}],
        mappings or {"api": "api"}, list(files), getter or AsyncMock(side_effect=lambda path: files[path]))


@pytest.mark.asyncio
async def test_default_budget_reads_more_than_100_and_keeps_runtime_unmeasured():
    files = {f"api/file{number:03d}.py": "value = 1" for number in range(161)}
    _, result = await collect(files)
    assert result["files_read"] == result["files_attempted"] == 161
    assert result["indicators"]["source_scan"]["status"] == "complete"
    assert result["indicators"]["parser_support"]["status"] == "supported"
    assert result["indicators"]["runtime_verification"]["status"] == "not_measured"
    assert not result["static_partial"]
    assert result["scan_limits"] == {"max_files": 500, "max_total_bytes": 8 * 1024 * 1024, "max_file_bytes": MAX_SOURCE_BYTES}


@pytest.mark.asyncio
async def test_file_budget_is_fair_deterministic_and_reports_exact_omissions(monkeypatch):
    monkeypatch.setattr(settings, "REPO_SOURCE_MAX_FILES", 3)
    files = {"z/aaa.py": "", "z/main.py": "", "a/aaa.py": "", "a/main.py": ""}
    getter = AsyncMock(side_effect=lambda path: files[path])
    _, result = await collect(files, [{"name": "z", "language": "python"}, {"name": "a", "language": "python"}],
                              {"z": "z", "a": "a"}, getter)
    assert [call.args[0] for call in getter.await_args_list] == ["a/main.py", "z/main.py", "a/aaa.py"]
    scan = result["indicators"]["source_scan"]
    assert (scan["eligible_files"], scan["read_files"], scan["omitted_files"]) == (4, 3, 1)
    assert scan["status"] == "partial"
    assert scan["reason_counts"] == {"source_file_limit_reached": 1}


@pytest.mark.asyncio
async def test_total_byte_budget_stops_fetches_and_accounts_for_rejected_boundary_file(monkeypatch):
    monkeypatch.setattr(settings, "REPO_SOURCE_MAX_TOTAL_BYTES", 20)
    files = {f"api/{number}.py": "#" * 12 for number in range(4)}
    getter = AsyncMock(side_effect=lambda path: files[path])
    _, result = await collect(files, getter=getter)
    assert getter.await_count == 2
    assert result["files_read"] == 1 and result["bytes_read"] == 12
    assert result["bytes_fetched"] == 24
    assert result["scan_reason_counts"] == {"total_source_limit_reached": 3}
    assert result["indicators"]["source_scan"]["omitted_files"] == 3


@pytest.mark.asyncio
async def test_source_limits_missing_files_and_parser_failures_do_not_mix_dimensions():
    files = {"api/a.py": "#" * (MAX_SOURCE_BYTES + 1), "api/b.py": "def invalid(:", "api/c.py": ""}

    async def getter(path):
        if path == "api/c.py":
            raise ValueError("Source unavailable")
        return files[path]

    _, result = await collect(files, getter=getter)
    assert result["files_read"] == 1
    assert result["scan_reason_counts"] == {"source_size_limit": 1, "source_unavailable": 1}
    assert result["indicators"]["parser_support"]["failed_files"] == 1
    assert result["indicators"]["parser_support"]["status"] == "partial"
    assert result["indicators"]["source_scan"]["omitted_files"] == 2


@pytest.mark.asyncio
async def test_rate_limit_aborts_remaining_calls_and_preserves_read_work():
    files = {f"api/{number}.py": "" for number in range(10)}
    getter = AsyncMock(side_effect=["", GitHubRateLimitError(60)])
    _, result = await collect(files, getter=getter)
    assert getter.await_count == 2 and result["files_read"] == 1
    assert result["scan_reason_counts"] == {"github_rate_limit": 9}
    assert result["indicators"]["source_scan"]["status"] == "partial"


@pytest.mark.asyncio
async def test_unreadable_source_reserves_budget_without_inventing_bytes_read(monkeypatch):
    monkeypatch.setattr(settings, "REPO_SOURCE_MAX_TOTAL_BYTES", MAX_SOURCE_BYTES * 2)
    files = {f"api/{number}.py": "" for number in range(5)}
    getter = AsyncMock(side_effect=UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid byte"))
    _, result = await collect(files, getter=getter)
    assert getter.await_count == 2
    assert result["byte_budget_used"] == MAX_SOURCE_BYTES * 2
    assert result["bytes_read"] == result["bytes_fetched"] == result["files_read"] == 0
    assert result["scan_reason_counts"] == {"source_unavailable": 2, "total_source_limit_reached": 3}


@pytest.mark.asyncio
async def test_complete_mapped_scan_discloses_exclusions_and_missing_declared_sources():
    files = {"api/main.py": "", "api/main.go": "package main", "optional/main.py": "", "api/vendor/lib.py": ""}
    services = [{"name": "api", "language": "python"}, {"name": "external", "source_expected": False},
                {"name": "missing", "source_expected": True, "language": "python"}]
    _, result = await collect(files, services)
    source = result["indicators"]["source_scan"]
    parser = result["indicators"]["parser_support"]
    assert source["status"] == "complete"
    assert source["excluded_source_files"] == source["unmapped_source_files"] == 1
    assert source["missing_source_services"] == ["missing"]
    assert source["external_source_services"] == ["external", "missing"]
    assert parser["parsed_files"] == parser["heuristic_files"] == 1
    assert parser["unsupported_contract_services"] == ["api"]
    assert result["static_partial"]


@pytest.mark.asyncio
async def test_no_source_is_unavailable_not_complete_zero_of_zero():
    _, result = await collect({"README.md": "text"})
    assert result["indicators"]["source_scan"]["status"] == "unavailable"
    assert result["indicators"]["parser_support"]["status"] == "unavailable"
    assert result["indicators"]["runtime_verification"]["status"] == "not_measured"


@pytest.mark.asyncio
@pytest.mark.parametrize("extension", ["js", "ts", "tsx", "jsx"])
async def test_empty_javascript_module_is_read_and_syntax_parsed(extension):
    _, result = await collect({f"api/main.{extension}": ""})
    assert result["files_read"] == 1
    assert result["parsers"] == {"tree_sitter": 1}
    assert result["indicators"]["parser_support"]["status"] == "supported"


def test_legacy_measurements_are_derived_without_promoting_umbrella_status():
    old = {"candidate_files": 4, "files_read": 4, "parsers": {"ast": 3, "failed": 1}, "partial": True,
           "warnings": ["static_topology_is_not_complete_runtime_communication"]}
    result = coverage_indicators(old)
    assert result["source_scan"]["status"] == "complete"
    assert result["source_scan"]["excluded_source_files"] is None
    assert result["parser_support"]["status"] == "partial"
    assert result["runtime_verification"]["status"] == "not_measured"
    missing = coverage_indicators({"partial": False})
    assert missing["source_scan"]["status"] == missing["parser_support"]["status"] == "unavailable"
    assert missing["runtime_verification"]["status"] == "unavailable"
    assert missing["source_scan"]["read_files"] is None


@pytest.mark.parametrize("counts", [
    {"candidate_files": 1, "files_read": 2},
    {"candidate_files": 2, "files_read": 2, "files_attempted": 1},
    {"candidate_files": 2, "files_read": 2, "files_attempted": 3},
    {"candidate_files": 2, "files_read": 2, "files_attempted": True},
    {"candidate_files": True, "files_read": 1},
    {"candidate_files": 1, "files_read": -1},
])
def test_inconsistent_source_counts_never_produce_complete(counts):
    assert coverage_indicators(counts)["source_scan"]["status"] == "unavailable"


@pytest.mark.parametrize("parsers", [{}, {"ast": 2, "failed": 1}, {"ast": -1}, {"ast": True}])
def test_inconsistent_or_missing_parser_counts_never_produce_supported(parsers):
    result = coverage_indicators({"files_read": 2, "parsers": parsers})["parser_support"]
    assert result["status"] == "unavailable"
    if not parsers:
        assert result["parsed_files"] is None


@pytest.mark.asyncio
async def test_runtime_caveat_does_not_downgrade_complete_static_change_evidence():
    _, coverage = await collect({"api/main.py": "value = 1"})
    coverage.update(partial=True, warnings=["static_topology_is_not_complete_runtime_communication"])
    snapshot = {"services": [{"name": "api"}], "file_mappings": {"api": "api"}, "coverage": coverage}
    item = GitAnalyzer()._build_change("api/main.py", "modified", "value = 1", "value = 2")
    with RegistryManager.use_snapshot(snapshot, "coverage-regression"):
        value, status, evidence = assess_evidence([item], snapshot)
        assert (value, status) == (1, "supported")
        assert evidence["reasons"] == []
        assert evidence["topology_indicators"]["runtime_verification"]["status"] == "not_measured"
        legacy = {**snapshot, "coverage": {key: value for key, value in coverage.items() if key != "coverage_schema_version"}}
        assert assess_evidence([item], legacy)[1] == "partial"


@pytest.mark.parametrize("field,value", [("REPO_SOURCE_MAX_FILES", 0), ("REPO_SOURCE_MAX_FILES", 5001),
                                        ("REPO_SOURCE_MAX_TOTAL_BYTES", 128), ("REPO_SOURCE_MAX_TOTAL_BYTES", 65 * 1024 * 1024)])
def test_scan_budget_configuration_has_bounded_validated_range(field, value):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{field: value})
