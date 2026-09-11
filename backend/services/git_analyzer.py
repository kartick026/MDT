"""
Git Analysis Service — Phase 4 (Week 5)
========================================
Handles real git diff parsing, file content retrieval, line counting,
and AST metadata extraction for the MDT analysis pipeline.

Two strategies for fetching diffs:
  1. GitHub REST API  — used when the repo is a GitHub URL and
     GITHUB_TOKEN is set. No local clone needed.
  2. Local gitpython  — used when a local repo path is provided or
     as a fallback after a clone.

AST extraction:
  - Python  : stdlib `ast` module (no extra deps)
  - JS / TS : regex heuristics (tree-sitter integration is a TODO)
  - Others  : regex heuristics for functions / classes
"""
import ast
import asyncio
import logging
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Any

import httpx
from git import Repo, InvalidGitRepositoryError, GitCommandError

from core.config import settings

logger = logging.getLogger(__name__)


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

    def __post_init__(self):
        # Normalise GitHub's "removed" → project-standard "deleted"
        if self.change_type == "removed":
            self.change_type = "deleted"
        if self.change_type not in {"added", "modified", "deleted"}:
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
}

SUPPORTED_EXTENSIONS = set(_EXT_TO_LANG.keys())

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
    pattern = r"github\.com[:/]([^/]+)/([^/\.]+)"
    match = re.search(pattern, repo_url)
    if match:
        return match.group(1), match.group(2).removesuffix(".git")
    return None


# ---------------------------------------------------------------------------
# GitHub API client
# ---------------------------------------------------------------------------

