"""Review generated caches without touching source, dependencies or saved data.

The default is a dry run which writes a private manifest under scratch/.
Use --apply only after reviewing the plan. This command never removes installed
dependencies, browser profile databases, credentials, source archives or backups.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
BROWSER_CACHES = frozenset({"GrShaderCache", "ShaderCache", "GraphiteDawnCache", "DawnCache",
    "Cache", "Code Cache", "GPUCache", "DawnGraphiteCache", "DawnWebGPUCache"})
EXCLUDED = frozenset({".git", "node_modules", "venv", "env", "ENV", ".kiro", ".impeccable"})
PROTECTED_SUFFIXES = frozenset({".db", ".sqlite", ".sqlite3", ".sqlite-wal", ".sqlite-shm",
    ".key", ".pem", ".pfx", ".p12", ".crt", ".zip", ".gz", ".tgz", ".tar", ".7z", ".rar",
    ".py", ".js", ".jsx", ".ts", ".tsx", ".css", ".html", ".json", ".toml", ".yaml", ".yml",
    ".md", ".txt", ".sh", ".ps1", ".bat", ".cmd", ".exe", ".dll", ".pyd", ".so",
    ".png", ".jpg", ".jpeg", ".svg", ".pdf", ".docx"})
PROTECTED_NAMES = frozenset({"Cookies", "Cookies-journal", "Login Data", "Login Data-journal",
    "History", "History-journal", "Web Data", "Web Data-journal", "Favicons", "Favicons-journal",
    ".neon"})
PYTEST_FILES = frozenset({"README.md", ".gitignore", "CACHEDIR.TAG", "v/cache/nodeids",
    "v/cache/lastfailed", "v/cache/stepwise"})


class CleanupError(RuntimeError):
    pass


@dataclass(frozen=True)
class Candidate:
    path: str
    kind: str
    directory: bool
    bytes: int
    files: int
    signature: str


def is_reparse(path: Path) -> bool:
    value = path.lstat()
    return stat.S_ISLNK(value.st_mode) or bool(getattr(value, "st_file_attributes", 0) & 0x400)


def checked_root(path: Path) -> Path:
    absolute = Path(os.path.abspath(path))
    if not absolute.is_dir():
        raise CleanupError("The workspace must be an existing directory.")
    for entry in (absolute, *absolute.parents):
        if is_reparse(entry):
            raise CleanupError("Workspace symlinks and reparse points are not allowed.")
    return absolute.resolve(strict=True)


def checked_path(root: Path, relative: str) -> Path:
    raw = Path(relative)
    if raw.is_absolute() or ".." in raw.parts:
        raise CleanupError("A cleanup target is outside the workspace.")
    path = root / raw
    if path == root or not path.is_relative_to(root):
        raise CleanupError("A cleanup target is outside the workspace.")
    for entry in (path, *path.parents):
        if not entry.is_relative_to(root):
            break
        if is_reparse(entry):
            raise CleanupError("Cleanup targets must not contain symlinks or reparse points.")
    if not path.resolve(strict=True).is_relative_to(root):
        raise CleanupError("A cleanup target resolves outside the workspace.")
    return path


def tracked_files(root: Path) -> set[str]:
    try:
        top = subprocess.run(["git", "-C", str(root), "rev-parse", "--show-toplevel"],
                             capture_output=True, check=True, text=True)
        if Path(top.stdout.strip()).resolve() != root:
            raise CleanupError("Select the repository root, not a parent or nested directory.")
        result = subprocess.run(["git", "-C", str(root), "ls-files", "-z"], capture_output=True, check=True)
    except (OSError, subprocess.CalledProcessError) as error:
        raise CleanupError("Cannot verify Git tracking. No cleanup is allowed.") from error
    return {os.fsdecode(value).replace("\\", "/") for value in result.stdout.split(b"\0") if value}


def ignored_directory(path: Path, root: Path) -> bool:
    relative = path.relative_to(root)
    return (path.name in EXCLUDED or path.name.startswith(".venv")
        or relative.parts[:2] == (".github", "skills")
        or (len(relative.parts) > 1 and relative.parts[0] == "scratch"
            and relative.parts[1].startswith("preservation-")))


def files_below(path: Path) -> list[Path]:
    if is_reparse(path):
        raise CleanupError("A candidate is a symlink or reparse point.")
    if not path.is_dir():
        return [path]
    files = []
    for entry in path.iterdir():
        if is_reparse(entry):
            raise CleanupError("A candidate contains a symlink or reparse point.")
        files.extend(files_below(entry) if entry.is_dir() else [entry])
    return files


def protected_file(path: Path) -> bool:
    name = path.name.lower()
    return (path.suffix.lower() in PROTECTED_SUFFIXES or path.name in PROTECTED_NAMES
        or name.startswith(".env") or name.endswith(".env") or ".env." in name)


def source_for_bytecode(path: Path) -> Path:
    if path.parent.name == "__pycache__":
        return path.parent.parent / (path.name.split(".", 1)[0] + ".py")
    return path.with_suffix(".py")


def inspect_candidate(root: Path, relative: str, kind: str, tracked: set[str]) -> Candidate:
    path = checked_path(root, relative)
    relative = path.relative_to(root).as_posix()
    prefix = relative + "/"
    if any(name == relative or name.startswith(prefix) for name in tracked):
        raise CleanupError("Candidate includes a Git-tracked file.")
    parts = Path(relative).parts
    browser = (len(parts) >= 3 and parts[0] == "scratch"
               and re.fullmatch(r"release-\d{4}-\d{2}-\d{2}", parts[1]) is not None)
    if kind == "browser-cache":
        allowed = browser and path.is_dir() and path.name in BROWSER_CACHES
    elif kind == "browser-performance-metrics":
        allowed = browser and path.is_file() and path.suffix == ".pma"
    elif kind == "python-bytecode":
        allowed = path.name == "__pycache__" if path.is_dir() else path.suffix in {".pyc", ".pyo"}
        allowed = allowed and not any(ignored_directory(parent, root) for parent in (path, *path.parents)
                                      if parent != root and parent.is_relative_to(root))
    elif kind == "pytest-cache":
        allowed = relative == ".pytest_cache" and path.is_dir()
    else:
        allowed = False
    if not allowed:
        raise CleanupError("Candidate is outside the cache allowlist.")
    files = sorted(files_below(path))
    for file in files:
        if kind == "python-bytecode":
            source = source_for_bytecode(file)
            if file.suffix not in {".pyc", ".pyo"} or not source.is_file() or is_reparse(source):
                raise CleanupError("Bytecode has no preserved source file or contains reusable files.")
        elif kind == "pytest-cache":
            if file.relative_to(path).as_posix() not in PYTEST_FILES:
                raise CleanupError("Pytest cache includes an unrecognized file.")
        elif protected_file(file):
            raise CleanupError("Candidate contains source, data, credentials, an archive or evidence.")
    signature = hashlib.sha256()
    size = 0
    for file in files:
        info = file.stat()
        size += info.st_size
        signature.update(json.dumps([file.relative_to(root).as_posix(), info.st_size, info.st_mtime_ns]).encode())
    return Candidate(relative, kind, path.is_dir(), size, len(files), signature.hexdigest())


def preservation_snapshot(root: Path, tracked: set[str]) -> dict[str, str]:
    result = {}
    def visit(directory):
        for entry in directory.iterdir():
            if is_reparse(entry):
                continue
            if entry.is_dir():
                if entry.name not in EXCLUDED and not entry.name.startswith(".venv"):
                    visit(entry)
            elif protected_file(entry) or entry.relative_to(root).as_posix() in tracked:
                result[entry.relative_to(root).as_posix()] = hashlib.sha256(entry.read_bytes()).hexdigest()
    visit(root)
    return result


def build_plan(root: Path, tracked: set[str] | None = None) -> dict:
    root = checked_root(root)
    tracked = tracked_files(root) if tracked is None else tracked
    candidates, refusals = [], []
    def add(path, kind):
        relative = path.relative_to(root).as_posix()
        try:
            candidates.append(inspect_candidate(root, relative, kind, tracked))
        except CleanupError as error:
            refusals.append({"path": relative, "reason": str(error)})
    def visit(directory):
        for entry in directory.iterdir():
            relative = entry.relative_to(root)
            if is_reparse(entry):
                refusals.append({"path": relative.as_posix(), "reason": "Symlink or reparse point retained."})
                continue
            if entry.is_dir():
                if ignored_directory(entry, root):
                    continue
                browser = len(relative.parts) >= 3 and relative.parts[0] == "scratch" and re.fullmatch(
                    r"release-\d{4}-\d{2}-\d{2}", relative.parts[1]) is not None
                if entry.name == "__pycache__":
                    add(entry, "python-bytecode")
                elif relative.as_posix() == ".pytest_cache":
                    add(entry, "pytest-cache")
                elif browser and entry.name in BROWSER_CACHES:
                    add(entry, "browser-cache")
                else:
                    visit(entry)
            elif entry.suffix in {".pyc", ".pyo"}:
                add(entry, "python-bytecode")
            elif (entry.suffix == ".pma" and len(relative.parts) >= 3 and relative.parts[0] == "scratch"
                  and re.fullmatch(r"release-\d{4}-\d{2}-\d{2}", relative.parts[1])):
                add(entry, "browser-performance-metrics")
    visit(root)
    return {"schema_version": 1, "created_utc": datetime.now(timezone.utc).isoformat(),
            "workspace": str(root), "status": "dry_run", "planned_bytes": sum(item.bytes for item in candidates),
            "targets": [asdict(item) for item in candidates], "retained_candidates": refusals,
            "tracked_paths": sorted(tracked), "preservation_sha256": preservation_snapshot(root, tracked)}


POWERSHELL_REMOVE = r"""
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath($env:MDT_CACHE_CLEANUP_ROOT).TrimEnd('\')
$target = [IO.Path]::GetFullPath($env:MDT_CACHE_CLEANUP_TARGET)
if (-not $target.StartsWith($root + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Outside workspace.' }
$item = Get-Item -LiteralPath $target -Force
$cursor = $item
while ($null -ne $cursor -and $cursor.FullName.StartsWith($root, [StringComparison]::OrdinalIgnoreCase)) {
    if (($cursor.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw 'Reparse point.' }
    $cursor = if ($cursor.PSIsContainer) { $cursor.Parent } else { $cursor.Directory }
}
if ($item.PSIsContainer) {
    if (@(Get-ChildItem -LiteralPath $target -Recurse -Force | Where-Object {
        ($_.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0
    }).Count -gt 0) { throw 'Nested reparse point.' }
    Remove-Item -LiteralPath $target -Recurse -Force
} else {
    Remove-Item -LiteralPath $target -Force
}
"""


def remove_cache(root: Path, candidate: Candidate) -> None:
    path = checked_path(root, candidate.path)
    if os.name == "nt":
        executable = shutil.which("pwsh.exe") or shutil.which("powershell.exe")
        if not executable:
            raise CleanupError("PowerShell is required for Windows cache cleanup.")
        env = {**os.environ, "MDT_CACHE_CLEANUP_ROOT": str(root), "MDT_CACHE_CLEANUP_TARGET": str(path)}
        result = subprocess.run([executable, "-NoProfile", "-NonInteractive", "-Command", "-"],
                                input=POWERSHELL_REMOVE, env=env, capture_output=True, text=True)
        if result.returncode:
            raise CleanupError("Native cache removal failed. Review the manifest before retrying.")
    elif candidate.directory:
        shutil.rmtree(path)
    else:
        path.unlink()


def changed_preserved_files(root: Path, snapshot: dict[str, str]) -> list[str]:
    changed = []
    for relative, digest in snapshot.items():
        path = root / relative
        if not path.is_file() or is_reparse(path) or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            changed.append(relative)
    return changed


def apply_plan(plan: dict, tracked: set[str] | None = None, remover=None) -> dict:
    root = checked_root(Path(plan["workspace"]))
    tracked = tracked_files(root) if tracked is None else tracked
    if sorted(tracked) != plan["tracked_paths"] or changed_preserved_files(root, plan["preservation_sha256"]):
        raise CleanupError("Source tracking or preserved files changed. Generate a fresh dry-run plan.")
    candidates = [Candidate(**item) for item in plan["targets"]]
    # Validate every target before the first removal, then recheck immediately
    # before each operation. An old or modified manifest is not permission.
    for candidate in candidates:
        if inspect_candidate(root, candidate.path, candidate.kind, tracked) != candidate:
            raise CleanupError("A cache changed after inspection. Generate a fresh dry-run plan.")
    removed, failed = [], []
    for candidate in candidates:
        try:
            if inspect_candidate(root, candidate.path, candidate.kind, tracked) != candidate:
                raise CleanupError("Cache changed immediately before removal.")
            (remover or remove_cache)(root, candidate)
            if (root / candidate.path).exists():
                raise CleanupError("Cache removal did not finish.")
            removed.append(candidate)
        except (CleanupError, OSError):
            failed.append(candidate.path)
            break
    changes = changed_preserved_files(root, plan["preservation_sha256"])
    return {"status": "failed" if failed or changes else "applied", "removed_targets": len(removed),
            "reclaimed_bytes": sum(item.bytes for item in removed), "failed_targets": failed,
            "preserved_files_unchanged": not changes, "changed_preserved_paths": changes,
            "finished_utc": datetime.now(timezone.utc).isoformat()}


def write_manifest(root: Path, plan: dict) -> Path:
    scratch = root / "scratch"
    if scratch.exists() and is_reparse(scratch):
        raise CleanupError("The manifest directory is a symlink or reparse point.")
    scratch.mkdir(exist_ok=True)
    name = "cleanup-manifest-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-") + uuid.uuid4().hex[:8] + ".json"
    path = scratch / name
    with path.open("x", encoding="utf-8") as stream:
        json.dump(plan, stream, indent=2)
        stream.write("\n")
    return path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=Path, default=ROOT, help="Repository root; defaults to this script's project")
    parser.add_argument("--apply", action="store_true", help="Explicitly remove the reviewed cache allowlist; default is dry-run")
    args = parser.parse_args(argv)
    try:
        plan = build_plan(args.root)
        root = Path(plan["workspace"])
        manifest = write_manifest(root, plan)
        if args.apply:
            plan["results"] = apply_plan(plan)
            plan["status"] = plan["results"]["status"]
            manifest.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"status": plan["status"], "manifest": str(manifest), "targets": len(plan["targets"]),
                          "planned_bytes": plan["planned_bytes"], "retained_candidates": len(plan["retained_candidates"]),
                          "results": plan.get("results")}, indent=2))
        return 0 if plan["status"] in {"dry_run", "applied"} else 1
    except (CleanupError, OSError) as error:
        print(f"Cleanup stopped ({type(error).__name__}): {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
