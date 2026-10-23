"""Public fallback must stay pinned, bounded and separate from private access."""
import io
import tarfile
from unittest.mock import AsyncMock

import pytest

from services.git_analyzer import GitAnalyzer, GitHubAPIClient, GitHubRateLimitError
from services.public_github_source import PublicGitHubArchive


def archive(files):
    result = io.BytesIO()
    with tarfile.open(fileobj=result, mode="w:gz") as target:
        for path, value in files.items():
            entry = tarfile.TarInfo("repo-sha/" + path)
            entry.size = len(value)
            target.addfile(entry, io.BytesIO(value))
    return result.getvalue()


def test_archive_keeps_empty_binary_and_oversized_source_distinct():
    value = PublicGitHubArchive.from_bytes(archive({"empty.py": b"", "binary.py": b"\xff", "big.py": b"x" * 262145}), "a" * 40)
    assert value.read("empty.py") == ""
    with pytest.raises(ValueError, match="binary"):
        value.read("binary.py")
    with pytest.raises(ValueError, match="256 KiB"):
        value.read("big.py")
    with pytest.raises(ValueError, match="absent"):
        value.read("missing.py")
    assert value.evidence["executed_source"] is False
    assert value.digests["big.py"] is not None


@pytest.mark.parametrize("path", ["../secret", "root/../../secret", "/absolute", "x\\secret"])
def test_archive_rejects_path_traversal_without_extracting(path):
    with pytest.raises(ValueError, match="Unsafe"):
        PublicGitHubArchive.from_bytes(archive({path: b"x"}), "a" * 40)


def test_expanded_size_and_file_bounds_are_enforced(monkeypatch):
    monkeypatch.setattr("services.public_github_source.MAX_EXPANDED_BYTES", 2)
    with pytest.raises(ValueError, match="expanded"):
        PublicGitHubArchive.from_bytes(archive({"a": b"xxx"}), "a" * 40)
    monkeypatch.setattr("services.public_github_source.MAX_EXPANDED_BYTES", 100)
    monkeypatch.setattr("services.public_github_source.MAX_ARCHIVE_FILES", 1)
    with pytest.raises(ValueError, match="expanded"):
        PublicGitHubArchive.from_bytes(archive({"a": b"x", "b": b"y"}), "a" * 40)


@pytest.mark.asyncio
async def test_anonymous_quota_fallback_reuses_one_exact_archive(httpx_mock, monkeypatch):
    client = GitHubAPIClient(token="")
    client._headers.pop("Authorization", None)
    value = PublicGitHubArchive.from_bytes(archive({"main.py": b"value=1", "empty.py": b""}), "a" * 40)
    fetch = AsyncMock(return_value=value)
    monkeypatch.setattr(PublicGitHubArchive, "fetch", fetch)
    httpx_mock.add_response(status_code=403, headers={"x-ratelimit-remaining": "0"})
    assert await client.get_repo_tree("owner", "repo", "a" * 40) == ["empty.py", "main.py"]
    assert await client.get_file_content("owner", "repo", "main.py", "a" * 40) == "value=1"
    assert await client.get_file_content("owner", "repo", "empty.py", "a" * 40) == ""
    assert fetch.await_count == len(httpx_mock.get_requests()) == 1
    client._headers["Authorization"] = "Bearer different-private-scope"
    client._sync_identity()
    assert client._public_archives == {}


@pytest.mark.asyncio
async def test_private_rate_limit_never_falls_back_to_public_archive(httpx_mock, monkeypatch):
    fetch = AsyncMock()
    monkeypatch.setattr(PublicGitHubArchive, "fetch", fetch)
    httpx_mock.add_response(status_code=403, headers={"x-ratelimit-remaining": "0"})
    with pytest.raises(GitHubRateLimitError):
        await GitHubAPIClient(token="private-token").get_repo_tree("owner", "repo", "a" * 40)
    fetch.assert_not_awaited()


@pytest.mark.asyncio
async def test_public_actual_parent_comparison_uses_sources_and_reports_limits(monkeypatch):
    analyzer = GitAnalyzer()
    analyzer.resolve_commit_sha = AsyncMock(return_value="b" * 40)
    old = PublicGitHubArchive.from_bytes(archive({"main.py": b"value=1\n", "same.py": b""}), "a" * 40)
    new = PublicGitHubArchive.from_bytes(archive({"main.py": b"value=2\n", "same.py": b""}), "b" * 40)
    analyzer._gh._public_archive = AsyncMock(side_effect=[new, old])
    monkeypatch.setattr("services.public_github_source.public_commit_metadata", lambda *args: {
        "sha": "b" * 40, "parents": ["a" * 40], "timestamp": 123})
    changes = await analyzer._analyze_public_archives("owner", "repo", "main")
    assert len(changes) == 1
    assert changes[0].old_content == "value=1\n" and changes[0].new_content == "value=2\n"
    assert changes[0].base_sha == "a" * 40 and changes[0].commit_timestamp == 123
    assert analyzer.last_extraction["transport_evidence"]["executed_source"] is False
    assert "rename_detection_unavailable" in analyzer.last_extraction["warnings"][0]


@pytest.mark.asyncio
async def test_unchanged_oversized_blobs_are_not_reported_as_changes(monkeypatch):
    analyzer = GitAnalyzer()
    analyzer.resolve_commit_sha = AsyncMock(return_value="b" * 40)
    common = b"x" * 262145
    old = PublicGitHubArchive.from_bytes(archive({"generated.py":common, "main.py":b"value=1"}), "a"*40)
    new = PublicGitHubArchive.from_bytes(archive({"generated.py":common, "main.py":b"value=2"}), "b"*40)
    analyzer._gh._public_archive = AsyncMock(side_effect=[new,old])
    monkeypatch.setattr("services.public_github_source.public_commit_metadata", lambda *args:{"sha":"b"*40,"parents":["a"*40],"timestamp":123})
    result = await analyzer._analyze_public_archives("owner","repo","main")
    assert [item.file_path for item in result] == ["main.py"]
