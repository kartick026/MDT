"""
Git Analysis Service — Phase 4 (Week 5)
========================================
Handles real git diff parsing, file content retrieval, line counting,
and AST metadata extraction for the MDT analysis pipeline.

Two strategies for fetching diffs:
  1. GitHub REST API  — used when the repo is a GitHub URL and
     GITHUB_TOKEN is set. No local clone needed.
  2. Local gitpython — reads bounded immutable source snapshots from existing objects.

Remote access errors and missing revisions are explicit failures, never empty safe analyses.

AST extraction:
  - Python  : stdlib `ast` module (no extra deps)
  - JS / TS : bounded Tree-sitter syntax trees and literal routes
  - Others  : regex heuristics for functions / classes
"""
import ast
import asyncio
import logging
import os
import re
import subprocess
import hashlib
import json
import math
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Any, Set

import httpx
from git import Repo, InvalidGitRepositoryError, GitCommandError, NULL_TREE

from core.config import settings
from services.source_parser import (extract_python_routes, parse_js_ts, semantic_comparison,
                                    PythonModelContext, compare_schema_models, compare_route_contracts)

logger = logging.getLogger(__name__)

MAX_CHANGE_FILES = 100
MAX_SOURCE_BYTES = 256 * 1024
MAX_TOTAL_SOURCE_BYTES = 2 * 1024 * 1024
MAX_CACHE_BYTES = 4 * 1024 * 1024
MAX_CACHE_ENTRIES = 256
EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"


def _safe_source_path(path: str) -> str:
    path = str(path).replace("\\", "/")
    if not path or path.startswith("/") or any(part in {"..", ".git"} for part in path.split("/")) or ":" in path or "\x00" in path:
        raise ValueError("Source paths must be repository-relative paths without traversal.")
    return path



def extract_route_signatures(content: str, language: str = "python") -> List[Dict[str, Any]]:
    """Literal routes, with bounded local annotation evidence where supported."""
    if language == "python":
        return extract_python_routes(content)
    if language in {"javascript", "typescript"}:
        return parse_js_ts(content, language)["routes"]
    return []


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ChangeInfo:
    """All information about a single changed file in a push event."""
    file_path: str
    change_type: str          # added | modified | deleted
    diff_content: str         # raw unified diff text
    additions: int            # lines added
    deletions: int            # lines removed
    old_content: str          # file content before the commit
    new_content: str          # file content after the commit
    ast_metadata: Dict[str, Any] = field(default_factory=dict)
    previous_path: Optional[str] = None
    base_sha: str = ""
    commit_sha: str = ""
    extraction_status: str = "complete"
    extraction_warnings: List[str] = field(default_factory=list)
    is_binary: bool = False
    parser_coverage: str = "unknown"
    commit_timestamp: Optional[int] = None

    def __post_init__(self):
        # Normalise GitHub's "removed" → project-standard "deleted"
        if self.change_type == "removed":
            self.change_type = "deleted"
        if self.change_type not in {"added", "modified", "deleted", "renamed", "copied"}:
            self.change_type = "modified"

    @property
    def lines_changed(self) -> int:
        return self.additions + self.deletions

    @property
    def extension(self) -> str:
        return Path(self.file_path).suffix.lower()

    @property
    def language(self) -> str:
        return _EXT_TO_LANG.get(self.extension, "unknown")


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_EXT_TO_LANG: Dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".jsx": "javascript",
    ".tsx": "typescript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".mts": "typescript",
    ".cts": "typescript",
    ".java": "java",
    ".go": "go",
    ".rs": "rust",
    ".cpp": "cpp", ".cc": "cpp", ".cxx": "cpp",
    ".c": "c",
    ".h": "c",
    ".rb": "ruby",
    ".php": "php",
    ".cs": "csharp",
    ".kt": "kotlin",
    ".swift": "swift",
    ".html": "html",
    ".htm": "html",
    ".jinja": "html",
    ".jinja2": "html",
    ".j2": "html",
    ".ejs": "html",
    ".vue": "javascript",
    ".svelte": "javascript",
    ".css": "css",
    ".scss": "css",
    ".sass": "css",
    ".less": "css",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
    ".xml": "xml",
    ".sql": "sql",
    ".sh": "bash",
    ".bash": "bash",
    ".dockerfile": "dockerfile",
}

BINARY_EXTENSIONS: Set[str] = {
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".webp",
    ".woff", ".woff2", ".ttf", ".eot", ".otf",
    ".pdf", ".zip", ".tar", ".gz", ".7z", ".rar",
    ".exe", ".dll", ".so", ".dylib", ".bin",
    ".pyc", ".pyo", ".class", ".jar", ".war",
    ".lock",
}

SUPPORTED_EXTENSIONS = set(_EXT_TO_LANG.keys())


def is_supported_file(file_path: str) -> bool:
    """Return True if file is a code, template, config or markup file that should be analyzed."""
    p = Path(file_path)
    suffix = p.suffix.lower()
    name = p.name.lower()
    if suffix in BINARY_EXTENSIONS:
        return False
    if name in {"dockerfile", "dockerfile.dev", "makefile", "procfile", "gemfile"}:
        return True
    if suffix in SUPPORTED_EXTENSIONS:
        return True
    # If no suffix or standard text/config file, include it unless it's binary
    return suffix not in BINARY_EXTENSIONS

# GitHub API base
_GH_API = "https://api.github.com"


# ---------------------------------------------------------------------------
# Diff helpers
# ---------------------------------------------------------------------------

def _count_diff_lines(diff_text: str) -> tuple[int, int]:
    """
    Count added/deleted lines from a unified diff string.
    Returns (additions, deletions).
    """
    additions = 0
    deletions = 0
    for line in diff_text.splitlines():
        if line.startswith("+") and not line.startswith("+++"):
            additions += 1
        elif line.startswith("-") and not line.startswith("---"):
            deletions += 1
    return additions, deletions


def _parse_github_url(repo_url: str) -> Optional[tuple[str, str]]:
    """
    Extract (owner, repo) from a GitHub URL.
    Handles https://github.com/owner/repo and https://github.com/owner/repo.git
    Returns None if not a GitHub URL.
    """
    pattern = r"github\.com[:/]([^/]+)/([^/#?]+?)(?:\.git)?(?:[/?#]|$)"
    match = re.search(pattern, (repo_url or "").strip())
    if match:
        return match.group(1), match.group(2).removesuffix(".git")
    return None


# ---------------------------------------------------------------------------
# GitHub API client
# ---------------------------------------------------------------------------

class GitHubRateLimitError(ValueError):
    """Safe, actionable error evidence without request tokens or response bodies."""

    def __init__(self, retry_after_seconds: int):
        self.retry_after_seconds = max(1, retry_after_seconds)
        super().__init__(f"GitHub rate limit reached. Retry after {self.retry_after_seconds} seconds; analysis coverage is incomplete.")

    @property
    def evidence(self):
        return f"github_rate_limit:retry_after_seconds={self.retry_after_seconds}"


