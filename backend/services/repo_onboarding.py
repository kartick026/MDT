import asyncio
import difflib
import logging
import os
import re
import subprocess
import tempfile
import yaml
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, Callable

from core.registry import RegistryManager
from services.dependency_graph import DependencyGraph
from services.git_analyzer import (
    GitHubAPIClient,
    _parse_github_url,
    _find_git_dir,
    _is_local_workspace_match,
)
from services.connection_validator import ConnectionValidator, ConnectionBug
from services.github_app import GitHubAppAuth

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
        except Exception:
            pass
    return []


def _get_local_file_content(git_dir: Path, ref: str, file_path: str) -> str:
    """Read file content at a given ref using local git in < 5ms."""
    clean_p = file_path.replace("\\", "/").lstrip("/")
    for cand_ref in [ref, f"origin/{ref}"]:
        try:
            res = subprocess.run(
                ["git", "--git-dir", str(git_dir), "show", f"{cand_ref}:{clean_p}"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=3,
            )
            if res.returncode == 0:
                return res.stdout
        except Exception:
            pass
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
                    local_branches = await asyncio.to_thread(_get_local_branches, git_dir)
                    target_branch = None
                    if clean_branch in local_branches:
                        target_branch = clean_branch
                    else:
                        for b in local_branches:
                            if b.lower() == clean_branch.lower():
                                target_branch = b
                                break

                    if not target_branch:
                        suggestion = _find_best_branch_match(clean_branch, local_branches)
                        avail_str = ", ".join(local_branches[:8]) if local_branches else "none"
                        err_msg = f"Branch '{clean_branch}' not found in repository."
                        if suggestion:
                            err_msg += f" Did you mean '{suggestion}'?"
                        err_msg += f" Available branches: {avail_str}"
                        raise ValueError(err_msg)

                    logger.info("Using local git fast-path for %s on branch %s", repo_url, target_branch)
                    tree = await asyncio.to_thread(_get_local_tree, git_dir, target_branch)
                    async def _local_get_content(path: str) -> str:
                        return await asyncio.to_thread(_get_local_file_content, git_dir, target_branch, path)
                    get_content_fn = _local_get_content
                    clean_branch = target_branch

            # -------------------------------------------------------------
            # Strategy 2: Cloned Repository Fast-Path (Single shallow clone, serves all files from disk)
            # -------------------------------------------------------------
            if get_content_fn is None:
                clone_url = f"https://github.com/{owner}/{repo}.git"
                dynamic_token = await GitHubAppAuth.get_installation_token_for_repo(repo_url)
                if dynamic_token:
                    self.gh_client._token = dynamic_token
                    self.gh_client._headers["Authorization"] = f"Bearer {dynamic_token}"
                    clone_url = f"https://x-access-token:{dynamic_token}@github.com/{owner}/{repo}.git"

                loop = asyncio.get_running_loop()
                def _attempt_shallow_clone():
                    td = tempfile.TemporaryDirectory()
                    try:
                        res = subprocess.run(
                            ["git", "clone", "--depth=1", "--single-branch", "--branch", clean_branch, clone_url, td.name],
                            capture_output=True,
                            text=True,
                            encoding="utf-8",
                            errors="replace",
                            timeout=25,
                        )
                        if res.returncode == 0:
                            tree_res = subprocess.run(
                                ["git", "--git-dir", os.path.join(td.name, ".git"), "ls-files"],
                                capture_output=True,
                                text=True,
                                encoding="utf-8",
                                errors="replace",
                                timeout=5,
                            )
                            flist = [l.strip() for l in tree_res.stdout.splitlines() if l.strip()]
                            return td, flist
                        td.cleanup()
                        err_out = res.stderr or res.stdout
                        return None, err_out
                    except Exception as e:
                        td.cleanup()
                        return None, str(e)

                td_obj, clone_result = await loop.run_in_executor(None, _attempt_shallow_clone)
                if td_obj is not None and isinstance(clone_result, list):
                    temp_dir_obj = td_obj
                    tree = clone_result
                    td_path = Path(td_obj.name)
                    logger.info("Successfully shallow-cloned %s/%s at branch %s (%d files)", owner, repo, clean_branch, len(tree))

                    async def _disk_get_content(path: str) -> str:
                        clean_p = path.replace("\\", "/").lstrip("/")
                        full_p = td_path / clean_p
                        if full_p.is_file():
                            try:
                                return full_p.read_text(encoding="utf-8", errors="replace")
                            except Exception:
                                return ""
                        return ""

                    get_content_fn = _disk_get_content
                else:
                    clone_err_str = str(clone_result)
                    if "Remote branch" in clone_err_str or "not found in upstream" in clone_err_str:
                        remote_branches = await asyncio.to_thread(_get_remote_branches_via_ls_remote, clone_url)
                        if remote_branches and clean_branch not in remote_branches:
                            suggestion = _find_best_branch_match(clean_branch, remote_branches)
                            avail_str = ", ".join(remote_branches[:8])
                            err_msg = f"Branch '{clean_branch}' not found on remote {repo_url}."
                            if suggestion:
                                err_msg += f" Did you mean '{suggestion}'?"
                            err_msg += f" Available branches: {avail_str}"
                            raise ValueError(err_msg)

            # -------------------------------------------------------------
            # Strategy 3: Remote GitHub REST API Fallback
            # -------------------------------------------------------------
            if get_content_fn is None:
                tree = await self.gh_client.get_repo_tree(owner, repo, clean_branch)
                if not tree:
                    remote_branches = await asyncio.to_thread(
                        _get_remote_branches_via_ls_remote, f"https://github.com/{owner}/{repo}.git"
                    )
                    if remote_branches and clean_branch not in remote_branches:
                        suggestion = _find_best_branch_match(clean_branch, remote_branches)
                        avail_str = ", ".join(remote_branches[:8])
                        err_msg = f"Branch '{clean_branch}' not found on {owner}/{repo}."
                        if suggestion:
                            err_msg += f" Did you mean '{suggestion}'?"
                        err_msg += f" Available branches: {avail_str}"
                        raise ValueError(err_msg)

                async def _gh_get_content(path: str) -> str:
                    return await self.gh_client.get_file_content(owner, repo, path, clean_branch)
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

            if compose_content:
                logger.info("Found %s in %s/%s", compose_filename, owner, repo)
                services, dependencies, file_mappings = self._parse_compose(compose_content)

            if render_content:
                logger.info("Found %s in %s/%s", render_filename, owner, repo)
                r_services, r_dependencies, r_file_mappings = self._parse_render(render_content)
                for r_s in r_services:
                    if not any(s["name"] == r_s["name"] for s in services):
                        services.append(r_s)
                dependencies.extend(r_dependencies)
                file_mappings.update(r_file_mappings)

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

            if not services:
                raise ValueError(
                    f"No microservices could be discovered in {repo_url} (checked docker-compose, render.yaml, and directory structures)."
                )

            # 5. Fetch primary source code files for each service concurrently
            async def fetch_service_entrypoints(svc: Dict[str, Any]) -> tuple[str, Dict[str, str]]:
                sname = svc["name"]
                prefix = ""
                for pref, mapped_name in file_mappings.items():
                    if mapped_name == sname:
                        prefix = pref.rstrip("/")
                        break

                matched_candidates = []
                if tree:
                    norm_prefix = f"{prefix}/" if prefix else ""
                    for p in tree:
                        clean_p = p.replace("\\", "/").strip("/")
                        if norm_prefix:
                            if clean_p.startswith(norm_prefix):
                                rel_p = clean_p[len(norm_prefix):]
                                if rel_p in COMMON_ENTRY_NAMES or Path(clean_p).name.lower() in [
                                    "main.py", "app.py", "server.py", "api.py", "page.tsx", "page.jsx",
                                    "index.js", "server.js", "app.jsx", "main.jsx", "app.tsx", "main.tsx"
                                ]:
                                    matched_candidates.append(clean_p)
                        else:
                            if clean_p in COMMON_ENTRY_NAMES:
                                matched_candidates.append(clean_p)

                    # If still nothing matched, grab any source code file in that service directory
                    if not matched_candidates and norm_prefix:
                        for p in tree:
                            clean_p = p.replace("\\", "/").strip("/")
                            if clean_p.startswith(norm_prefix):
                                ext = Path(clean_p).suffix.lower()
                                if ext in {".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".rs", ".java", ".cs", ".php", ".rb"}:
                                    matched_candidates.append(clean_p)
                                    if len(matched_candidates) >= 2:
                                        break

                fallback_candidates = [
                    f"{prefix}/main.py",
                    f"{prefix}/app.py",
                    f"{prefix}/server.js",
                    f"{prefix}/index.js",
                ] if prefix else ["main.py", "app.py", "server.js", "index.js"]

                if tree_set:
                    candidates = [c for c in matched_candidates if c.lstrip("/") in tree_set]
                else:
                    candidates = matched_candidates or fallback_candidates

                found = {}
                for cand in candidates:
                    cand_clean = cand.lstrip("/")
                    code = await get_content_fn(cand_clean)
                    if code:
                        found[cand_clean] = code
                        break  # Stop at first valid entrypoint file
                return sname, found

            results = await asyncio.gather(*(fetch_service_entrypoints(svc) for svc in services))
            for sname, found in results:
                service_files[sname] = found

            # 6. Extract cross-service dependencies from static code analysis & validate connections
            for sname, files in service_files.items():
                if sname == "unknown":
                    continue
                for fpath, code in files.items():
                    calls = ConnectionValidator.extract_outbound_calls(code, file_path=fpath)
                    for call in calls:
                        target_host = call["host"]
                        target_port = call["port"]
                        call_path = call["path"] or "/"
                        target_svc = ConnectionValidator._resolve_host_to_service(
                            target_host, target_port, {s["name"]: s for s in services}
                        )
                        if target_svc and target_svc != sname and any(s["name"] == target_svc for s in services):
                            clean_endpoint = call_path if call_path != "/" else "/"
                            existing = next((d for d in dependencies if d["from"] == sname and d["to"] == target_svc), None)
                            if existing:
                                if existing.get("endpoint") in ("/", "") and clean_endpoint not in ("/", ""):
                                    existing["endpoint"] = clean_endpoint
                            else:
                                dependencies.append({
                                    "from": sname,
                                    "to": target_svc,
                                    "type": "http",
                                    "endpoint": clean_endpoint,
                                })

            connection_bugs = ConnectionValidator.validate_topology(services, service_files)

            # 7. Extract static endpoints & calculate baseline architectural risk scores
            for svc in services:
                sname = svc["name"]
                svc["is_external"] = True

                # Extract exposed endpoints from entrypoint code
                svc_routes = []
                files = service_files.get(sname, {})
                for fpath, code in files.items():
                    routes = ConnectionValidator.extract_routes_from_code(code)
                    svc_routes.extend(routes)

                svc_routes = list(dict.fromkeys(svc_routes))
                if svc_routes:
                    svc["api_count"] = len(svc_routes)
                    svc["endpoints"] = svc_routes
                else:
                    is_web = any(k in sname.lower() for k in ["frontend", "ui", "web", "client"])
                    svc["api_count"] = 1 if is_web else (len([d for d in dependencies if d['to'] == sname]) or 1)
                    svc["endpoints"] = ["/"] if is_web else []

                # Calculate risk based on architectural defects
                src_bugs = [b for b in connection_bugs if b.source_service == sname]
                tgt_bugs = [b for b in connection_bugs if b.target_service == sname]

                if any(b.severity == "CRITICAL" for b in src_bugs):
                    score = 80.0
                    level = "CRITICAL"
                elif any(b.severity == "HIGH" for b in src_bugs):
                    score = 60.0
                    level = "HIGH"
                elif any(b.severity == "MEDIUM" for b in src_bugs):
                    score = 40.0
                    level = "MEDIUM"
                elif tgt_bugs:
                    score = 25.0
                    level = "LOW"
                else:
                    score = 15.0 + min(15.0, len([d for d in dependencies if d['from'] == sname or d['to'] == sname]) * 5.0)
                    level = "LOW"

                svc["risk_score"] = round(score, 1)
                svc["risk_level"] = level

            # 8. Save to RegistryManager and Neo4j (Wipe previous project so architectures never mix)
            RegistryManager.clear()
            await self.dep_graph.clear_graph()

            for svc in services:
                RegistryManager.add_service(svc)
                await self.dep_graph.add_service(svc["name"], svc)

            for dep in dependencies:
                RegistryManager.add_dependency(
                    dep["from"], dep["to"], dep.get("type", "http"), dep.get("endpoint", "")
                )
                await self.dep_graph.add_dependency(
                    dep["from"], dep["to"], dep.get("type", "http"), dep.get("endpoint", "")
                )

            for prefix, svc_name in file_mappings.items():
                RegistryManager.add_file_mapping(prefix, svc_name)

            # Persist the topology owner only after all registry writes complete.
            # Manual impact analysis can now reject a different repository instead
            # of applying these service mappings to unrelated source files.
            RegistryManager.set_project_context(repo_url, clean_branch, source="repository")

            # 9. Persist initial architectural risk audit in Neo4j analysis history
            avg_score = round(sum(s.get("risk_score", 0) for s in services) / max(len(services), 1), 1)
            overall_severity = "CRITICAL" if avg_score >= 75 else ("HIGH" if avg_score >= 50 else ("MEDIUM" if avg_score >= 25 else "LOW"))

            try:
                await self.dep_graph.record_analysis(
                    commit_sha=f"import-{clean_branch[:12]}",
                    service_names=[s["name"] for s in services],
                    risk_score=avg_score,
                    severity=overall_severity,
                    changed_files=list(file_mappings.keys()) or ["repository_root"],
                    repo_url=repo_url,
                    branch_ref=clean_branch,
                )
            except Exception as e:
                logger.warning("Could not record initial architecture analysis: %s", e)

            return {
                "status": "success",
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
                except Exception:
                    pass

    def _parse_compose(self, yaml_content: str) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, str]]:
        """Parse docker-compose.yml into services, dependencies, and file mappings."""
        services = []
        dependencies = []
        file_mappings = {}

        try:
            data = yaml.safe_load(yaml_content) or {}
        except Exception as e:
            logger.warning("Failed to parse docker-compose YAML: %s", e)
            return [], [], {}

        compose_services = data.get("services", {})
        if not isinstance(compose_services, dict):
            return [], [], {}

        for sname, sconfig in compose_services.items():
            if not isinstance(sconfig, dict):
                continue

            # Ignore infrastructure services like databases/brokers in the microservices overview
            image = str(sconfig.get("image", "")).lower()
            if any(infra in sname.lower() or infra in image for infra in ["neo4j", "chroma", "redis", "postgres", "mysql", "rabbitmq", "kafka", "mongo"]):
                continue

            # Parse port
            port = 8000
            host_port = 8000
            ports = sconfig.get("ports", [])
            if ports and isinstance(ports, list):
                raw_port = str(ports[0])
                if ":" in raw_port:
                    parts = raw_port.split(":")
                    try:
                        host_port = int(parts[0].strip("'\""))
                        port = int(parts[-1].strip("'\""))  # Container internal port
                    except ValueError:
                        pass
                else:
                    try:
                        port = int(raw_port)
                        host_port = port
                    except ValueError:
                        pass

            # Parse file context
            build_info = sconfig.get("build")
            context_path = ""
            if isinstance(build_info, str):
                context_path = build_info
            elif isinstance(build_info, dict):
                context_path = build_info.get("context", "")

            # Normalize context path
            clean_prefix = context_path.lstrip("./").strip("/")
            if clean_prefix:
                file_mappings[clean_prefix] = sname

            display_name = sname.replace("-service", "").replace("_service", "").replace("-", " ").title() + " Service"

            services.append({
                "name": sname,
                "display_name": display_name,
                "port": port,
                "internal_port": port,
                "host_port": host_port,
                "published_port": host_port,
                "url": f"http://{sname}:{port}",
                "description": f"Microservice defined in docker-compose ({sname})",
                "language": self._infer_service_language(sconfig)
            })

            # Parse dependencies (depends_on)
            deps = sconfig.get("depends_on", [])
            if isinstance(deps, list):
                for dep in deps:
                    if dep in compose_services and not any(infra in dep.lower() for infra in ["neo4j", "chroma", "redis", "postgres", "mongo"]):
                        dependencies.append({
                            "from": sname,
                            "to": dep,
                            "type": "http",
                            "endpoint": "/"
                        })
            elif isinstance(deps, dict):
                for dep in deps.keys():
                    if dep in compose_services and not any(infra in dep.lower() for infra in ["neo4j", "chroma", "redis", "postgres", "mongo"]):
                        dependencies.append({
                            "from": sname,
                            "to": dep,
                            "type": "http",
                            "endpoint": "/"
                        })

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

        base_port = 8000
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

            port = base_port + idx
            display_name = sname.replace("-service", "").replace("_service", "").replace("-", " ").replace("_", " ").title() + " Service"

            services.append({
                "name": sname,
                "display_name": display_name,
                "port": port,
                "url": f"http://{sname}:{port}",
                "description": f"Service defined in render.yaml ({sname})",
                "language": lang
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
            ".git", "coverage", "common", "shared", "utils", "lib", "src"
        }
        known_service_names = {
            "backend", "frontend", "server", "client", "api", "web", "ui",
            "gateway", "worker", "auth", "admin", "portal", "dashboard",
            "engine", "microservice", "service"
        }
        code_entry_indicators = {
            "main.py", "app.py", "server.js", "index.js", "package.json",
            "requirements.txt", "dockerfile", "go.mod", "cargo.toml",
            "pom.xml", "build.gradle", "tsconfig.json"
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

            if top in ("services", "apps", "packages", "microservices") and len(parts) >= 2:
                skey = f"{top}/{parts[1]}"
            else:
                skey = top

            dir_files.setdefault(skey, []).append(clean_p)

        already_mapped_dirs = set(file_mappings.keys())
        already_registered_names = {s["name"].lower() for s in services}

        # Determine which directories are actual services
        for sdir, files in dir_files.items():
            base_dir_name = sdir.split("/")[-1].lower()

            if sdir in already_mapped_dirs or base_dir_name in already_registered_names:
                continue

            is_service_dir = False
            if base_dir_name in known_service_names:
                is_service_dir = True
            elif "service" in base_dir_name or "app" in base_dir_name:
                is_service_dir = True
            else:
                file_names = {Path(f).name.lower() for f in files}
                if file_names & code_entry_indicators:
                    is_service_dir = True

            if is_service_dir:
                sname = base_dir_name
                if sname in already_registered_names:
                    sname = f"{sdir.replace('/', '-')}"
                service_dirs[sname] = {
                    "dir": sdir,
                    "files": files,
                }

        base_port = 8000 + len(services)
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

            # 3000 for frontend/ui/web/client, 8000+ for backend/services
            if any(k in sname for k in ["frontend", "ui", "web", "client"]) and lang == "javascript":
                port = 3000
            else:
                port = base_port + idx + 1

            display_name = sname.replace("-service", "").replace("_service", "").replace("-", " ").replace("_", " ").title() + " Service"

            services.append({
                "name": sname,
                "display_name": display_name,
                "port": port,
                "url": f"http://{sname}:{port}",
                "description": f"Inferred microservice from {data['dir']}",
                "language": lang
            })

            file_mappings[data["dir"]] = sname

        # Single-service repository detection (root application)
        if not services and (root_files or tree):
            all_files_str = " ".join(tree).lower()
            has_entry = any(Path(f).name.lower() in code_entry_indicators for f in (root_files or tree))
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
                    "port": 8000,
                    "url": f"http://{sname}:8000",
                    "description": f"Single-service application from {owner}/{repo}",
                    "language": lang
                })
                file_mappings[""] = sname

        # Infer dependencies between discovered services (e.g. frontend -> backend)
        for s1 in services:
            n1 = s1["name"].lower()
            is_client = any(k in n1 for k in ["frontend", "client", "ui", "web"])
            if is_client:
                for s2 in services:
                    n2 = s2["name"].lower()
                    if s1["name"] != s2["name"] and any(k in n2 for k in ["backend", "api", "server"]):
                        if not any(d["from"] == s1["name"] and d["to"] == s2["name"] for d in dependencies):
                            dependencies.append({
                                "from": s1["name"],
                                "to": s2["name"],
                                "type": "http",
                                "endpoint": "/api/analyze"
                            })

        return services, dependencies, file_mappings