class GitHubAPIClient:
    """
    Thin async wrapper around the GitHub REST API.
    Used to fetch file contents and commit diffs without cloning.
    """
    _is_globally_rate_limited = False

    def __init__(self, token: Optional[str] = None):
        self._token = token or settings.GITHUB_TOKEN or os.getenv("GITHUB_TOKEN", "")
        headers = {"Accept": "application/vnd.github+json",
                   "X-GitHub-Api-Version": "2022-11-28"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        self._headers = headers

    async def _request_with_retry(
        self,
        client: httpx.AsyncClient,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, Any]] = None,
        max_retries: int = 3,
    ) -> httpx.Response:
        """Make an HTTP GET request with exponential backoff for transient failures."""
        req_headers = headers if headers is not None else self._headers
        last_exc = None
        resp: Optional[httpx.Response] = None
        for attempt in range(max_retries):
            try:
                resp = await client.get(url, headers=req_headers, params=params)
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

    async def get_repo_tree(
        self,
        owner: str,
        repo: str,
        tree_sha: str = "main",
    ) -> List[str]:
        """Fetch the full recursive git tree paths for a repository branch or commit."""
        # 1. Try GitHub REST API if not globally rate-limited or if token present
        if self._token or not GitHubAPIClient._is_globally_rate_limited:
            for branch_candidate in ([tree_sha, "master"] if tree_sha == "main" else [tree_sha]):
                try:
                    async with httpx.AsyncClient(timeout=10.0) as client:
                        url = f"{_GH_API}/repos/{owner}/{repo}/git/trees/{branch_candidate}?recursive=1"
                        resp = await self._request_with_retry(client, url)
                        if resp.status_code == 200:
                            data = resp.json()
                            return [item["path"] for item in data.get("tree", []) if "path" in item]
                        if resp.status_code in (403, 429):
                            GitHubAPIClient._is_globally_rate_limited = True
                            logger.warning("GitHub git tree API rate limited for %s/%s, falling back to shallow clone", owner, repo)
                            break
                        logger.warning("GitHub git tree API %s/%s (ref=%s) → %d", owner, repo, branch_candidate, resp.status_code)
                except Exception as exc:
                    logger.warning("get_repo_tree REST failed for %s/%s: %s", owner, repo, exc)
                    break

        # 2. Resilient fallback: shallow clone without hitting REST API rate limits
        try:
            logger.info("Executing shallow clone fallback for %s/%s", owner, repo)
            loop = asyncio.get_running_loop()

            def _clone_and_list() -> List[str]:
                with tempfile.TemporaryDirectory() as td:
                    clone_url = f"https://github.com/{owner}/{repo}.git"
                    try:
                        r = Repo.clone_from(clone_url, td, depth=1, branch=tree_sha)
                    except Exception as e:
                        logger.warning("Shallow clone branch %s failed for %s/%s: %s", tree_sha, owner, repo, e)
                        return []
                    return r.git.ls_files().splitlines()

            file_list = await loop.run_in_executor(None, _clone_and_list)
            if file_list:
                return file_list
        except Exception as exc:
            logger.warning("Shallow clone fallback error for %s/%s: %s", owner, repo, exc)

        return []

    async def get_file_content(
        self,
        owner: str,
        repo: str,
        path: str,
        ref: str,
    ) -> str:
        """Return raw file content at a specific commit/ref. Empty string on error."""
        clean_path = path.lstrip("/")
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                # Fast path: If unauthenticated and already rate-limited, directly use raw.githubusercontent.com
                if not self._token and GitHubAPIClient._is_globally_rate_limited:
                    for branch_cand in ([ref, "master"] if ref == "main" else [ref]):
                        raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch_cand}/{clean_path}"
                        fallback_resp = await client.get(raw_url, timeout=2.5)
                        if fallback_resp.status_code == 200:
                            return fallback_resp.text
                    return ""

                url = f"{_GH_API}/repos/{owner}/{repo}/contents/{clean_path}"
                resp = await self._request_with_retry(client, url, params={"ref": ref}, max_retries=1)
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("encoding") == "base64":
                        import base64
                        return base64.b64decode(data["content"]).decode("utf-8", errors="replace")
                elif resp.status_code == 404:
                    return ""   # file didn't exist at this ref
                elif resp.status_code in (403, 429):
                    GitHubAPIClient._is_globally_rate_limited = True
                    for branch_cand in ([ref, "master"] if ref == "main" else [ref]):
                        raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch_cand}/{clean_path}"
                        fallback_resp = await client.get(raw_url, timeout=2.5)
                        if fallback_resp.status_code == 200:
                            return fallback_resp.text
                    return ""
        except Exception as exc:
            logger.debug("get_file_content failed for %s: %s", clean_path, exc)
            try:
                async with httpx.AsyncClient(timeout=2.5) as client:
                    for branch_cand in ([ref, "master"] if ref == "main" else [ref]):
                        raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch_cand}/{clean_path}"
                        r = await client.get(raw_url)
                        if r.status_code == 200:
                            return r.text
            except Exception:
                pass
        return ""

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
                if not self._token and GitHubAPIClient._is_globally_rate_limited:
                    patch_url = f"https://github.com/{owner}/{repo}/commit/{commit_sha}.patch"
                    fallback_resp = await client.get(patch_url)
                    if fallback_resp.status_code == 200:
                        return _split_diff_by_file(fallback_resp.text)
                    return None

                url = f"{_GH_API}/repos/{owner}/{repo}/commits/{commit_sha}"
                resp = await self._request_with_retry(
                    client,
                    url,
                    headers={**self._headers, "Accept": "application/vnd.github.diff"}
                )
                if resp.status_code == 200:
                    return _split_diff_by_file(resp.text)
                elif resp.status_code in (403, 429):
                    GitHubAPIClient._is_globally_rate_limited = True
                    # Rate limit exceeded, fallback to github.com commit patch
                    patch_url = f"https://github.com/{owner}/{repo}/commit/{commit_sha}.patch"
                    logger.warning("GitHub API rate limited, falling back to %s", patch_url)
                    fallback_resp = await client.get(patch_url)
                    if fallback_resp.status_code == 200:
                        return _split_diff_by_file(fallback_resp.text)
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
    - JS/TS/others: regex heuristics.
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
        functions: List[str] = []
        classes: List[str] = []
        imports: List[str] = []
        exports: List[str] = []

        # named functions
        functions += re.findall(r'\bfunction\s+(\w+)\s*\(', content)
        # arrow / const functions
        functions += re.findall(
            r'\bconst\s+(\w+)\s*=\s*(?:async\s*)?\([^)]*\)\s*=>', content)
        # class declarations
        classes += re.findall(r'\bclass\s+(\w+)', content)
        # import statements
        imports += re.findall(r"import\s+.*?from\s+['\"]([^'\"]+)['\"]", content)
        # require()
        imports += re.findall(r"require\s*\(\s*['\"]([^'\"]+)['\"]\s*\)", content)
        # exports
        exports += re.findall(r'\bexport\s+(?:default\s+)?(?:function|class|const)\s+(\w+)', content)

        return {
            "language": language,
            "functions": list(dict.fromkeys(functions)),
            "classes": list(dict.fromkeys(classes)),
            "imports": list(dict.fromkeys(imports)),
            "exports": list(dict.fromkeys(exports)),
        }

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
# GitAnalyzer — main service class
# ---------------------------------------------------------------------------