class GitHubAPIClient:
    """
    Thin async wrapper around the GitHub REST API.
    Used to fetch file contents and commit diffs without cloning.
    """
    def __init__(self, token: Optional[str] = None):
        self._token = token or settings.GITHUB_TOKEN or os.getenv("GITHUB_TOKEN", "")
        headers = {"Accept": "application/vnd.github+json",
                   "X-GitHub-Api-Version": "2022-11-28"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        self._headers = headers
        # Job/client scoped: private source never crosses clients/accounts or
        # persists to disk. Only full immutable SHAs are cacheable. Authentication
        # changes (e.g. installation-token rotation) invalidate this cache.
        self._source_cache = OrderedDict()
        self._cache_bytes = 0
        self._cache_identity = self._credential_identity()
        self._retry_at = 0.0
        self._public_archives = {}
        self.source_evidence = {}

    def _credential_identity(self):
        return hashlib.sha256(self._headers.get("Authorization", "").encode()).digest()

    def _sync_identity(self):
        identity = self._credential_identity()
        if identity != self._cache_identity:
            self._source_cache.clear()
            self._cache_bytes = 0
            self._retry_at = 0.0
            self._cache_identity = identity
            self._public_archives.clear()
            self.source_evidence = {}

    def _check_cooldown(self):
        self._sync_identity()
        if self._retry_at > time.time():
            raise GitHubRateLimitError(math.ceil(self._retry_at - time.time()))

    def _check_rate_limit(self, response):
        limited = response.status_code == 429 or response.status_code == 403 and (
            response.headers.get("x-ratelimit-remaining") == "0" or "retry-after" in response.headers)
        if not limited:
            return
        waits = [60.0]
        for header, absolute in (("retry-after", False), ("x-ratelimit-reset", True)):
            try:
                value = float(response.headers.get(header, ""))
                if math.isfinite(value):
                    waits.append(max(0, value - time.time()) if absolute else max(0, value))
            except ValueError:
                pass
        # Prefer documented retry times when present, using 60s only as fallback.
        wait = max(waits[1:]) if len(waits) > 1 else waits[0]
        self._retry_at = time.time() + max(1, wait)
        raise GitHubRateLimitError(math.ceil(max(1, wait)))

    def _remember_source(self, key, source):
        if key is None:
            return
        size = len(source.encode("utf-8"))
        if size > MAX_CACHE_BYTES:
            return
        previous = self._source_cache.pop(key, None)
        if previous is not None:
            self._cache_bytes -= len(previous.encode("utf-8"))
        self._source_cache[key] = source
        self._cache_bytes += size
        while self._cache_bytes > MAX_CACHE_BYTES or len(self._source_cache) > MAX_CACHE_ENTRIES:
            _, evicted = self._source_cache.popitem(last=False)
            self._cache_bytes -= len(evicted.encode("utf-8"))

    async def _request_with_retry(
        self,
        client: httpx.AsyncClient,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, Any]] = None,
        max_retries: int = 3,
    ) -> httpx.Response:
        """Make an HTTP GET request with exponential backoff for transient failures."""
        self._check_cooldown()
        req_headers = headers if headers is not None else self._headers
        last_exc = None
        resp: Optional[httpx.Response] = None
        for attempt in range(max_retries):
            try:
                resp = await client.get(url, headers=req_headers, params=params)
                self._check_rate_limit(resp)
                if resp.status_code >= 500 and attempt < max_retries - 1:
                    backoff = 0.3 * (2 ** attempt)
                    logger.debug("GitHub transient status %d on attempt %d for %s. Backoff %.1fs", resp.status_code, attempt + 1, url, backoff)
                    await asyncio.sleep(backoff)
                    continue
                return resp
            except (httpx.TransportError, httpx.TimeoutException) as exc:
                last_exc = exc
                if attempt < max_retries - 1:
                    backoff = 0.3 * (2 ** attempt)
                    logger.debug("GitHub transport error %s on attempt %d. Backoff %.1fs", exc, attempt + 1, backoff)
                    await asyncio.sleep(backoff)
                else:
                    raise
        if resp is not None:
            return resp
        if last_exc:
            raise last_exc
        raise httpx.RequestError(f"Failed request to {url} after {max_retries} retries", request=None)

    async def _public_archive(self, owner, repo, revision):
        from services.public_github_source import PublicGitHubArchive
        self._sync_identity()
        if self._headers.get("Authorization") or not re.fullmatch("[a-fA-F0-9]{40}", revision):
            raise ValueError("Anonymous archive fallback requires an exact public revision")
        key = (owner.lower(), repo.lower(), revision.lower())
        if key not in self._public_archives:
            archive = await PublicGitHubArchive.fetch(owner, repo, revision)
            self._public_archives.clear()
            self._public_archives[key] = archive
        self.source_evidence = self._public_archives[key].evidence
        return self._public_archives[key]

    async def get_repo_tree(self, owner, repo, tree_sha="main"):
        try:
            return await self._get_api_repo_tree(owner, repo, tree_sha)
        except GitHubRateLimitError:
            if self._headers.get("Authorization"):
                raise
            return sorted((await self._public_archive(owner, repo, tree_sha)).files)

    async def get_file_content(self, owner, repo, path, ref):
        path = _safe_source_path(path)
        self._sync_identity()
        key = (owner.lower(), repo.lower(), ref.lower())
        if key in self._public_archives:
            return self._public_archives[key].read(path)
        try:
            return await self._get_api_file_content(owner, repo, path, ref)
        except GitHubRateLimitError:
            if self._headers.get("Authorization"):
                raise
            return (await self._public_archive(owner, repo, ref)).read(path)

    async def _get_api_repo_tree(self, owner: str, repo: str, tree_sha: str = "main") -> List[str]:
        """Read one exact, bounded tree. Truncated trees cannot support complete onboarding."""
        from urllib.parse import quote
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await self._request_with_retry(client,
                f"{_GH_API}/repos/{owner}/{repo}/git/trees/{quote(tree_sha, safe='')}",
                params={"recursive": "1"}, max_retries=1)
        if response.status_code != 200:
            raise ValueError(f"Repository tree is unavailable (GitHub HTTP {response.status_code}).")
        if len(response.content) > 8 * 1024 * 1024:
            raise ValueError("Repository tree exceeds the onboarding limit.")
        data = response.json()
        if data.get("truncated") or len(data.get("tree", [])) > 20000:
            raise ValueError("Repository tree exceeds the bounded alpha limit; select a smaller repository.")
        return [_safe_source_path(item["path"]) for item in data.get("tree", [])
                if item.get("type") == "blob"]

    async def _get_api_file_content(self, owner: str, repo: str, path: str, ref: str) -> str:
        """Read a bounded UTF-8 blob at exactly the requested ref; no branch substitution."""
        from urllib.parse import quote
        path = _safe_source_path(path)
        self._sync_identity()
        key = (owner.lower(), repo.lower(), ref.lower(), path) if re.fullmatch(r"[0-9a-fA-F]{40}", ref) else None
        if key is not None and key in self._source_cache:
            self._source_cache.move_to_end(key)
            return self._source_cache[key]
        self._check_cooldown()
        url = f"{_GH_API}/repos/{owner}/{repo}/contents/{quote(path, safe='/')}"
        headers = {**self._headers, "Accept": "application/vnd.github.raw+json"}
        async with httpx.AsyncClient(timeout=8.0) as client:
            async with client.stream("GET", url, params={"ref": ref}, headers=headers) as response:
                self._check_rate_limit(response)
                if response.status_code != 200:
                    raise ValueError(f"Source unavailable (GitHub HTTP {response.status_code}).")
                content = bytearray()
                async for chunk in response.aiter_bytes():
                    content.extend(chunk)
                    if len(content) > MAX_SOURCE_BYTES:
                        raise ValueError("Source exceeds the 256 KiB per-file limit.")
                source = bytes(content).decode("utf-8")
                self._remember_source(key, source)
                return source

    async def get_commit_diff(
        self,
        owner: str,
        repo: str,
        commit_sha: str,
    ) -> Optional[Dict[str, str]]:
        """
        Return a dict of {file_path: diff_text} for all files in a commit.
        Returns ``None`` when the commit cannot be read.  An empty dict is a
        valid response for a commit with no textual file changes, so callers
        can distinguish that case from an authentication or lookup failure.
        """
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                url = f"{_GH_API}/repos/{owner}/{repo}/commits/{commit_sha}"
                resp = await self._request_with_retry(
                    client,
                    url,
                    headers={**self._headers, "Accept": "application/vnd.github.diff"}
                )
                if resp.status_code == 200:
                    return _split_diff_by_file(resp.text)
                logger.warning("GitHub commit diff API → %d", resp.status_code)
        except Exception as exc:
            logger.warning("get_commit_diff failed: %s", exc)
        return None



