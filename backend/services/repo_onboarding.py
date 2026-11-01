import asyncio
import difflib
import logging
import os
import posixpath
import re
import subprocess
import tempfile
import yaml
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, Callable

from core.config import settings
from core.registry import RegistryManager, current_project_id
from services.dependency_graph import DependencyGraph
from services.git_analyzer import (
    GitHubAPIClient, GitHubRateLimitError, GitAnalyzer, MAX_SOURCE_BYTES, MAX_TOTAL_SOURCE_BYTES, _safe_source_path,
    extract_route_signatures, _EXT_TO_LANG,
    _parse_github_url,
    _find_git_dir,
    _is_local_workspace_match,
)
from services.connection_validator import ConnectionValidator, ConnectionBug
from services.github_app import GitHubAppAuth
from services.deployment_evidence import (compose_ports, compose_references, literal_endpoint, merge_source_calls,
                                        dotenv_literals, compose_default_config, compose_env_files)
from services.aspire_discovery import discover_aspire
from services.coverage_indicators import coverage_indicators, static_coverage_reasons
from services.source_parser import parse_js_ts, parse_python

logger = logging.getLogger(__name__)

COMPOSE_FILENAMES = [
    "docker-compose.yml",
    "docker-compose.yaml",
    "compose.yml",
    "compose.yaml",
]

RENDER_FILENAMES = [
    "render.yaml",
    "render.yml",
]

COMMON_ENTRY_NAMES = [
    "main.py", "app.py", "server.py", "api.py", "routes.py",
    "server.js", "index.js", "app.js", "main.js",
    "server.ts", "index.ts", "app.ts", "main.ts",
    "src/main.py", "src/app.py", "src/server.py", "src/api.py",
    "src/main.jsx", "src/App.jsx", "src/index.jsx", "src/main.js", "src/App.js", "src/index.js",
    "src/main.tsx", "src/App.tsx", "src/index.tsx", "src/main.ts", "src/server.ts", "src/app.ts",
    "app/page.tsx", "app/page.jsx", "app/page.js", "pages/index.tsx", "pages/index.js",
    "main.go", "src/main.go", "src/main.rs", "src/lib.rs",
]