class GitAnalyzer:
    """
    Analyses a push event and produces a list of fully-populated ChangeInfo
    objects, each with diff content, line counts, and AST metadata.

    Strategy:
      1. If repo_url points to GitHub and GITHUB_TOKEN is set (or even
         without it for public repos), use the GitHub API — no clone needed.
      2. Otherwise attempt a shallow clone into a temp dir and use gitpython.
      3. On any failure, return minimal ChangeInfo with what we know from the
         webhook payload (file path + change_type) so the pipeline still runs.
    """

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
        except Exception:
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
        if req_key in ("kartick026/mdt", "kartick026/mdt.git"):
            return True
        if os.path.isdir(repo_url):
            return True
    except Exception:
        pass
    return False


def _resolve_local_workspace_sha(ref: str) -> Optional[str]:
    """Resolve a branch or ref in the local git repository in < 10ms."""
    try:
        clean_ref = (ref or "").strip()
        if not clean_ref:
            return None
        if re.match(r"^[0-9a-fA-F]{40}$", clean_ref):
            return clean_ref.lower()

        git_dir = _find_git_dir()
        if not git_dir or not git_dir.exists():
            return None

        # 1. Direct filesystem read from .git/refs/
        candidate_paths = [
            git_dir / "refs" / "heads" / clean_ref,
            git_dir / "refs" / "remotes" / "origin" / clean_ref,
            git_dir / "refs" / "tags" / clean_ref,
        ]
        if clean_ref.startswith("refs/"):
            candidate_paths.insert(0, git_dir / clean_ref)

        for p in candidate_paths:
            if p.is_file():
                content = p.read_text(encoding="utf-8", errors="ignore").strip()
                if re.match(r"^[0-9a-fA-F]{40}$", content):
                    return content.lower()

        # 2. Packed-refs file
        packed_refs_file = git_dir / "packed-refs"
        if packed_refs_file.is_file():
            content = packed_refs_file.read_text(encoding="utf-8", errors="ignore")
            for line in content.splitlines():
                parts = line.strip().split()
                if len(parts) >= 2 and re.match(r"^[0-9a-fA-F]{40}$", parts[0]):
                    ref_name = parts[1]
                    if (
                        ref_name == f"refs/heads/{clean_ref}"
                        or ref_name == f"refs/remotes/origin/{clean_ref}"
                        or ref_name == f"refs/tags/{clean_ref}"
                        or ref_name == clean_ref
                    ):
                        return parts[0].lower()

        # 3. HEAD file if clean_ref is HEAD
        if clean_ref.upper() == "HEAD":
            head_file = git_dir / "HEAD"
            if head_file.is_file():
                head_content = head_file.read_text(encoding="utf-8", errors="ignore").strip()
                if head_content.startswith("ref:"):
                    target_ref = head_content.split(":", 1)[1].strip()
                    target_p = git_dir / target_ref
                    if target_p.is_file():
                        content = target_p.read_text(encoding="utf-8", errors="ignore").strip()
                        if re.match(r"^[0-9a-fA-F]{40}$", content):
                            return content.lower()
                elif re.match(r"^[0-9a-fA-F]{40}$", head_content):
                    return head_content.lower()

        # 4. Fallback: git rev-parse with --git-dir (bypasses working dir access issues)
        for candidate in [clean_ref, f"origin/{clean_ref}", f"refs/heads/{clean_ref}"]:
            res = subprocess.run(
                ["git", "--git-dir", str(git_dir), "rev-parse", f"{candidate}^{{commit}}"],
                capture_output=True,
                text=True,
                timeout=2,
            )
            if res.returncode == 0 and res.stdout.strip():
                sha = res.stdout.strip().splitlines()[0].strip()
                if re.match(r"^[0-9a-fA-F]{40}$", sha):
                    return sha.lower()
    except Exception:
        pass
    return None