def _split_diff_by_file(full_diff: str) -> Dict[str, str]:
    """
    Split a full unified diff (multiple files) into per-file diff strings.
    Keys are file paths (strips a/ b/ prefixes).
    """
    result: Dict[str, str] = {}
    current_file: Optional[str] = None
    current_lines: List[str] = []

    for line in full_diff.splitlines(keepends=True):
        if line.startswith("diff --git "):
            if current_file and current_lines:
                result[current_file] = "".join(current_lines)
            # extract filename from "diff --git a/path b/path"
            parts = line.split(" b/", 1)
            current_file = parts[1].strip() if len(parts) == 2 else None
            current_lines = [line]
        elif current_file is not None:
            current_lines.append(line)

    if current_file and current_lines:
        result[current_file] = "".join(current_lines)

    return result


# ---------------------------------------------------------------------------
# AST Analyzer
# ---------------------------------------------------------------------------

class ASTAnalyzer:
    """
    Extracts structural metadata from source code.
    - Python: uses stdlib `ast` — accurate function/class/import detection.
    - JS/TS: Tree-sitter syntax trees; other languages: regex heuristics.
    """

    # ---- public API ----

    def analyze(self, content: str, language: str) -> Dict[str, Any]:
        """Return metadata dict with functions, classes, imports, exports."""
        if not content:
            return self._empty(language)
        try:
            if language == "python":
                return self._parse_python(content)
            elif language in ("javascript", "typescript"):
                return self._parse_js_ts(content, language)
            elif language == "java":
                return self._parse_java(content)
            elif language == "go":
                return self._parse_go(content)
            else:
                return self._parse_generic(content, language)
        except Exception as exc:
            logger.debug("AST parse failed for %s: %s", language, exc)
            return self._empty(language)

    # ---- Python (stdlib ast) ----

    def _parse_python(self, content: str) -> Dict[str, Any]:
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return self._parse_generic(content, "python")

        functions: List[str] = []
        classes: List[str] = []
        imports: List[str] = []

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                functions.append(node.name)
            elif isinstance(node, ast.ClassDef):
                classes.append(node.name)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                for alias in node.names:
                    imports.append(f"{module}.{alias.name}" if module else alias.name)

        return {
            "language": "python",
            "functions": list(dict.fromkeys(functions)),   # dedupe, preserve order
            "classes": list(dict.fromkeys(classes)),
            "imports": list(dict.fromkeys(imports)),
            "exports": [],
        }

    # ---- JavaScript / TypeScript ----

    def _parse_js_ts(self, content: str, language: str) -> Dict[str, Any]:
        return parse_js_ts(content, language)

    # ---- Java ----

    def _parse_java(self, content: str) -> Dict[str, Any]:
        functions = re.findall(
            r'(?:public|private|protected|static|\s)+[\w<>\[\]]+\s+(\w+)\s*\(', content)
        classes = re.findall(r'\bclass\s+(\w+)', content)
        imports = re.findall(r'^import\s+([\w.]+);', content, re.MULTILINE)
        return {"language": "java", "functions": list(dict.fromkeys(functions)),
                "classes": list(dict.fromkeys(classes)),
                "imports": list(dict.fromkeys(imports)), "exports": []}

    # ---- Go ----

    def _parse_go(self, content: str) -> Dict[str, Any]:
        functions = re.findall(r'\bfunc\s+(?:\(\w+\s+\*?\w+\)\s+)?(\w+)\s*\(', content)
        imports_block = re.findall(r'"([^"]+)"', content)
        return {"language": "go", "functions": list(dict.fromkeys(functions)),
                "classes": [], "imports": list(dict.fromkeys(imports_block)),
                "exports": []}

    # ---- Generic regex ----

    def _parse_generic(self, content: str, language: str) -> Dict[str, Any]:
        functions = re.findall(r'\bdef\s+(\w+)\s*\(', content)  # py-style
        functions += re.findall(r'\bfunction\s+(\w+)\s*\(', content)  # js-style
        classes = re.findall(r'\bclass\s+(\w+)', content)
        return {"language": language, "functions": list(dict.fromkeys(functions)),
                "classes": list(dict.fromkeys(classes)),
                "imports": [], "exports": []}

    @staticmethod
    def _empty(language: str) -> Dict[str, Any]:
        return {"language": language, "functions": [], "classes": [],
                "imports": [], "exports": []}


# ---------------------------------------------------------------------------
# Local repository detection helpers
# ---------------------------------------------------------------------------