def _get_local_branches(git_dir: Path) -> List[str]:
    """Retrieve all local and remote branches from a git dir in < 10ms."""
    try:
        res = subprocess.run(
            [
                "git",
                "--git-dir",
                str(git_dir),
                "for-each-ref",
                "--format=%(refname:short)",
                "refs/heads",
                "refs/remotes/origin",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=3,
        )
        branches = set()
        if res.returncode == 0:
            for line in res.stdout.splitlines():
                b = line.strip()
                if b.startswith("origin/"):
                    b = b[len("origin/"):]
                if b and b != "HEAD" and b != "origin":
                    branches.add(b)
        return sorted(branches)
    except Exception as exc:
        logger.debug("Failed to list local branches: %s", exc)
        return []


def _find_best_branch_match(requested: str, available: List[str]) -> Optional[str]:
    """Find prefix match or closest matching branch name."""
    clean = requested.strip()
    if not clean or not available:
        return None
    for b in available:
        if b.lower() == clean.lower():
            return b
    prefix_matches = [b for b in available if b.lower().startswith(clean.lower())]
    if prefix_matches:
        return prefix_matches[0]
    sub_matches = [b for b in available if clean.lower() in b.lower()]
    if sub_matches:
        return sub_matches[0]
    close = difflib.get_close_matches(clean, available, n=1, cutoff=0.4)
    if close:
        return close[0]
    return None


def _get_remote_branches_via_ls_remote(repo_url: str) -> List[str]:
    """Fetch remote heads via git ls-remote in < 2s."""
    try:
        res = subprocess.run(
            ["git", "ls-remote", "--heads", repo_url],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
        )
        if res.returncode == 0:
            branches = []
            for line in res.stdout.splitlines():
                parts = line.strip().split()
                if len(parts) >= 2 and parts[1].startswith("refs/heads/"):
                    branches.append(parts[1][len("refs/heads/"):])
            return sorted(branches)
    except Exception as exc:
        logger.debug("Failed to fetch remote branches via ls-remote: %s", exc)
    return []


def _get_local_tree(git_dir: Path, ref: str) -> List[str]:
    """List all files at a given ref using local git in < 15ms."""
    for cand_ref in [ref, f"origin/{ref}"]:
        try:
            res = subprocess.run(
                ["git", "--git-dir", str(git_dir), "ls-tree", "-r", "--name-only", cand_ref],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=3,
            )
            if res.returncode == 0:
                lines = [line.strip() for line in res.stdout.splitlines() if line.strip()]
                if lines:
                    return lines
        except Exception as exc:
            logger.debug("Local git ls-tree failed for cand_ref %s: %s", cand_ref, exc)
    return []


def _get_local_file_content(git_dir: Path, ref: str, file_path: str) -> str:
    """Read an exact bounded blob; do not follow symlinks in a checked-out worktree."""
    from git import Repo
    path = _safe_source_path(file_path)
    try:
        blob = Repo(git_dir).commit(ref).tree[path]
        if blob.size > MAX_SOURCE_BYTES:
            raise ValueError("Source exceeds the 256 KiB limit.")
        return blob.data_stream.read(MAX_SOURCE_BYTES + 1).decode("utf-8")
    except KeyError:
        return ""


class RepoOnboarder:
    """
    Auto-discovers and imports microservice architectures from GitHub repositories.
    Supports docker-compose.yml, render.yaml, polyglot directories, monorepos,
    and single-service repositories.
    """

    def __init__(self):
        self.gh_client = GitHubAPIClient()
        self.dep_graph = DependencyGraph()

    async def import_from_repo(self, repo_url: str, branch: str = "main") -> Dict[str, Any]:
        """
        Ingest a GitHub repository, discover its microservice architecture,
        register it in the system, and run connection validation.
        """
        coords = _parse_github_url(repo_url)
        if not coords:
            raise ValueError(f"Invalid GitHub repository URL: {repo_url}")

        owner, repo = coords
        clean_branch = (branch or "").strip() or "main"

        logger.info("Importing architecture from %s/%s branch=%s", owner, repo, clean_branch)

        tree: List[str] = []
        get_content_fn: Optional[Callable[[str], Any]] = None
        temp_dir_obj: Optional[tempfile.TemporaryDirectory] = None

        try:
            # -------------------------------------------------------------
            # Strategy 1: Local workspace Git fast-path (< 50ms, zero network)
            # -------------------------------------------------------------
            if _is_local_workspace_match(repo_url):
                git_dir = _find_git_dir()
                if git_dir and git_dir.exists():
                    from git import Repo
                    try:
                        target_branch = Repo(git_dir).commit(clean_branch).hexsha
                    except Exception as exc:
                        raise ValueError(f"Requested revision '{clean_branch}' is unavailable.") from exc
                    tree = await asyncio.to_thread(_get_local_tree, git_dir, target_branch)
                    async def _local_get_content(path: str) -> str:
                        return await asyncio.to_thread(_get_local_file_content, git_dir, target_branch, path)
                    get_content_fn = _local_get_content
                    clean_branch = target_branch

            if get_content_fn is None:
                token = await GitHubAppAuth.get_installation_token_for_repo(repo_url)
                if token:
                    self.gh_client._token = token
                    self.gh_client._headers["Authorization"] = f"Bearer {token}"
                analyzer = GitAnalyzer()
                analyzer._gh = self.gh_client
                revision = await analyzer.resolve_commit_sha(repo_url, clean_branch)
                if not revision:
                    raise ValueError(f"Requested revision '{clean_branch}' could not be resolved.")
                clean_branch = revision
                tree = await self.gh_client.get_repo_tree(owner, repo, revision)
                async def _gh_get_content(path: str) -> str:
                    return await self.gh_client.get_file_content(owner, repo, path, revision)
                get_content_fn = _gh_get_content

            tree_set = {p.replace("\\", "/").strip("/") for p in tree} if tree else set()

            # 2. Try to find and parse docker-compose
            compose_content = None
            compose_filename = None
            for fname in COMPOSE_FILENAMES:
                if not tree_set or fname in tree_set:
                    content = await get_content_fn(fname)
                    if content:
                        compose_content = content
                        compose_filename = fname
                        break

            # 3. Try to find and parse render.yaml
            render_content = None
            render_filename = None
            for fname in RENDER_FILENAMES:
                if not tree_set or fname in tree_set:
                    content = await get_content_fn(fname)
                    if content:
                        render_content = content
                        render_filename = fname
                        break

            services: List[Dict[str, Any]] = []
            dependencies: List[Dict[str, Any]] = []
            file_mappings: Dict[str, str] = {}
            service_files: Dict[str, Dict[str, str]] = {}
            compose_warnings = []

            if compose_content:
                logger.info("Found %s in %s/%s", compose_filename, owner, repo)
                defaults = {}
                if ".env" in tree_set:
                    try:
                        defaults = dotenv_literals(await get_content_fn(".env"))
                    except Exception:
                        pass  # Unavailable defaults remain unresolved, never read from this host.
                file_environments, compose_warnings = await compose_env_files(
                    compose_content, compose_filename, tree_set, get_content_fn, defaults)
                services, dependencies, file_mappings = self._parse_compose(compose_content, compose_filename, defaults, file_environments)

            if render_content:
                logger.info("Found %s in %s/%s", render_filename, owner, repo)
                r_services, r_dependencies, r_file_mappings = self._parse_render(render_content)
                for r_s in r_services:
                    if not any(s["name"] == r_s["name"] for s in services):
                        services.append(r_s)
                dependencies.extend(r_dependencies)
                file_mappings.update(r_file_mappings)

            # Alternative deployment systems are separate configurations, not a
            # union of simultaneously deployed services.
            if services:
                k_services, k_dependencies, k_mappings = [], [], {}
                discovery = {"sources": [], "warnings": [], "selected_manifest": compose_filename or render_filename}
            else:
                k_services, k_dependencies, k_mappings, discovery = await self._discover_kubernetes(tree, get_content_fn)
            for service in k_services:
                if not any(existing["name"] == service["name"] for existing in services):
                    services.append(service)
            dependencies.extend(k_dependencies)
            for prefix, name in k_mappings.items():
                file_mappings.setdefault(prefix, name)
            discovery["sources"] = (["compose"] if compose_content else []) + (["render"] if render_content else []) + discovery["sources"]
            if not services:
                services, dependencies, file_mappings, aspire_metadata = await discover_aspire(tree, get_content_fn)
                discovery["sources"].extend(aspire_metadata["sources"])
                discovery["warnings"].extend(aspire_metadata["warnings"])
                if aspire_metadata["sources"]:
                    discovery["selected_manifest_files"] = aspire_metadata["selected_manifest_files"]

            # 4. Discover additional/polyglot service directories or fallback to directory structure
            services, dependencies, file_mappings = await self._infer_from_file_tree(
                owner,
                repo,
                clean_branch,
                tree=tree,
                existing_services=services,
                existing_dependencies=dependencies,
                existing_mappings=file_mappings,
            )
            discovery["sources"] = sorted(set(discovery["sources"]) | {
                service.get("discovery_kind", "unknown") for service in services})

            if not services:
                raise ValueError(
                    "Insufficient architecture evidence: no supported deployment topology or application entrypoints "
                    f"were discovered in {repo_url}. Framework-specific deployment definitions may be unsupported."
                )

            # Read source across each service, retaining coverage and file evidence.
            service_files, coverage = await self._collect_service_sources(services, file_mappings, tree, get_content_fn)
            coverage["discovery"] = discovery
            coverage["transport_evidence"] = getattr(self.gh_client, "source_evidence", {})
            coverage["warnings"].extend(discovery["warnings"])
            coverage["warnings"].extend(compose_warnings)
            if compose_content:
                coverage["warnings"].append("compose_uses_recorded_defaults_not_runtime_environment")
            if any(edge.get("evidence_kind") == "compose_startup_order" for edge in dependencies):
                coverage["warnings"].append("compose_dependencies_are_startup_order_not_verified_calls")
            coverage["warnings"].append("static_topology_is_not_complete_runtime_communication")
            coverage["indicators"] = coverage_indicators(coverage)
            coverage["static_partial"] = bool(static_coverage_reasons(coverage))
            # Backwards-compatible umbrella. New clients display the independently
            # measured dimensions rather than treating this as a file-read ratio.
            coverage["partial"] = True

            # 6. Extract cross-service dependencies from static code analysis & validate connections
            dependencies = merge_source_calls(services, service_files, dependencies, ConnectionValidator)

            connection_bugs = ConnectionValidator.validate_topology(services, service_files)
            from services.connection_validator import ConnectionBug
            for edge in dependencies:
                if edge.get("has_bug") and edge.get("evidence_kind") == "compose_startup_order":
                    connection_bugs.append(ConnectionBug(source_service=edge["from"], target_service=edge["to"],
                        target_url=edge["to"], bug_type="UNDEFINED_COMPOSE_SERVICE", severity="HIGH",
                        description=edge["resolution_reason"], file_path=edge["source_file"], line_number=0,
                        suggestion="Correct depends_on to a declared service name, or supply the missing service in the deployment configuration."))

            # 7. Extract static endpoints & calculate baseline architectural risk scores
            for svc in services:
                sname = svc["name"]
                svc["is_external"] = svc.get("node_type") == "external"

                # Extract exposed endpoints from entrypoint code
                svc_routes = []
                svc_contracts = []
                files = service_files.get(sname, {})
                for fpath, code in files.items():
                    language = _EXT_TO_LANG.get(Path(fpath).suffix.lower(), "unknown")
                    contracts = extract_route_signatures(code, language)
                    svc_contracts.extend({**contract, "source_file": fpath} for contract in contracts)
                    routes = [contract["path"] for contract in contracts] if language in {"python", "javascript", "typescript"} else ConnectionValidator.extract_routes_from_code(code)
                    svc_routes.extend(routes)

                svc_routes = list(dict.fromkeys(svc_routes))
                svc["api_endpoints"] = svc_contracts
                if svc_routes:
                    svc["api_count"] = len({(c["method"], c["path"]) for c in svc_contracts}) or len(svc_routes)
                    svc["endpoints"] = svc_routes
                else:
                    svc["api_count"] = 0
                    svc["endpoints"] = []
                svc["contract_coverage"] = ("observed_static" if svc_contracts else "not_observed")

                # Importing a topology is not a commit-risk assessment.
                svc["risk_score"] = None
                svc["risk_level"] = "UNKNOWN"

            # 8. Save to RegistryManager and Neo4j (Wipe previous project so architectures never mix)
            RegistryManager.clear()
            await self.dep_graph.clear_graph()

            for svc in services:
                RegistryManager.add_service(svc)
                # Neo4j node properties cannot contain maps. The owned raw
                # snapshot retains structured contracts; the legacy graph gets
                # scalar metadata and its existing endpoint strings only.
                await self.dep_graph.add_service(svc["name"], {key: value for key, value in svc.items() if key != "api_endpoints"})

            for dep in dependencies:
                RegistryManager.add_dependency(
                    dep["from"], dep["to"], dep.get("type", "http"), dep.get("endpoint", "")
                )
                await self.dep_graph.add_dependency(
                    dep["from"], dep["to"], dep.get("type", "http"), dep.get("endpoint", ""), evidence=dep
                )

            for prefix, svc_name in file_mappings.items():
                RegistryManager.add_file_mapping(prefix, svc_name)

            # Persist the topology owner only after all registry writes complete.
            # Manual impact analysis can now reject a different repository instead
            # of applying these service mappings to unrelated source files.
            RegistryManager.set_project_context(repo_url, clean_branch, source="repository")
            snapshot = RegistryManager.load()
            snapshot["dependencies"] = dependencies  # Preserve route/file provenance and distinct calls.
            snapshot["coverage"] = coverage
            snapshot.setdefault("project", {})["revision"] = clean_branch
            RegistryManager.save(snapshot)

            return {
                "status": "partial" if coverage["partial"] else "success",
                "coverage": coverage,
                "revision": clean_branch,
                "repo_url": repo_url,
                "branch": clean_branch,
                "project_context": RegistryManager.get_project_context(),
                "compose_file": compose_filename or render_filename or "directory_inferred",
                "services_count": len(services),
                "dependencies_count": len(dependencies),
                "services": services,
                "dependencies": dependencies,
                "file_mappings": file_mappings,
                "connection_bugs": [b.to_dict() for b in connection_bugs],
            }
        finally:
            if temp_dir_obj is not None:
                try:
                    temp_dir_obj.cleanup()
                except Exception as exc:
                    logger.debug("Failed cleaning up temporary directory %s: %s", getattr(temp_dir_obj, 'name', 'unknown'), exc)

    async def _collect_service_sources(self, services, file_mappings, tree, get_content):
        """Read a bounded, deterministic and service-fair source sample with omissions."""
        extensions = {".py", ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".mts", ".cts", ".go", ".rs", ".java", ".cs", ".php", ".rb"}
        ignored = {"node_modules", ".git", "venv", ".venv", "dist", "build", "vendor", "__pycache__"}
        results = {service["name"]: {} for service in services}
        candidates = []
        excluded_source_files = unmapped_source_files = invalid_paths = 0
        excluded_reasons = {}
        for path in sorted(set(tree)):
            try:
                path = _safe_source_path(path)
            except ValueError:
                invalid_paths += 1
                continue
            if Path(path).suffix.lower() not in extensions:
                continue
            generated = Path(path).name.lower().endswith(('.min.js', '.min.mjs', '.min.cjs'))
            if set(path.split("/")) & ignored or generated:
                excluded_source_files += 1
                reason = 'minified_bundle' if generated else 'ignored_directory'
                excluded_reasons[reason] = excluded_reasons.get(reason, 0) + 1
                continue
            prefixes = [(prefix, service) for prefix, service in file_mappings.items()
                        if not prefix or path == prefix.rstrip("/") or path.startswith(prefix.rstrip("/") + "/")]
            if prefixes:
                _, service = max(prefixes, key=lambda match: len(match[0]))
                if service in results:
                    candidates.append((service, path))
                    continue
            unmapped_source_files += 1
        # Round robin prevents one large frontend from consuming every file slot.
        # Each queue retains deterministic entrypoint-first ordering.
        queues = {service: [] for service in results}
        for service, path in candidates:
            queues[service].append(path)
        entry_names = {Path(name).name.lower() for name in COMMON_ENTRY_NAMES}
        for files in queues.values():
            files.sort(key=lambda path: (Path(path).name.lower() not in entry_names, path))
        candidates = [(service, files[index]) for index in range(max(map(len, queues.values()), default=0))
                      for service, files in sorted(queues.items()) if index < len(files)]
        max_files, max_bytes = settings.REPO_SOURCE_MAX_FILES, settings.REPO_SOURCE_MAX_TOTAL_BYTES
        coverage = {"coverage_schema_version": 2,
                    "candidate_files": len(candidates), "files_read": 0, "bytes_read": 0, "bytes_fetched": 0,
                    "byte_budget_used": 0,
                    "files_candidates": len(candidates), "files_attempted": 0,
                    "warnings": [], "source": "static_source", "per_service": {}, "parsers": {},
                    "parser_compatibility": {},
                    "excluded_source_files": excluded_source_files, "unmapped_source_files": unmapped_source_files,
                    "excluded_source_reasons": excluded_reasons,
                    "invalid_tree_paths": invalid_paths, "scan_reason_counts": {},
                    "scan_limits": {"max_files": max_files, "max_total_bytes": max_bytes, "max_file_bytes": MAX_SOURCE_BYTES},
                    "per_service_parsed": {service: 0 for service in results},
                    "per_service_candidates": {service: len(files) for service, files in queues.items()}}
        service_languages = {service: set() for service in results}

        def omitted(reason, count=1):
            coverage["scan_reason_counts"][reason] = coverage["scan_reason_counts"].get(reason, 0) + count

        if invalid_paths:
            coverage["warnings"].append("unsafe_source_paths_excluded")
        for index, (service, path) in enumerate(candidates):
            if coverage["files_attempted"] >= max_files:
                coverage["warnings"].append("source_file_limit_reached")
                omitted("source_file_limit_reached", len(candidates) - index)
                break
            if coverage["byte_budget_used"] >= max_bytes:
                coverage["warnings"].append("total_source_limit_reached")
                omitted("total_source_limit_reached", len(candidates) - index)
                break
            try:
                coverage["files_attempted"] += 1
                source = await get_content(path)
                size = len(source.encode("utf-8"))
                coverage["bytes_fetched"] += size
                coverage["byte_budget_used"] += size
                if size > MAX_SOURCE_BYTES:
                    coverage["warnings"].append(f"source_size_limit:{path}")
                    omitted("source_size_limit")
                    continue
                if coverage["byte_budget_used"] > max_bytes:
                    coverage["warnings"].append("total_source_limit_reached")
                    omitted("total_source_limit_reached", len(candidates) - index)
                    break
                # A tree-listed empty module is valid Python/JS source. Transport
                # failures raise above; emptiness must not consume coverage as a failure.
                results[service][path] = source
                coverage["files_read"] += 1
                coverage["bytes_read"] += size
                language = _EXT_TO_LANG.get(Path(path).suffix.lower(), "unknown")
                service_languages[service].add(language)
                parser = "heuristic"
                if language in {"javascript", "typescript"}:
                    # ASTAnalyzer has an empty-content shortcut used by diffs.
                    # A collected empty module is still valid syntax to parse.
                    parsed = parse_js_ts(source, language)
                    parser = parsed.get("parser_coverage", "failed")
                    coverage["warnings"].extend(f"{warning}:{path}" for warning in parsed.get("parser_warnings", []))
                    for compatibility in parsed.get("parser_compatibility", []):
                        coverage["parser_compatibility"][compatibility] = coverage["parser_compatibility"].get(compatibility, 0) + 1
                elif language == "python":
                    try:
                        parsed = parse_python(source)
                        for compatibility in parsed.mdt_compatibility:
                            coverage['parser_compatibility'][compatibility] = coverage['parser_compatibility'].get(compatibility, 0) + 1
                        parser = "ast"
                    except (SyntaxError, ValueError, RecursionError):
                        parser = "failed"
                        coverage["warnings"].append(f"source_parse_failed:{path}")
                coverage["parsers"][parser] = coverage["parsers"].get(parser, 0) + 1
                if parser in {"ast", "tree_sitter"}:
                    coverage["per_service_parsed"][service] += 1
            except GitHubRateLimitError as exc:
                coverage["warnings"].append(f"{exc.evidence}:{path}")
                omitted("github_rate_limit", len(candidates) - index)
                # One upstream cooldown affects the remaining reads too; do not
                # burn the whole scan budget issuing known-to-fail requests.
                break
            except Exception as exc:
                if path in results[service]:
                    coverage["parsers"]["failed"] = coverage["parsers"].get("failed", 0) + 1
                    coverage["warnings"].append(f"source_parse_failed:{path}")
                    continue
                reason = "source_size_limit" if isinstance(exc, ValueError) and str(exc).startswith("Source exceeds") else "source_unavailable"
                coverage["warnings"].append(f"{reason}:{path}")
                omitted(reason)
                # A failed read may have downloaded bytes before decoding or
                # transport failed. Reserve its bounded per-file allowance so
                # repeated unreadable blobs cannot bypass the aggregate budget.
                # This is conservative budget accounting, not measured bytes.
                coverage["byte_budget_used"] += MAX_SOURCE_BYTES
        coverage["per_service"] = {service: len(files) for service, files in results.items()}
        coverage["missing_source_services"] = [service["name"] for service in services
            if service.get("source_expected", service["name"] in file_mappings.values())
            and not results[service["name"]]]
        coverage["unsupported_contract_services"] = [service["name"] for service in services
            if service.get("source_expected", service["name"] in file_mappings.values())
            and (service_languages[service["name"]] or {service.get("language", "unknown")})
                - {"python", "javascript", "typescript"}]
        coverage["external_source_services"] = [service["name"] for service in services
            if service.get("node_type", "service") == "service" and not results[service["name"]]]
        if coverage["external_source_services"]:
            coverage["warnings"].append("application_source_unavailable_for_declared_services")
        coverage["indicators"] = coverage_indicators(coverage)
        coverage["static_partial"] = bool(static_coverage_reasons(coverage))
        coverage["partial"] = coverage["static_partial"]
        return results, coverage

    @staticmethod
    def _source_prefix(path: Any) -> Optional[str]:
        """Accept repository-relative paths only; never turn ../ into an in-repo mapping."""
        if not isinstance(path, str) or not path.strip() or "$" in path:
            return None
        path = path.replace("\\", "/")
        if path.startswith("/") or re.match(r"^[a-zA-Z]+:", path):
            return None
        normalized = posixpath.normpath(path)
        if normalized == ".." or normalized.startswith("../"):
            return None
        return "" if normalized == "." else normalized.strip("/")

    async def _discover_kubernetes(self, tree, get_content):
        """Read bounded plain manifests. Never render Helm, run kubectl or infer calls from names."""
        directories = {"k8s", "kubernetes", "kubernetes-manifests", "manifests", "deployments"}
        candidates = sorted(path for path in set(tree)
            if Path(path).suffix.lower() in {".yaml", ".yml"}
            and (set(path.lower().split("/")[:-1]) & directories or Path(path).name.startswith("kubernetes"))
            and not set(path.lower().split("/")) & {"examples", "docs", "tests", "test", "node_modules", "vendor"})
        # Read direct manifests in one nearest deployment directory before optional
        # monitoring trees, overlays and copies consume the entire read budget.
        direct = [path for path in candidates if posixpath.basename(posixpath.dirname(path)) in directories]
        excluded = 0
        if direct:
            roots = sorted({posixpath.dirname(path) for path in direct}, key=lambda root: (root.count("/"), root))
            selected = roots[0]
            chosen = [path for path in direct if posixpath.dirname(path) == selected]
            excluded, candidates = len(candidates) - len(chosen), chosen
        metadata = {"sources": [], "warnings": [], "manifest_files_read": 0,
                    "dependency_coverage": "static_only", "unsupported_protocols": []}
        metadata["selected_manifest_files"] = candidates[:32]
        metadata["alternative_manifest_files_excluded"] = excluded
        if excluded:
            metadata["warnings"].append("alternative_kubernetes_configurations_not_combined")
        if len(candidates) > 32:
            metadata["warnings"].append("kubernetes_manifest_file_limit_reached")
        documents, total_bytes = [], 0
        for path in candidates[:32]:
            try:
                content = await get_content(path)
                total_bytes += len(content.encode("utf-8"))
                if len(content.encode("utf-8")) > MAX_SOURCE_BYTES or total_bytes > MAX_TOTAL_SOURCE_BYTES:
                    metadata["warnings"].append("kubernetes_manifest_size_limit_reached")
                    break
                if "{{" in content:
                    metadata["warnings"].append(f"kubernetes_template_unresolved:{path}")
                    continue
                # Reject aliases in deployment discovery to bound YAML object expansion.
                if any(isinstance(token, yaml.tokens.AliasToken) for token in yaml.scan(content)):
                    metadata["warnings"].append(f"kubernetes_yaml_alias_unsupported:{path}")
                    continue
                for document in yaml.safe_load_all(content):
                    if len(documents) >= 256:
                        metadata["warnings"].append("kubernetes_document_limit_reached")
                        break
                    if isinstance(document, dict):
                        documents.append((path, document))
                metadata["manifest_files_read"] += 1
            except Exception:
                metadata["warnings"].append(f"kubernetes_manifest_unavailable:{path}")
        workloads, service_docs = {}, []
        for path, document in documents:
            kind = document.get("kind")
            meta = document.get("metadata") or {}
            name = meta.get("name") if isinstance(meta, dict) else None
            namespace = str(meta.get("namespace") or "default") if isinstance(meta, dict) else "default"
            if not isinstance(name, str) or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]*", name):
                continue
            if kind == "Service":
                service_docs.append((namespace, name, document))
            elif kind in {"Deployment", "StatefulSet", "DaemonSet", "Job"}:
                spec = document.get("spec") or {}
                template = spec.get("template") or {} if isinstance(spec, dict) else {}
                template_spec = template.get("spec") or {} if isinstance(template, dict) else {}
                containers = template_spec.get("containers") or [] if isinstance(template_spec, dict) else []
                if not isinstance(containers, list) or not containers:
                    continue
                key = (namespace, name)
                if key in workloads:
                    metadata["warnings"].append(f"kubernetes_duplicate_workload:{namespace}/{name}")
                    continue
                template_meta = template.get("metadata") or {}
                labels = template_meta.get("labels") or {} if isinstance(template_meta, dict) else {}
                if not isinstance(labels, dict):
                    labels = {}
                workloads[key] = (path, containers, labels)
        names = [name for _, name in workloads]
        services, mappings, aliases, dependencies = [], {}, {}, []
        for (namespace, name), (path, containers, labels) in sorted(workloads.items()):
            # Preserve namespace identity when the same workload name occurs twice.
            node_name = name if names.count(name) == 1 else f"{namespace}/{name}"
            aliases[(namespace, name)] = node_name
            port = None
            for container in containers:
                if not isinstance(container, dict):
                    continue
                ports = container.get("ports") or []
                for item in ports if isinstance(ports, list) else []:
                    if isinstance(item, dict) and isinstance(item.get("containerPort"), int):
                        port = item["containerPort"]
                        break
                if port is not None:
                    break
            roots = [prefix for prefix in (f"src/{name}", f"services/{name}", f"apps/{name}", name)
                     if any(file.startswith(prefix + "/") for file in tree)]
            if len(roots) == 1:
                mappings[roots[0]] = node_name
            elif len(roots) > 1:
                metadata["warnings"].append(f"ambiguous_workload_source:{node_name}")
            node_type = next((kind for container in containers if isinstance(container, dict)
                              if (kind := self._image_node_type(container.get("image", ""))) != "service"), "service")
            services.append({"name": node_name, "display_name": name, "port": port, "node_type": node_type,
                "description": f"Kubernetes {namespace}/{name}", "language": "unknown",
                "discovery_kind": "kubernetes", "source_expected": bool(roots), "source_file": path})
        for namespace, name, document in service_docs:
            spec = document.get("spec") or {}
            selector = spec.get("selector") or {} if isinstance(spec, dict) else {}
            if not isinstance(selector, dict) or not selector:
                continue
            matches = [aliases[key] for key, (_, _, labels) in workloads.items()
                       if key[0] == namespace and all(labels.get(k) == v for k, v in selector.items())]
            if len(matches) == 1:
                aliases[(namespace, name)] = matches[0]
            elif len(matches) > 1:
                metadata["warnings"].append(f"kubernetes_selector_ambiguous:{namespace}/{name}")
        for (namespace, name), (path, containers, _) in sorted(workloads.items()):
            source = aliases[(namespace, name)]
            for container in containers:
                if not isinstance(container, dict):
                    continue
                environment = container.get("env") or []
                for item in environment if isinstance(environment, list) else []:
                    if not isinstance(item, dict):
                        continue
                    value = item.get("value")
                    # A literal endpoint declaration proves configuration reference,
                    # not a runtime call, HTTP protocol or a verified gRPC contract.
                    if not isinstance(value, str):
                        if item.get("valueFrom"):
                            metadata["warnings"].append(f"kubernetes_environment_unresolved:{source}:{item.get('name', '')}")
                        continue
                    resolved = literal_endpoint(value, str(item.get("name", "")))
                    if not resolved:
                        continue
                    hostname, scheme, endpoint = resolved
                    hostparts = hostname.split(".")
                    target = aliases.get((hostparts[1] if len(hostparts) > 1 else namespace, hostparts[0]))
                    if target and target != source:
                        edge = {"from": source, "to": target, "type": scheme or "declared",
                                "endpoint": endpoint or "", "evidence_kind": "kubernetes_env_reference",
                                "source_file": path, "environment_variable": str(item.get("name", ""))}
                        if edge not in dependencies:
                            dependencies.append(edge)
        if workloads:
            metadata["sources"].append("kubernetes")
            metadata["warnings"].append("kubernetes_environment_references_are_not_runtime_calls")
        if any(path.endswith(".proto") for path in tree):
            metadata["unsupported_protocols"].append("grpc_contracts")
            metadata["warnings"].append("grpc_contracts_unresolved")
        return services, dependencies, mappings, metadata

    @staticmethod
    def _image_node_type(image):
        image = str(image).lower().split("@", 1)[0].rsplit("/", 1)[-1].split(":", 1)[0]
        if image in {"postgres", "postgresql", "mysql", "mariadb", "mongo", "mongodb", "redis", "valkey", "neo4j", "chromadb", "chroma"}:
            return "database"
        if image in {"rabbitmq", "kafka", "nats", "zookeeper"}:
            return "broker"
        return "service"

    def _parse_compose(self, yaml_content: str, source_file: str = "docker-compose.yml", defaults=None, file_environments=None) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, str]]:
        """Parse docker-compose.yml into services, dependencies, and file mappings."""
        services = []
        dependencies = []
        file_mappings = {}

        try:
            data = yaml.safe_load(yaml_content) or {}
        except Exception as e:
            logger.warning("Failed to parse docker-compose YAML: %s", e)
            return [], [], {}

        if not isinstance(data, dict):
            return [], [], {}

        compose_services = data.get("services", {})
        if not isinstance(compose_services, dict):
            return [], [], {}
        compose_services = {name: compose_default_config(config, defaults or {}, (file_environments or {}).get(name))
                            for name, config in compose_services.items() if isinstance(config, dict)}

        for sname, sconfig in compose_services.items():
            if not isinstance(sconfig, dict):
                continue

            # Infrastructure belongs in the graph. Classify by declared image,
            # never discard a service because its name contains a product word.
            node_type = self._image_node_type(sconfig.get("image", ""))

            port, host_port = compose_ports(sconfig)

            # Parse file context
            build_info = sconfig.get("build")
            context_path = ""
            if isinstance(build_info, str):
                context_path = build_info
            elif isinstance(build_info, dict):
                context_path = build_info.get("context", "")

            # Normalize context path
            clean_prefix = self._source_prefix(context_path)
            # A shared root build context is not ownership of the entire repo.
            # A nested Dockerfile is useful evidence of the service's source root.
            if clean_prefix == "" and isinstance(build_info, dict):
                dockerfile = self._source_prefix(build_info.get("dockerfile", "Dockerfile"))
                clean_prefix = posixpath.dirname(dockerfile) if dockerfile else ""
            if clean_prefix:
                file_mappings[clean_prefix] = sname
            elif clean_prefix == "" and len(compose_services) == 1:
                file_mappings[""] = sname

            display_name = sname.replace("-service", "").replace("_service", "").replace("-", " ").title() + " Service"

            services.append({
                "name": sname,
                "display_name": display_name,
                "port": port,
                "internal_port": port,
                "host_port": host_port,
                "published_port": host_port,
                "url": f"http://{sname}:{port}" if port is not None else None,
                "description": f"Microservice defined in docker-compose ({sname})",
                "language": self._infer_service_language(sconfig),
                "node_type": node_type,
                "discovery_kind": "compose",
                "source_expected": build_info is not None,
            })

            # Undefined targets are part of the captured problem. Keep them as
            # unresolved nodes rather than silently deleting the invalid link.
            deps = sconfig.get("depends_on", [])
            for dep in deps if isinstance(deps, (list, dict)) else []:
                if not isinstance(dep, str) or not dep.strip():
                    continue
                edge = {"from": sname, "to": dep, "type": "startup", "endpoint": "",
                        "evidence_kind": "compose_startup_order", "source_file": source_file}
                if dep not in compose_services:
                    reason = f"{sname} requires '{dep}', but that service is not declared in {source_file}. Check the selected Compose files and overrides."
                    edge.update(has_bug=True, resolution_reason=reason)
                    if not any(service["name"] == dep for service in services):
                        services.append({"name": dep, "node_type": "external", "is_external": True,
                            "is_broken": True, "resolution_reason": f"Not declared in {source_file}.",
                            "resolution_source": source_file, "source_expected": False,
                            "discovery_kind": "compose_unresolved", "port": None, "url": None})
                dependencies.append(edge)

        dependencies.extend(compose_references(compose_services, source_file))
        names = {service["name"] for service in services}
        dependencies = [edge for edge in dependencies if edge["from"] in names and edge["to"] in names]
        return services, dependencies, file_mappings
    def _parse_render(self, yaml_content: str) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, str]]:
        """Parse render.yaml into services, dependencies, and file mappings."""
        services = []
        dependencies = []
        file_mappings = {}

        try:
            data = yaml.safe_load(yaml_content) or {}
        except Exception as e:
            logger.warning("Failed to parse render.yaml: %s", e)
            return [], [], {}

        render_services = data.get("services", [])
        if not isinstance(render_services, list):
            return [], [], {}

        for idx, svc in enumerate(render_services):
            if not isinstance(svc, dict):
                continue
            sname = svc.get("name", f"service-{idx+1}")
            root_dir = str(svc.get("rootDir", "")).lstrip("./").strip("/").strip()
            runtime = str(svc.get("runtime", "unknown")).lower()
            build_cmd = str(svc.get("buildCommand", "")).lower()

            if any(k in runtime for k in ["python", "py"]) or "pip" in build_cmd:
                lang = "python"
            elif any(k in runtime for k in ["node", "js", "ts"]) or "npm" in build_cmd or "yarn" in build_cmd:
                lang = "javascript"
            elif "go" in runtime:
                lang = "go"
            elif "rust" in runtime:
                lang = "rust"
            elif "ruby" in runtime:
                lang = "ruby"
            elif "java" in runtime:
                lang = "java"
            else:
                lang = "python" if "uvicorn" in str(svc.get("startCommand", "")).lower() else "unknown"

            port = None
            display_name = sname.replace("-service", "").replace("_service", "").replace("-", " ").replace("_", " ").title() + " Service"

            services.append({
                "name": sname,
                "display_name": display_name,
                "port": port,
                "url": f"http://{sname}:{port}" if port is not None else None,
                "description": f"Service defined in render.yaml ({sname})",
                "language": lang,
                "discovery_kind": "render",
                "source_expected": True,
            })

            if root_dir:
                file_mappings[root_dir] = sname

        return services, dependencies, file_mappings

    @classmethod
    def _infer_service_language(cls, sconfig: Dict[str, Any]) -> str:
        """Infer programming language from container image or config dictionary."""
        text = str(sconfig.get("image", "")).lower() + " " + str(sconfig.get("build", "")).lower()
        if any(k in text for k in ["python", "py"]):
            return "python"
        if any(k in text for k in ["node", "javascript", "typescript"]):
            return "javascript"
        if any(k in text for k in ["golang", "go:", "go-", "go/"]) or text.startswith("go:"):
            return "go"
        if any(k in text for k in ["openjdk", "java", "maven", "gradle"]):
            return "java"
        if any(k in text for k in ["rust", "cargo"]):
            return "rust"
        if any(k in text for k in ["dotnet", "csharp", "aspnet", "mcr.microsoft"]):
            return "csharp"
        if any(k in text for k in ["ruby", "rails"]):
            return "ruby"
        if any(k in text for k in ["php", "laravel", "symfony"]):
            return "php"
        return "unknown"

    async def _infer_from_file_tree(
        self,
        owner: str,
        repo: str,
        branch: str,
        tree: Optional[List[str]] = None,
        existing_services: Optional[List[Dict[str, Any]]] = None,
        existing_dependencies: Optional[List[Dict[str, Any]]] = None,
        existing_mappings: Optional[Dict[str, str]] = None
    ) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, str]]:
        """
        Inspect repository file tree to discover service directories,
        supporting monorepos, fullstack apps, polyglot directories, and single-service repos.
        """
        if tree is None:
            try:
                tree = await self.gh_client.get_repo_tree(owner, repo, branch)
            except Exception as e:
                logger.warning("Could not fetch repo tree: %s", e)
                tree = []

        services: List[Dict[str, Any]] = list(existing_services or [])
        # Compose/Render dependencies are authoritative declarations.  Keep
        # them while inferring extra services from the file tree; previously
        # this reset to an empty list and silently removed order -> user.
        dependencies: List[Dict[str, Any]] = list(existing_dependencies or [])
        file_mappings: Dict[str, str] = dict(existing_mappings or {})

        if not tree:
            return services, dependencies, file_mappings

        service_dirs: Dict[str, Dict[str, Any]] = {}
        ignored_roots = {
            "docs", "doc", "test", "tests", ".github", ".vscode", ".idea",
            "scripts", "build", "deploy", "datasets", "results", ".streamlit",
            "assets", "static", "public", "dist", "node_modules", "venv",
            ".git", "coverage", "common", "shared", "utils", "lib",
            "examples", "example", "samples", "sample", "docs_src", "tutorial", "tutorials", "demos"
        }
        known_service_names = {
            "backend", "frontend", "server", "client", "api", "web", "ui",
            "gateway", "worker", "auth", "admin", "portal", "dashboard",
            "engine", "microservice", "service"
        }
        # Map files by top-level or sub-package directory
        dir_files: Dict[str, List[str]] = {}
        root_files: List[str] = []

        for p in tree:
            clean_p = p.replace("\\", "/").strip("/")
            parts = clean_p.split("/")
            if len(parts) == 1:
                root_files.append(clean_p)
                continue

            top = parts[0]
            if top in ignored_roots:
                continue

            if top in ("services", "apps", "packages", "microservices", "src") and len(parts) >= 3:
                skey = f"{top}/{parts[1]}"
            elif top == "src":
                continue
            else:
                skey = top

            dir_files.setdefault(skey, []).append(clean_p)

        already_mapped_dirs = set(file_mappings.keys())
        already_registered_names = {s["name"].lower() for s in services}
        deployment_defined = any(service.get("discovery_kind") in {"kubernetes", "compose", "render", "aspire"} for service in services)

        # Determine which directories are actual services
        for sdir, files in dir_files.items():
            base_dir_name = sdir.split("/")[-1].lower()

            if sdir in already_mapped_dirs:
                continue

            # A Compose declaration and its matching directory complement each
            # other. Previously the existing name prevented the missing mapping.
            existing = next((service for service in services if service["name"].lower() == base_dir_name), None)
            if existing:
                if existing.get("node_type", "service") == "service" and existing["name"] not in file_mappings.values():
                    file_mappings[sdir] = existing["name"]
                    existing["source_expected"] = True
                continue
            if deployment_defined:
                # Shared Docker build templates, alternate profiles and source
                # directory aliases are not additional deployed components.
                continue

            is_service_dir = False
            direct_names = {file[len(sdir) + 1:].lower() for file in files}
            explicit_entry = bool(direct_names & {"dockerfile", "procfile", "main.py", "app.py", "server.py",
                                  "server.js", "server.ts", "main.go", "src/main.rs", "src/main.jsx",
                                  "src/main.tsx", "app/page.tsx", "app/page.jsx"})
            named_app = base_dir_name in known_service_names or "service" in base_dir_name
            if "dockerfile" in direct_names or "procfile" in direct_names:
                is_service_dir = True
            elif named_app and explicit_entry:
                is_service_dir = True
            elif sdir.split("/")[0] in {"services", "apps", "microservices"} and explicit_entry:
                is_service_dir = True

            if is_service_dir:
                sname = base_dir_name
                if sname in already_registered_names:
                    sname = f"{sdir.replace('/', '-')}"
                service_dirs[sname] = {
                    "dir": sdir,
                    "files": files,
                }

        for idx, (sname, data) in enumerate(service_dirs.items()):
            files = data["files"]
            files_str = " ".join(files).lower()

            if "go.mod" in files_str or ".go" in files_str:
                lang = "go"
            elif any(k in files_str for k in ["requirements.txt", "pipfile", "pyproject.toml", ".py"]):
                lang = "python"
            elif any(k in files_str for k in ["package.json", ".ts", ".tsx", ".js", ".jsx"]):
                lang = "javascript"
            elif any(k in files_str for k in ["cargo.toml", ".rs"]):
                lang = "rust"
            elif any(k in files_str for k in ["pom.xml", "build.gradle", ".java"]):
                lang = "java"
            elif any(k in files_str for k in ["gemfile", ".rb"]):
                lang = "ruby"
            elif any(k in files_str for k in ["composer.json", ".php"]):
                lang = "php"
            elif any(k in files_str for k in [".csproj", ".cs"]):
                lang = "csharp"
            else:
                lang = "unknown"

            port = None  # A directory name does not establish a listening port.

            display_name = sname.replace("-service", "").replace("_service", "").replace("-", " ").replace("_", " ").title() + " Service"

            services.append({
                "name": sname,
                "display_name": display_name,
                "port": port,
                "url": f"http://{sname}:{port}" if port is not None else None,
                "description": f"Inferred microservice from {data['dir']}",
                "language": lang,
                "discovery_kind": "directory_entrypoint",
                "source_expected": True,
            })

            file_mappings[data["dir"]] = sname

        # Single-service repository detection (root application)
        if not services and (root_files or tree):
            all_files_str = " ".join(tree).lower()
            # package.json, index.js, pyproject.toml and docs examples also occur
            # in libraries. Require an application/deployment entrypoint.
            root_app_entries = {"dockerfile", "procfile", "main.py", "app.py", "server.py", "server.js", "server.ts",
                                "src/server.js", "src/server.ts", "src/main.jsx", "src/main.tsx", "app/page.tsx"}
            has_entry = bool({file.lower() for file in tree} & root_app_entries)
            if has_entry:
                sname = repo.lower().replace("_", "-")
                if "go.mod" in all_files_str:
                    lang = "go"
                elif any(k in all_files_str for k in ["requirements.txt", ".py"]):
                    lang = "python"
                elif any(k in all_files_str for k in ["package.json", ".js", ".ts"]):
                    lang = "javascript"
                elif "cargo.toml" in all_files_str:
                    lang = "rust"
                elif any(k in all_files_str for k in ["pom.xml", ".java"]):
                    lang = "java"
                else:
                    lang = "python"

                services.append({
                    "name": sname,
                    "display_name": sname.replace("-", " ").title() + " Service",
                    "port": None,
                    "url": None,
                    "description": f"Single-service application from {owner}/{repo}",
                    "language": lang,
                    "discovery_kind": "application_entrypoint",
                    "source_expected": True,
                })
                file_mappings[""] = sname

        # Update manifest-only unknown languages from mapped source files, without
        # creating relationships solely because names resemble frontend/backend.
        suffix_languages = {".py": "python", ".ts": "typescript", ".tsx": "typescript", ".js": "javascript",
                           ".jsx": "javascript", ".go": "go", ".java": "java", ".cs": "csharp", ".rs": "rust"}
        for service in services:
            if service.get("language", "unknown") != "unknown":
                continue
            prefixes = [prefix for prefix, name in file_mappings.items() if name == service["name"]]
            counts = {}
            for path in tree:
                if any(not prefix or path.startswith(prefix + "/") for prefix in prefixes):
                    language = suffix_languages.get(Path(path).suffix.lower())
                    if language:
                        counts[language] = counts.get(language, 0) + 1
            if counts:
                service["language"] = max(sorted(counts), key=counts.get)

        return services, dependencies, file_mappings