class GitAnalyzer:
    """
    Coordinates AST analysis and git diff retrieval.

    Strategy:
      0. If repo corresponds to the local workspace, use local git (< 50ms, zero network).
      1. If the repo is on GitHub and GITHUB_TOKEN is available (or works
         without it for public repos), use the GitHub API — no clone needed.
      2. Otherwise attempt a shallow clone into a temp dir and use gitpython.
      3. On any failure, return minimal ChangeInfo with what we know from the
         webhook payload (file path + change_type) so the pipeline still runs.
    """

    def __init__(self):
        self._ast = ASTAnalyzer()
        self._gh = GitHubAPIClient()

    # ------------------------------------------------------------------ #
    #  Public entry point
    # ------------------------------------------------------------------ #

    async def resolve_commit_sha(
        self,
        repo_url: str,
        ref: str,
    ) -> Optional[str]:
        """
        Resolve a git reference (e.g. 'main', 'master', branch tag, or commit hash)
        to a full 40-character commit SHA.
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
                    except Exception:
                        return None
                local_sha = await asyncio.to_thread(_resolve_local)
                if local_sha:
                    return local_sha.lower()
            except Exception as exc:
                logger.debug("Local repo SHA resolution failed: %s", exc)

        # 3. git ls-remote (fast, rate-limit free for any remote git repository)
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
                    except Exception:
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
                        # Only fall back to default branch if user specifically requested a default branch name
                        if clean_ref.lower() in ("main", "master", "head"):
                            for line in lines:
                                parts = line.strip().split()
                                if len(parts) >= 2 and parts[1] in ("HEAD", "refs/heads/main", "refs/heads/master"):
                                    return parts[0].lower()
                except Exception:
                    pass
                return None

            sha = await asyncio.to_thread(_run_ls_remote)
            if sha:
                logger.info("Resolved %s on %s -> %s via git ls-remote", clean_ref, repo_url, sha)
                return sha
        except Exception as exc:
            logger.warning("git ls-remote failed for %s: %s", repo_url, exc)

        # 4. GitHub REST API fallback
        gh_coords = _parse_github_url(repo_url)
        if gh_coords:
            owner, repo = gh_coords
            try:
                async with httpx.AsyncClient(timeout=8.0) as client:
                    for branch_cand in ([clean_ref, "master"] if clean_ref == "main" else [clean_ref]):
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
                    for branch_cand in ([clean_ref, "master"] if clean_ref == "main" else [clean_ref]):
                        patch_url = f"https://github.com/{owner}/{repo}/commit/{branch_cand}.patch"
                        resp = await client.get(patch_url, headers={"User-Agent": "MDT-GitAnalyzer"})
                        if resp.status_code == 200:
                            match = re.search(r"^From\s+([0-9a-fA-F]{40})", resp.text, re.MULTILINE)
                            if match:
                                return match.group(1).lower()
            except Exception as exc:
                logger.warning("GitHub patch SHA resolution fallback failed: %s", exc)

        return clean_ref

    async def analyze_push(
        self,
        repo_url: str,
        commit_sha: str,
        changed_files: Optional[List[str]] = None,
    ) -> List[ChangeInfo]:
        """
        Analyse changed files for a commit or push event.
        If changed_files is omitted or empty, all files in the commit are automatically detected.
        """
        from services.github_app import GitHubAppAuth
        
        # Dynamically fetch installation token for the repo (falls back to PAT)
        dynamic_token = await GitHubAppAuth.get_installation_token_for_repo(repo_url)
        if dynamic_token:
            self._gh._token = dynamic_token
            self._gh._headers["Authorization"] = f"Bearer {dynamic_token}"

        logger.info("analyze_push | repo=%s commit=%s files=%s",
                    repo_url, commit_sha, len(changed_files) if changed_files is not None else "auto-detect")

        # If files explicitly provided, filter to supported extensions
        files = None
        if changed_files:
            files = [f for f in changed_files
                     if Path(f).suffix.lower() in SUPPORTED_EXTENSIONS]
            if not files:
                logger.info("No supported-extension files in specified list, skipping")
                return []

        # 0. Local workspace fast-path (< 50ms, zero network calls)
        if _is_local_workspace_match(repo_url):
            try:
                local_changes = await asyncio.to_thread(
                    self._analyze_from_local_workspace,
                    commit_sha,
                    files,
                )
                if local_changes:
                    logger.info("Extracted %d changes directly from local git repository", len(local_changes))
                    return local_changes
            except Exception as exc:
                logger.warning("Local workspace analysis failed: %s, falling back to remote strategies", exc)

        gh_coords = _parse_github_url(repo_url)

        if gh_coords:
            api_changes = await self._analyze_via_github_api(
                gh_coords[0], gh_coords[1], commit_sha, files)
            if api_changes is not None:
                return api_changes
            logger.warning(
                "GitHub API could not read %s at %s; falling back to git clone",
                repo_url, commit_sha,
            )
            return await self._analyze_via_local_repo(
                repo_url, commit_sha, files or [])
        else:
            return await self._analyze_via_local_repo(
                repo_url, commit_sha, files or [])

    def _analyze_from_local_workspace(
        self,
        target_ref: str,
        files: Optional[List[str]] = None,
    ) -> List[ChangeInfo]:
        """Fast-path for repositories matching the local workspace: diffs and content in < 50ms."""
        git_dir = _find_git_dir() or (Path(__file__).resolve().parent.parent.parent / ".git")
        safe_cwd = tempfile.gettempdir()

        # 1. Resolve commit or target reference
        sha = _resolve_local_workspace_sha(target_ref) or target_ref

        # 2. Determine diff base
        # If target_ref is a branch other than main, diff against main or merge-base
        base_ref = f"{sha}~1"
        if target_ref.lower() not in ("main", "master", "head"):
            main_sha = _resolve_local_workspace_sha("main")
            if main_sha and main_sha != sha:
                mb_res = subprocess.run(
                    ["git", "--git-dir", str(git_dir), "merge-base", main_sha, sha],
                    cwd=safe_cwd,
                    capture_output=True,
                    text=True,
                    timeout=3,
                )
                if mb_res.returncode == 0 and mb_res.stdout.strip():
                    base_ref = mb_res.stdout.strip()
                else:
                    base_ref = main_sha

        # 3. Detect changed files if not explicitly provided
        file_status_map: Dict[str, str] = {}
        if not files:
            res = subprocess.run(
                ["git", "--git-dir", str(git_dir), "diff", "--name-status", base_ref, sha],
                cwd=safe_cwd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="ignore",
                timeout=5,
            )
            if res.returncode == 0 and res.stdout.strip():
                for line in res.stdout.strip().splitlines():
                    parts = line.strip().split(None, 1)
                    if len(parts) == 2:
                        status_code = parts[0][0].upper()
                        fpath = parts[1].strip()
                        if Path(fpath).suffix.lower() in SUPPORTED_EXTENSIONS:
                            st_map = {"A": "added", "D": "deleted", "M": "modified", "R": "modified"}
                            file_status_map[fpath] = st_map.get(status_code, "modified")
                files = list(file_status_map.keys())

        if not files:
            return []

        changes: List[ChangeInfo] = []
        for f in files:
            try:
                change_type = file_status_map.get(f, "modified")
                # Extract diff
                diff_res = subprocess.run(
                    ["git", "--git-dir", str(git_dir), "diff", "-U3", base_ref, sha, "--", f],
                    cwd=safe_cwd,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="ignore",
                    timeout=3,
                )
                diff_text = diff_res.stdout if diff_res.returncode == 0 else ""
                additions, deletions = _count_diff_lines(diff_text)

                # Extract content at target commit
                content = ""
                if change_type != "deleted":
                    show_res = subprocess.run(
                        ["git", "--git-dir", str(git_dir), "show", f"{sha}:{f}"],
                        cwd=safe_cwd,
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        errors="ignore",
                        timeout=3,
                    )
                    content = show_res.stdout if show_res.returncode == 0 else ""

                lang = _EXT_TO_LANG.get(Path(f).suffix.lower(), "unknown")
                ast_meta = self._ast.analyze(content or diff_text, lang)

                ci = ChangeInfo(
                    file_path=f,
                    change_type=change_type,
                    diff_content=diff_text,
                    additions=additions,
                    deletions=deletions,
                    old_content="",
                    new_content=content,
                    ast_metadata=ast_meta,
                )
                changes.append(ci)
            except Exception as exc:
                logger.warning("Local extract failed for %s: %s", f, exc)
                changes.append(self._minimal_change(f))

        return changes

    # ------------------------------------------------------------------ #
    #  Strategy 1 — GitHub API (preferred, no clone)
    # ------------------------------------------------------------------ #

    async def _analyze_via_github_api(
        self,
        owner: str,
        repo: str,
        commit_sha: str,
        files: Optional[List[str]] = None,
    ) -> Optional[List[ChangeInfo]]:
        """Fetch diffs + file contents via GitHub REST API."""
        logger.info("Using GitHub API | owner=%s repo=%s", owner, repo)

        # Fetch the full commit diff once (covers all files in one request)
        file_diffs = await self._gh.get_commit_diff(owner, repo, commit_sha)
        if file_diffs is None:
            return None

        # If files was not specified, auto-detect all supported files in this commit
        if not files:
            files = [f for f in file_diffs.keys()
                     if Path(f).suffix.lower() in SUPPORTED_EXTENSIONS]
            logger.info("Auto-detected %d changed files from commit diff", len(files))

        if not files:
            return []

        # Derive the parent SHA for fetching old content
        parent_sha = await self._get_parent_sha(owner, repo, commit_sha)

        # Fan out file content fetches concurrently with low concurrency to protect rate limits
        tasks = [
            self._build_change_info_from_api(
                owner, repo, f, commit_sha, parent_sha,
                file_diffs.get(f, ""))
            for f in files
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        changes: List[ChangeInfo] = []
        for f, result in zip(files, results):
            if isinstance(result, ChangeInfo):
                changes.append(result)
            else:
                logger.warning("Failed to analyse %s: %s", f, result)
                changes.append(self._minimal_change(f))

        return changes

    async def _build_change_info_from_api(
        self,
        owner: str,
        repo: str,
        file_path: str,
        commit_sha: str,
        parent_sha: Optional[str],
        diff_text: str,
    ) -> ChangeInfo:
        """Build a single ChangeInfo using unified diff text and resilient fast content fallback."""
        additions, deletions = _count_diff_lines(diff_text)

        # Determine change_type from diff mode lines
        change_type = "modified"
        if "new file mode" in diff_text:
            change_type = "added"
        elif "deleted file mode" in diff_text:
            change_type = "deleted"

        # Avoid 100+ requests hitting GitHub rate limits:
        # Only fetch full file content for primary service entrypoints
        new_content = ""
        old_content = ""
        is_entrypoint = any(file_path.endswith(k) for k in ["main.py", "app.py", "server.js", "index.js"])

        if is_entrypoint:
            try:
                new_content = await asyncio.wait_for(
                    self._gh.get_file_content(owner, repo, file_path, commit_sha),
                    timeout=3.0,
                )
            except Exception:
                new_content = ""

        lang = _EXT_TO_LANG.get(Path(file_path).suffix.lower(), "unknown")
        ast_meta = self._ast.analyze(new_content or diff_text, lang)

        return ChangeInfo(
            file_path=file_path,
            change_type=change_type,
            diff_content=diff_text,
            additions=additions,
            deletions=deletions,
            old_content=old_content,
            new_content=new_content,
            ast_metadata=ast_meta,
        )

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

    # ------------------------------------------------------------------ #
    #  Strategy 2 — local gitpython (clone or existing repo)
    # ------------------------------------------------------------------ #

    async def _analyze_via_local_repo(
        self,
        repo_url: str,
        commit_sha: str,
        files: List[str],
    ) -> List[ChangeInfo]:
        """Shallow-clone the repo and use gitpython to extract diffs."""
        logger.info("Falling back to gitpython clone | url=%s", repo_url)
        tmp_dir = tempfile.mkdtemp(prefix="mdt_clone_")
        try:
            repo = await asyncio.to_thread(
                self._clone_repo, repo_url, tmp_dir, commit_sha)
            if not files:
                try:
                    c = repo.commit(commit_sha)
                    diffs = c.parents[0].diff(c) if c.parents else c.diff(None)
                    extracted_files = [str(d.a_path or d.b_path) for d in diffs if (d.a_path or d.b_path)]
                    files = [f for f in extracted_files if Path(f).suffix.lower() in SUPPORTED_EXTENSIONS]
                except Exception:
                    files = []

            changes = []
            for f in files:
                try:
                    ci = await asyncio.to_thread(
                        self._extract_from_repo, repo, commit_sha, f)
                    changes.append(ci)
                except Exception as exc:
                    logger.warning("gitpython extract failed for %s: %s", f, exc)
                    changes.append(self._minimal_change(f))
            return changes
        except Exception as exc:
            logger.error("Clone failed: %s", exc)
            return [self._minimal_change(f) for f in files]
        finally:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)

    @staticmethod
    def _clone_repo(repo_url: str, target_dir: str, commit_sha: str) -> Repo:
        """Shallow clone (depth=2 so we can diff HEAD vs parent)."""
        repo = Repo.clone_from(repo_url, target_dir, depth=2,
                               no_single_branch=True)
        # Checkout the target commit
        repo.git.checkout(commit_sha)
        return repo

    def _extract_from_repo(
        self, repo: Repo, commit_sha: str, file_path: str
    ) -> ChangeInfo:
        """Use gitpython to extract diff + content for one file."""
        commit = repo.commit(commit_sha)
        parents = commit.parents

        diff_text = ""
        old_content = ""
        new_content = ""
        change_type = "modified"

        if parents:
            parent = parents[0]
            diff_text = repo.git.diff(parent.hexsha, commit_sha, "--", file_path)

            # Old content
            try:
                old_blob = parent.tree[file_path]
                old_content = old_blob.data_stream.read().decode("utf-8",
                                                                  errors="replace")
            except KeyError:
                old_content = ""
                change_type = "added"
        else:
            # First commit — everything is new
            change_type = "added"

        # New content
        try:
            new_blob = commit.tree[file_path]
            new_content = new_blob.data_stream.read().decode("utf-8",
                                                              errors="replace")
        except KeyError:
            new_content = ""
            if change_type != "added":
                change_type = "deleted"

        if not diff_text and (old_content or new_content):
            diff_text = _make_simple_diff(file_path, old_content, new_content)

        additions, deletions = _count_diff_lines(diff_text)
        lang = _EXT_TO_LANG.get(Path(file_path).suffix.lower(), "unknown")
        ast_meta = self._ast.analyze(new_content or old_content, lang)

        return ChangeInfo(
            file_path=file_path,
            change_type=change_type,
            diff_content=diff_text,
            additions=additions,
            deletions=deletions,
            old_content=old_content,
            new_content=new_content,
            ast_metadata=ast_meta,
        )

    # ------------------------------------------------------------------ #
    #  Helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _minimal_change(file_path: str, change_type: str = "modified") -> ChangeInfo:
        """Return a minimal ChangeInfo when analysis fails — pipeline still runs."""
        return ChangeInfo(
            file_path=file_path,
            change_type=change_type,
            diff_content="",
            additions=0,
            deletions=0,
            old_content="",
            new_content="",
            ast_metadata={},
        )

    # ------------------------------------------------------------------ #
    #  Convenience — analyse a single local file diff (used in tests)
    # ------------------------------------------------------------------ #

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