def _find_git_dir() -> Optional[Path]:
    """Locate the .git directory either in local dev or Docker container mount."""
    candidates = [
        Path("/app/.git"),
        Path(__file__).resolve().parent.parent / ".git",
        Path(__file__).resolve().parent.parent.parent / ".git",
        Path("/workspace/.git"),
        Path(".git"),
    ]
    for p in candidates:
        try:
            if p.is_dir() or (p.is_file() and p.name == ".git"):
                return p
        except Exception as exc:
            logger.debug("Failed checking git dir candidate %s: %s", p, exc)
            continue
    return None


def _is_local_workspace_match(repo_url: str) -> bool:
    """Check if repo_url refers to this local repository workspace."""
    try:
        from core.registry import RegistryManager
        req_key = RegistryManager.repository_key(repo_url)
        git_dir = _find_git_dir()
        if git_dir and git_dir.exists():
            config_file = git_dir / "config"
            if config_file.is_file():
                content = config_file.read_text(encoding="utf-8", errors="ignore")
                for line in content.splitlines():
                    if "url =" in line:
                        cfg_url = line.split("=", 1)[1].strip()
                        if RegistryManager.repository_key(cfg_url) == req_key:
                            return True
            res = subprocess.run(
                ["git", "--git-dir", str(git_dir), "config", "--get", "remote.origin.url"],
                capture_output=True,
                text=True,
                timeout=2,
            )
            if res.returncode == 0 and res.stdout.strip():
                local_key = RegistryManager.repository_key(res.stdout.strip())
                if local_key == req_key:
                    return True
        if os.path.isdir(repo_url):
            return True
    except Exception as exc:
        logger.debug("_is_local_workspace_match failed for %s: %s", repo_url, exc)
    return False


def _resolve_local_workspace_sha(ref: str) -> Optional[str]:
    """Resolve and verify one exact commit reference in the current workspace."""
    if not ref or ref.startswith("-") or "\x00" in ref:
        return None
    git_dir = _find_git_dir()
    if not git_dir:
        return None
    try:
        return Repo(git_dir).commit(ref).hexsha
    except Exception:
        return None


