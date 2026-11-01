"""Only disposable fixtures are removed; never run real-workspace cleanup in tests."""
from pathlib import Path

import pytest

from scripts.clean_generated_cache import CleanupError, apply_plan, build_plan, checked_path, inspect_candidate


def write(root, relative, content=b"fixture"):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def test_cache_plan_retains_source_databases_backups_and_dependencies(tmp_path):
    write(tmp_path, "backend/engine.py")
    write(tmp_path, "backend/__pycache__/engine.cpython-311.pyc")
    write(tmp_path, "backend/data/saved.sqlite3")
    write(tmp_path, "scratch/preservation-20261028/backup.pyc")
    write(tmp_path, ".venv/lib/__pycache__/library.pyc")
    write(tmp_path, "scratch/release-2026-10-25/profile/Cache/index")
    write(tmp_path, "scratch/release-2026-10-25/profile/GPUCache/cache.db")
    plan = build_plan(tmp_path, tracked=set())
    assert {item["path"] for item in plan["targets"]} == {
        "backend/__pycache__", "scratch/release-2026-10-25/profile/Cache"}
    assert plan["status"] == "dry_run"
    assert (tmp_path / "backend/data/saved.sqlite3").exists()
    assert any("GPUCache" in item["path"] for item in plan["retained_candidates"])


def test_cleanup_refuses_traversal_and_tracked_cache(tmp_path):
    write(tmp_path, "backend/engine.py")
    write(tmp_path, "backend/__pycache__/engine.cpython-311.pyc")
    with pytest.raises(CleanupError, match="outside"):
        checked_path(tmp_path, "../another-folder")
    with pytest.raises(CleanupError, match="tracked"):
        inspect_candidate(tmp_path, "backend/__pycache__", "python-bytecode",
                          {"backend/__pycache__/engine.cpython-311.pyc"})


def test_orphaned_bytecode_is_preserved_as_potentially_reusable(tmp_path):
    write(tmp_path, "backend/__pycache__/orphan.cpython-311.pyc")
    plan = build_plan(tmp_path, tracked=set())
    assert not plan["targets"]
    assert plan["retained_candidates"]


def test_changed_source_aborts_before_any_removal(tmp_path):
    source = write(tmp_path, "backend/engine.py")
    write(tmp_path, "backend/__pycache__/engine.cpython-311.pyc")
    plan = build_plan(tmp_path, tracked=set())
    source.write_bytes(b"new reusable work")
    calls = []
    with pytest.raises(CleanupError, match="preserved files changed"):
        apply_plan(plan, tracked=set(), remover=lambda *args: calls.append(args))
    assert not calls


def test_verified_fixture_cache_can_be_removed_while_source_is_unchanged(tmp_path):
    source = write(tmp_path, "backend/engine.py")
    cache = write(tmp_path, "backend/__pycache__/engine.cpython-311.pyc")
    plan = build_plan(tmp_path, tracked=set())
    def remove_fixture(root, candidate):
        target = root / candidate.path
        assert target.is_relative_to(tmp_path)
        for child in target.iterdir():
            child.unlink()
        target.rmdir()
    result = apply_plan(plan, tracked=set(), remover=remove_fixture)
    assert result["status"] == "applied" and result["preserved_files_unchanged"]
    assert not cache.exists()
    assert source.read_bytes() == b"fixture"