class GitAnalyzer:
    """
    Coordinates AST analysis and git diff retrieval.

    Strategy:
      0. If repo corresponds to the local workspace, use local git (< 50ms, zero network).
      1. If the repo is on GitHub and GITHUB_TOKEN is available (or works
         without it for public repos), use the GitHub API — no clone needed.
      2. Submitted staged/working snapshots use the same bounded parsing pipeline.
      3. Unavailable data is reported as partial or failed rather than silently safe.
    """

    def __init__(self):
        self._ast = ASTAnalyzer()
        self._gh = GitHubAPIClient()
        self.last_extraction: Dict[str, Any] = {}

    # ------------------------------------------------------------------ #
    #  Public entry point
    # ------------------------------------------------------------------ #

    async def resolve_commit_sha(
        self,
        repo_url: str,
        ref: str,
    ) -> Optional[str]:
        """
        Resolve a git reference (e.g. 'main', 'master', branch tag, commit hash,
        short SHA, or relative revision like 'HEAD~1') to a full 40-character commit SHA.
        """
        clean_ref = (ref or "").strip()
        if not clean_ref:
            return None

        # 1. Already a full 40-character hex commit SHA
        if re.match(r"^[0-9a-fA-F]{40}$", clean_ref):
            return clean_ref.lower()

        # 2. Local workspace git fast-path (< 10ms, immune to network/rate-limits)
        if _is_local_workspace_match(repo_url):
            local_sha = await asyncio.to_thread(_resolve_local_workspace_sha, clean_ref)
            if local_sha:
                logger.info("Resolved %s on %s -> %s via local git fast-path", clean_ref, repo_url, local_sha)
                return local_sha

        # 2b. Local directory handling
        if os.path.isdir(repo_url):
            try:
                def _resolve_local() -> Optional[str]:
                    try:
                        r = Repo(repo_url)
                        return r.commit(clean_ref).hexsha
                    except Exception as exc:
                        logger.debug("Repo.commit failed for %s: %s", clean_ref, exc)
                        return None
                local_sha = await asyncio.to_thread(_resolve_local)
                if local_sha:
                    return local_sha.lower()
            except Exception as exc:
                logger.debug("Local repo SHA resolution failed: %s", exc)

        gh_coords = _parse_github_url(repo_url)

        # 2c. Handle relative revisions like HEAD~1, main~2, or <sha>~1 for remote repos
        if ("~" in clean_ref or "^" in clean_ref) and gh_coords:
            owner, repo = gh_coords
            parts = re.split(r"([~^].*)", clean_ref, maxsplit=1)
            base_part = parts[0].strip() or "HEAD"
            rel_part = parts[1].strip() if len(parts) > 1 else ""

            base_sha = await self.resolve_commit_sha(repo_url, base_part)
            if base_sha and re.match(r"^[0-9a-fA-F]{40}$", base_sha):
                curr_sha = base_sha
                steps = 1
                if rel_part.startswith("~"):
                    try:
                        steps = int(rel_part[1:]) if len(rel_part) > 1 else 1
                    except ValueError:
                        steps = 1
                elif rel_part.startswith("^"):
                    steps = 1

                if steps < 0 or steps > 20 or not re.fullmatch(r"[~^]\d*", rel_part):
                    return None
                if rel_part.startswith("^") and rel_part not in {"^", "^1"}:
                    return None
                for _ in range(steps):
                    parent = await self._get_parent_sha(owner, repo, curr_sha)
                    if parent:
                        curr_sha = parent
                    else:
                        return None
                return curr_sha.lower()

        # 3. git ls-remote (fast, rate-limit free for branches and tags)
        # Skip ls-remote for commit SHAs or relative refs since ls-remote only lists refs
        is_sha_candidate = bool(re.match(r"^[0-9a-fA-F]{7,39}$", clean_ref))
        if not is_sha_candidate and "~" not in clean_ref and "^" not in clean_ref:
            try:
                def _run_ls_remote() -> Optional[str]:
                    # Try specific query refs first
                    for query_ref in [clean_ref, f"refs/heads/{clean_ref}", f"refs/tags/{clean_ref}"]:
                        try:
                            cmd = ["git", "ls-remote", repo_url, query_ref]
                            res = subprocess.run(cmd, capture_output=True, text=True, timeout=12)
                            if res.returncode == 0 and res.stdout:
                                for line in res.stdout.strip().splitlines():
                                    parts = line.strip().split()
                                    if len(parts) >= 2 and re.match(r"^[0-9a-fA-F]{40}$", parts[0]):
                                        return parts[0].lower()
                        except Exception as exc:
                            logger.debug("git ls-remote candidate %s failed: %s", query_ref, exc)
                            continue

                    # If specific ref query returned nothing, list all refs to match
                    try:
                        res = subprocess.run(["git", "ls-remote", repo_url], capture_output=True, text=True, timeout=15)
                        if res.returncode == 0 and res.stdout:
                            lines = res.stdout.strip().splitlines()
                            for line in lines:
                                parts = line.strip().split()
                                if len(parts) >= 2 and re.match(r"^[0-9a-fA-F]{40}$", parts[0]):
                                    ref_name = parts[1]
                                    if (
                                        ref_name == f"refs/heads/{clean_ref}"
                                        or ref_name == f"refs/tags/{clean_ref}"
                                        or ref_name == clean_ref
                                        or ref_name.endswith(f"/{clean_ref}")
                                    ):
                                        return parts[0].lower()
                    except Exception as exc:
                        logger.debug("git ls-remote fallback scan failed: %s", exc)
                    return None

                sha = await asyncio.to_thread(_run_ls_remote)
                if sha:
                    logger.info("Resolved %s on %s -> %s via git ls-remote", clean_ref, repo_url, sha)
                    return sha
            except Exception as exc:
                logger.warning("git ls-remote failed for %s: %s", repo_url, exc)

        # 4. GitHub REST API fallback (works for short SHAs, branches, and tags)
        if gh_coords:
            owner, repo = gh_coords
            try:
                async with httpx.AsyncClient(timeout=8.0) as client:
                    for branch_cand in [clean_ref]:
                        api_url = f"{_GH_API}/repos/{owner}/{repo}/commits/{branch_cand}"
                        resp = await client.get(api_url, headers=self._gh._headers)
                        if resp.status_code == 200:
                            data = resp.json()
                            if "sha" in data:
                                return data["sha"].lower()
            except Exception as exc:
                logger.warning("GitHub API commit SHA resolution failed: %s", exc)

            # 5. Fallback: Check commit patch header
            try:
                async with httpx.AsyncClient(timeout=8.0) as client:
                    for branch_cand in [clean_ref]:
                        patch_url = f"https://github.com/{owner}/{repo}/commit/{branch_cand}.patch"
                        resp = await client.get(patch_url, headers={"User-Agent": "MDT-GitAnalyzer"})
                        if resp.status_code == 200:
                            match = re.search(r"^From\s+([0-9a-fA-F]{40})", resp.text, re.MULTILINE)
                            if match:
                                return match.group(1).lower()
            except Exception as exc:
                logger.warning("GitHub patch SHA resolution fallback failed: %s", exc)

        return None

    def _build_change(self, file_path: str, change_type: str, old_content: str,
                      new_content: str, diff_text: str = "", *, previous_path=None,
                      base_sha="", commit_sha="", warnings=None, is_binary=False,
                      commit_timestamp=None) -> ChangeInfo:
        """Parse complete snapshots only; a patch is never treated as source code."""
        file_path = _safe_source_path(file_path)
        warnings = list(warnings or [])
        for name, content in (("old", old_content), ("new", new_content)):
            if len(content.encode("utf-8")) > MAX_SOURCE_BYTES:
                warnings.append(f"{name}_source_exceeds_limit")
                if name == "old":
                    old_content = ""
                else:
                    new_content = ""
        is_binary = is_binary or "\x00" in old_content or "\x00" in new_content
        if is_binary:
            old_content = new_content = ""
            warnings.append("binary_source_not_parsed")
        if not diff_text and not is_binary:
            diff_text = _make_simple_diff(file_path, old_content, new_content)
        if len(diff_text.encode("utf-8")) > MAX_SOURCE_BYTES:
            diff_text = diff_text.encode("utf-8")[:MAX_SOURCE_BYTES].decode("utf-8", "ignore")
            warnings.append("diff_truncated")
        additions, deletions = _count_diff_lines(diff_text)
        language = _EXT_TO_LANG.get(Path(file_path).suffix.lower(), "unknown")
        parser_coverage = "ast" if language == "python" else "heuristic"
        if not is_supported_file(file_path):
            parser_coverage = "unsupported"
            warnings.append("unsupported_file_type")
        old_meta = self._ast.analyze(old_content, language)
        new_meta = self._ast.analyze(new_content, language)
        if language in {"javascript", "typescript"}:
            parser_coverage = "tree_sitter"
            for name, metadata in (("old", old_meta), ("new", new_meta)):
                warnings.extend(f"{name}_{warning}" for warning in metadata.get("parser_warnings", []))
                if metadata.get("parser_coverage") in {"failed", "partial"}:
                    parser_coverage = metadata["parser_coverage"]
        if language == "python":
            for name, source in (("old", old_content), ("new", new_content)):
                if source:
                    try:
                        ast.parse(source)
                    except (SyntaxError, ValueError, RecursionError):
                        warnings.append(f"{name}_source_parse_failed")
                        parser_coverage = "failed"
        old_routes = old_meta.get("routes") if "routes" in old_meta else extract_route_signatures(old_content, language)
        new_routes = new_meta.get("routes") if "routes" in new_meta else extract_route_signatures(new_content, language)
        old_meta["routes"] = old_routes
        new_meta["routes"] = new_routes
        metadata = dict(old_meta if change_type in {"removed", "deleted"} else new_meta)
        metadata["contract_changes"] = compare_route_contracts(old_routes, new_routes, language)
        metadata.update(semantic_comparison(old_content, new_content, language,
            complete=not is_binary and not any(any(marker in warning for marker in
                ("source_", "binary", "syntax_node_limit", "unsupported_file_type")) for warning in warnings),
            structural_change=change_type in {"added", "deleted", "removed", "renamed", "copied"} or bool(previous_path)))
        if language == "python":
            old_models = PythonModelContext({file_path: old_content}).schemas(file_path)
            new_models = PythonModelContext({file_path: new_content}).schemas(file_path)
            metadata["schema_changes"] = compare_schema_models(old_models, new_models)
        if language in {"python", "javascript", "typescript", "json", "yaml", "toml"} and metadata["semantic_change"] is None:
            warnings.append("semantic_analysis_unavailable")
            for key in ("contract_changes", "schema_changes"):
                if key in metadata:
                    metadata[key] = {"added": [], "removed": [], "modified": [], "breaking_changes": [],
                        "additive_changes": [], "uncertain_changes": [{"reason": "source_unavailable_or_invalid"}],
                        "compatibility": "uncertain", "coverage": "unavailable"}
        metadata.update({"old": old_meta, "new": new_meta, "parser_coverage": parser_coverage,
                         "extraction_status": "partial" if warnings else "complete",
                         "extraction_warnings": list(dict.fromkeys(warnings))})
        return ChangeInfo(file_path, change_type, diff_text, additions, deletions,
                          old_content, new_content, metadata, previous_path, base_sha,
                          commit_sha, "partial" if warnings else "complete",
                          list(dict.fromkeys(warnings)), is_binary, parser_coverage,
                          commit_timestamp)

    def _summarize(self, changes, *, base_sha="", commit_sha="", warnings=None, source_context=None):
        self._resolve_snapshot_contracts(changes, source_context)
        warnings = list(warnings or [])
        warnings.extend(w for c in changes for w in c.extraction_warnings)
        self.last_extraction = {"status": "partial" if warnings else "complete",
                                "base_sha": base_sha, "head_sha": commit_sha,
                                "files_analyzed": len(changes),
                                "warnings": list(dict.fromkeys(warnings))}
        return changes

    def _resolve_snapshot_contracts(self, changes, source_context=None):
        """Use only supplied immutable snapshots, never assume unseen imports match."""
        before, after = {}, {}
        if source_context:
            if not isinstance(source_context, dict) or set(source_context) - {"before", "after"}:
                raise ValueError("Source context must contain before and after snapshots.")
            for side, target in (("before", before), ("after", after)):
                values = source_context.get(side, {})
                if not isinstance(values, dict):
                    raise ValueError("Source context snapshots must be path-to-text mappings.")
                for path, content in values.items():
                    path = _safe_source_path(path)
                    if not isinstance(content, str) or len(content.encode()) > MAX_SOURCE_BYTES:
                        raise ValueError("Source context files must be text within the parser limit.")
                    target[path] = content
        for change in changes:
            # The explicit change snapshots are authoritative over optional context.
            before[change.previous_path or change.file_path] = change.old_content
            after[change.file_path] = change.new_content
        if max(len(before), len(after)) > MAX_CHANGE_FILES or sum(len(s.encode()) for s in list(before.values()) + list(after.values())) > MAX_TOTAL_SOURCE_BYTES:
            raise ValueError("Combined change and context snapshots exceed the 100-file / 2 MiB analysis limit.")
        # Never resolve another file against one side of an unavailable model.
        # Missing snapshots are unknown evidence, not deleted definitions.
        for change in changes:
            if change.ast_metadata.get("semantic_change") is None:
                before.pop(change.previous_path or change.file_path, None)
                after.pop(change.file_path, None)
        old_ctx, new_ctx = PythonModelContext(before), PythonModelContext(after)
        changed_paths = {change.file_path for change in changes}
        affected = []
        for path in sorted(old_ctx.trees.keys() | new_ctx.trees.keys()):
            if path in changed_paths:
                continue
            old_routes = extract_python_routes(before.get(path, ""), file_path=path, context=old_ctx)
            new_routes = extract_python_routes(after.get(path, ""), file_path=path, context=new_ctx)
            delta = compare_route_contracts(old_routes, new_routes, "python")
            if delta["modified"]:
                affected.append({"file_path": path, **delta})
        for change in changes:
            if change.language != "python":
                continue
            if change.ast_metadata.get("semantic_change") is None:
                continue
            old_path = change.previous_path or change.file_path
            old_routes = extract_python_routes(change.old_content, file_path=old_path, context=old_ctx)
            new_routes = extract_python_routes(change.new_content, file_path=change.file_path, context=new_ctx)
            meta = change.ast_metadata
            meta["old"]["routes"], meta["new"]["routes"] = old_routes, new_routes
            meta["routes"] = old_routes if change.change_type == "deleted" else new_routes
            meta["contract_changes"] = compare_route_contracts(old_routes, new_routes, "python")
            if any(meta["contract_changes"][kind] for kind in ("added", "removed", "modified")) and meta.get("semantic_change") is False:
                meta.update(semantic_change=True, semantic_status="changed", semantic_evidence="resolved_contract_change")
            schemas = compare_schema_models(old_ctx.schemas(old_path), new_ctx.schemas(change.file_path))
            if any(schemas[k] for k in ("added", "removed", "modified")):
                schemas["affected_routes"] = [entry for entry in affected if any(
                    model.get("source_path") in {old_path, change.file_path} or any(field.get("source_path") in {old_path, change.file_path} for field in model.get("fields", []))
                    for route in entry["modified"] for state in ("before", "after")
                    for model in list(route[state].get("request_schema", {}).values()) + list(route[state].get("response_schema", {}).get("models", {}).values()))]
            meta["schema_changes"] = schemas
            meta["contract_context"] = {"coverage": "supplied_snapshots_only", "files": len(old_ctx.trees.keys() | new_ctx.trees.keys()),
                "unresolved_models": meta["contract_changes"]["unresolved_models"]}

    def analyze_local_changes(self, local_changes, *, base_sha, commit_sha, source_context=None):
        if not base_sha:
            raise ValueError("Submitted source snapshots require an explicit base_sha.")
        if len(local_changes) > MAX_CHANGE_FILES:
            raise ValueError(f"At most {MAX_CHANGE_FILES} changed files may be submitted.")
        changes, total = [], 0
        for item in local_changes:
            if hasattr(item, "model_dump"):
                item = item.model_dump()
            file_path = _safe_source_path(item.get("file_path") or item.get("path", ""))
            previous_path = item.get("previous_path")
            if previous_path:
                previous_path = _safe_source_path(previous_path)
            if "old_content" not in item or "new_content" not in item:
                raise ValueError("Each submitted change requires old_content and new_content snapshots.")
            old, new = item["old_content"], item["new_content"]
            if not isinstance(old, str) or not isinstance(new, str):
                raise ValueError("Source snapshots must be text.")
            total += len(old.encode("utf-8")) + len(new.encode("utf-8"))
            if total > MAX_TOTAL_SOURCE_BYTES:
                raise ValueError("Submitted source snapshots exceed the 2 MiB analysis limit.")
            changes.append(self._build_change(file_path, item.get("change_type", "modified"),
                                             old, new, previous_path=previous_path,
                                             base_sha=base_sha, commit_sha=commit_sha,
                                             warnings=item.get("extraction_warnings", []),
                                             is_binary=bool(item.get("is_binary", False))))
        self._summarize(changes, base_sha=base_sha, commit_sha=commit_sha, source_context=source_context)
        digest_input = [{"path": change.file_path, "previous_path": change.previous_path,
                         "old": change.old_content, "new": change.new_content} for change in changes]
        digest_input = {"changes": digest_input, "context": source_context or {}}
        self.last_extraction.update(source="client_supplied_snapshots",
            snapshot_digest=hashlib.sha256(json.dumps(digest_input, sort_keys=True).encode()).hexdigest())
        return changes

    async def analyze_push(self, repo_url: str, commit_sha: str,
                           changed_files: Optional[List[str]] = None, *, base_sha=None,
                           comparison_mode="direct", local_changes=None, source_context=None) -> List[ChangeInfo]:
        if comparison_mode not in {"direct", "merge_base"}:
            raise ValueError("comparison_mode must be direct or merge_base.")
        if local_changes is not None:
            return self.analyze_local_changes(local_changes, base_sha=base_sha, commit_sha=commit_sha, source_context=source_context)
        if os.path.isdir(repo_url):
            return await asyncio.to_thread(self._analyze_git_snapshots, Repo(repo_url),
                                           commit_sha, changed_files, base_sha, comparison_mode)
        if _is_local_workspace_match(repo_url):
            return await asyncio.to_thread(self._analyze_from_local_workspace, commit_sha,
                                           changed_files, base_sha, comparison_mode)
        coords = _parse_github_url(repo_url)
        if not coords:
            raise ValueError("Only a local repository or a supported GitHub repository can be analyzed.")
        from services.github_app import GitHubAppAuth
        token = await GitHubAppAuth.get_installation_token_for_repo(repo_url)
        if token:
            self._gh._token = token
            self._gh._headers["Authorization"] = f"Bearer {token}"
        try:
            return await self._analyze_via_github_api(*coords, commit_sha, changed_files,
                base_sha=base_sha, comparison_mode=comparison_mode)
        except GitHubRateLimitError:
            if self._gh._headers.get("Authorization"):
                raise
            return await self._analyze_public_archives(*coords, commit_sha, changed_files,
                base_sha=base_sha, comparison_mode=comparison_mode)

    async def _analyze_public_archives(self, owner, repo, head_ref, files=None, *, base_sha=None, comparison_mode="direct"):
        from services.public_github_source import public_commit_metadata
        if comparison_mode != "direct":
            raise ValueError("Anonymous archive analysis requires a direct comparison; merge-base analysis needs GitHub API access")
        url = f"https://github.com/{owner}/{repo}"
        head = await self.resolve_commit_sha(url, head_ref)
        if not head:
            raise ValueError("Head revision could not be resolved")
        metadata = await asyncio.to_thread(public_commit_metadata, owner, repo, head)
        base = (await self.resolve_commit_sha(url, base_sha)) if base_sha else next(iter(metadata["parents"]), EMPTY_TREE)
        if not base:
            raise ValueError("Base revision could not be resolved")
        new = await self._gh._public_archive(owner, repo, head)
        old = None if base in {EMPTY_TREE, "0" * 40} else await self._gh._public_archive(owner, repo, base)
        old_files = old.files if old else {}
        requested = {_safe_source_path(path) for path in files} if files else None
        paths = sorted(set(old_files) | set(new.files))
        changes, warnings, total = [], ["public_archive_comparison_rename_detection_unavailable"], 0
        for path in paths:
            if requested is not None and path not in requested:
                continue
            # Oversized files retain tree membership but cannot prove equality.
            if path in old_files and path in new.files and old.digests[path] is not None and old.digests[path] == new.digests[path]:
                continue
            if len(changes) >= MAX_CHANGE_FILES:
                warnings.append("file_count_limit_reached")
                break
            kind = "added" if path not in old_files else "deleted" if path not in new.files else "modified"
            contents, file_warnings = {}, []
            for side, archive, needed in (("old", old, kind != "added"), ("new", new, kind != "deleted")):
                try:
                    source = archive.read(path) if archive and needed else ""
                    size = len(source.encode())
                    if total + size > MAX_TOTAL_SOURCE_BYTES:
                        raise ValueError("total source limit")
                    total += size
                    contents[side] = source
                except ValueError:
                    contents[side] = ""
                    file_warnings.append(side + "_source_unavailable_or_limit")
            changes.append(self._build_change(path, kind, contents["old"], contents["new"], base_sha=base,
                commit_sha=head, warnings=file_warnings, commit_timestamp=metadata["timestamp"]))
        result = self._summarize(changes, base_sha=base, commit_sha=head, warnings=warnings)
        self.last_extraction.update(source="public_github_archives", transport_evidence={
            "head": new.evidence, "base": old.evidence if old else {"revision": EMPTY_TREE}, "executed_source": False})
        return result


    def _analyze_from_local_workspace(self, target_ref, files=None, base_sha=None,
                                      comparison_mode="direct"):
        git_dir = _find_git_dir()
        if not git_dir:
            raise ValueError("Local repository objects are unavailable.")
        return self._analyze_git_snapshots(Repo(git_dir), target_ref, files, base_sha, comparison_mode)

    def _analyze_git_snapshots(self, repo, target_ref, files=None, base_sha=None,
                              comparison_mode="direct"):
        try:
            head = repo.commit(target_ref)
            base = (EMPTY_TREE if base_sha == EMPTY_TREE or base_sha == "0" * 40 else
                    repo.commit(base_sha).hexsha if base_sha else
                    head.parents[0].hexsha if head.parents else EMPTY_TREE)
            if comparison_mode == "merge_base" and base != EMPTY_TREE:
                bases = repo.merge_base(base, head)
                if not bases:
                    raise ValueError("The supplied base and head do not share a merge base.")
                base = bases[0].hexsha
        except Exception as exc:
            raise ValueError("The requested base or head revision is unavailable.") from exc
        records = repo.git.diff("--name-status", "-z", "--find-renames", base, head.hexsha).split("\x00")
        requested = {_safe_source_path(f) for f in files} if files else None
        changes, warnings, total, i = [], [], 0, 0
        while i < len(records) and records[i]:
            status = records[i]; path = records[i + 1]; i += 2
            previous = None
            if status[0] in {"R", "C"}:
                previous, path = path, records[i]; i += 1
            if requested is not None and path not in requested and previous not in requested:
                continue
            if len(changes) >= MAX_CHANGE_FILES:
                warnings.append("file_count_limit_reached")
                break
            kind = {"A": "added", "D": "deleted", "R": "renamed", "C": "copied"}.get(status[0], "modified")
            file_warnings = []
            def read_blob(ref, source_path, absent=False):
                nonlocal total
                if absent:
                    return ""
                try:
                    blob = repo.commit(ref).tree[source_path]
                    if blob.size > MAX_SOURCE_BYTES or total + blob.size > MAX_TOTAL_SOURCE_BYTES:
                        file_warnings.append("source_size_limit_reached")
                        return ""
                    total += blob.size
                    return blob.data_stream.read(MAX_SOURCE_BYTES + 1).decode("utf-8")
                except UnicodeDecodeError:
                    file_warnings.append("binary_or_non_utf8_source")
                    return ""
                except (KeyError, ValueError):
                    file_warnings.append("source_unavailable")
                    return ""
            old = read_blob(base, previous or path, kind == "added" or base == EMPTY_TREE)
            new = read_blob(head.hexsha, path, kind == "deleted")
            # Compute a bounded patch from the two verified source snapshots.
            changes.append(self._build_change(path, kind, old, new, previous_path=previous,
                          base_sha=base, commit_sha=head.hexsha, warnings=file_warnings,
                          commit_timestamp=head.committed_date))
        return self._summarize(changes, base_sha=base, commit_sha=head.hexsha, warnings=warnings)

    async def _analyze_via_github_api(self, owner, repo, commit_sha, files=None, *,
                                     base_sha=None, comparison_mode="direct"):
        """Read bounded GitHub commit/compare metadata; never silently clone an unbounded repo."""
        requested = {_safe_source_path(f) for f in files} if files else None
        async with httpx.AsyncClient(timeout=15.0) as client:
            async def get_json(url, params=None):
                response = await self._gh._request_with_retry(client, url, params=params, max_retries=1)
                if response.status_code != 200:
                    raise ValueError(f"GitHub could not read the requested revision (HTTP {response.status_code}).")
                if len(response.content) > 8 * 1024 * 1024:
                    raise ValueError("GitHub comparison metadata exceeds the analysis limit.")
                return response.json()
            head_data = await get_json(f"{_GH_API}/repos/{owner}/{repo}/commits/{commit_sha}", {"per_page": 100})
            head = head_data["sha"]
            parents = head_data.get("parents", [])
            base = base_sha or (parents[0]["sha"] if parents else "")
            metadata = head_data
            warnings = []
            if base_sha:
                if base_sha in {EMPTY_TREE, "0" * 40}:
                    raise ValueError("Remote root-tree comparisons require submitted bounded snapshots.")
                metadata = await get_json(f"{_GH_API}/repos/{owner}/{repo}/compare/{base_sha}...{head}", {"per_page": 1})
                base = metadata.get("base_commit", {}).get("sha", base_sha)
                merge_base = metadata.get("merge_base_commit", {}).get("sha", base)
                if comparison_mode == "merge_base":
                    base = merge_base
                elif merge_base != base:
                    raise ValueError("GitHub compare uses merge-base semantics for divergent refs; submit snapshots for a direct divergent comparison.")
                # GitHub returns at most 300 changed files on the first comparison page.
                if len(metadata.get("files", [])) >= 300:
                    warnings.append("github_compare_file_limit_reached")
            all_files = metadata.get("files", [])
            if not base_sha and len(all_files) >= 100:
                warnings.append("github_commit_file_page_limit_reached")
            selected = [f for f in all_files if requested is None or f.get("filename") in requested or f.get("previous_filename") in requested]
            if requested and not requested.issubset({f.get("filename") for f in all_files} | {f.get("previous_filename") for f in all_files}):
                warnings.append("requested_files_not_in_available_diff")
            if len(selected) > MAX_CHANGE_FILES:
                warnings.append("file_count_limit_reached")
            changes, total = [], 0
            timestamp = None
            try:
                from datetime import datetime
                timestamp = int(datetime.fromisoformat(head_data["commit"]["committer"]["date"].replace("Z", "+00:00")).timestamp())
            except (KeyError, TypeError, ValueError):
                warnings.append("commit_timestamp_unavailable")
            for entry in selected[:MAX_CHANGE_FILES]:
                path = entry["filename"]
                kind = entry.get("status", "modified")
                file_warnings = []
                old = new = ""
                for side, ref, source_path, needed in (
                    ("old", base, entry.get("previous_filename", path), kind != "added" and bool(base)),
                    ("new", head, path, kind not in {"removed", "deleted"})):
                    if not needed:
                        continue
                    if total >= MAX_TOTAL_SOURCE_BYTES:
                        file_warnings.append("total_source_limit_reached")
                        continue
                    try:
                        source = await self._gh.get_file_content(owner, repo, source_path, ref)
                        if len(source.encode("utf-8")) > MAX_SOURCE_BYTES or total + len(source.encode("utf-8")) > MAX_TOTAL_SOURCE_BYTES:
                            source = ""
                            file_warnings.append("source_size_limit_reached")
                        total += len(source.encode("utf-8"))
                        if side == "old": old = source
                        else: new = source
                    except GitHubRateLimitError as exc:
                        file_warnings.append(f"{side}_{exc.evidence}")
                    except Exception:
                        file_warnings.append(f"{side}_source_unavailable")
                if "patch" not in entry and entry.get("changes", 0):
                    file_warnings.append("github_patch_unavailable_or_binary")
                change = self._build_change(path, kind, old, new, previous_path=entry.get("previous_filename"),
                    base_sha=base, commit_sha=head, warnings=file_warnings, commit_timestamp=timestamp)
                # GitHub's counts remain valid even when source retrieval is partial.
                change.additions = entry.get("additions", change.additions)
                change.deletions = entry.get("deletions", change.deletions)
                changes.append(change)
        return self._summarize(changes, base_sha=base, commit_sha=head, warnings=warnings)

    async def _build_change_info_from_api(self, owner, repo, file_path, commit_sha, parent_sha, diff_text):
        kind = "added" if "new file mode" in diff_text else "deleted" if "deleted file mode" in diff_text else "modified"
        old = await self._gh.get_file_content(owner, repo, file_path, parent_sha) if parent_sha and kind != "added" else ""
        new = await self._gh.get_file_content(owner, repo, file_path, commit_sha) if kind != "deleted" else ""
        return self._build_change(file_path, kind, old, new, diff_text, base_sha=parent_sha or "", commit_sha=commit_sha)

    async def _get_parent_sha(
        self, owner: str, repo: str, commit_sha: str
    ) -> Optional[str]:
        """Return the first parent SHA of a commit, or None."""
        url = f"{_GH_API}/repos/{owner}/{repo}/commits/{commit_sha}"
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.get(url, headers=self._gh._headers)
                if resp.status_code == 200:
                    parents = resp.json().get("parents", [])
                    if parents:
                        return parents[0]["sha"]
        except Exception as exc:
            logger.debug("get_parent_sha failed: %s", exc)
        return None

    async def get_file_diff(
        self, repo_path: str, commit_sha: str, file_path: str
    ) -> str:
        """Get the unified diff for a file from a local repo."""
        try:
            repo = Repo(repo_path)
            diff = repo.git.diff(f"{commit_sha}^", commit_sha, "--", file_path)
            return diff
        except (InvalidGitRepositoryError, GitCommandError) as exc:
            logger.error("get_file_diff failed for %s: %s", file_path, exc)
            return ""

    async def extract_ast_metadata(
        self, file_path: str, content: str
    ) -> Dict[str, Any]:
        """Public wrapper around ASTAnalyzer for external callers."""
        lang = _EXT_TO_LANG.get(Path(file_path).suffix.lower(), "unknown")
        return self._ast.analyze(content, lang)


# ---------------------------------------------------------------------------
# Simple diff generator (when we have content but no diff text)
# ---------------------------------------------------------------------------

def _make_simple_diff(
    file_path: str, old_content: str, new_content: str
) -> str:
    """
    Generate a minimal unified diff from two content strings.
    Used as a fallback when the API doesn't return a diff.
    """
    import difflib
    old_lines = old_content.splitlines(keepends=True)
    new_lines = new_content.splitlines(keepends=True)
    diff = difflib.unified_diff(
        old_lines, new_lines,
        fromfile=f"a/{file_path}",
        tofile=f"b/{file_path}",
        lineterm="",
    )
    return "".join(diff)
