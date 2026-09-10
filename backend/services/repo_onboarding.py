import asyncio
import yaml
import logging
import re
from typing import Dict, List, Any, Optional
from pathlib import Path

from core.registry import RegistryManager
from services.dependency_graph import DependencyGraph
from services.git_analyzer import GitHubAPIClient, _parse_github_url
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

        # Authenticate if possible
        dynamic_token = await GitHubAppAuth.get_installation_token_for_repo(repo_url)
        if dynamic_token:
            self.gh_client._token = dynamic_token
            self.gh_client._headers["Authorization"] = f"Bearer {dynamic_token}"

        logger.info("Importing architecture from %s/%s branch=%s", owner, repo, branch)

        # 1. Fetch file tree first to determine structure
        tree = await self.gh_client.get_repo_tree(owner, repo, branch)

        # 2. Try to find and parse docker-compose
        compose_content = None
        compose_filename = None
        for fname in COMPOSE_FILENAMES:
            if not tree or fname in tree:
                content = await self.gh_client.get_file_content(owner, repo, fname, branch)
                if content:
                    compose_content = content
                    compose_filename = fname
                    break

        # 3. Try to find and parse render.yaml
        render_content = None
        render_filename = None
        for fname in RENDER_FILENAMES:
            if not tree or fname in tree:
                content = await self.gh_client.get_file_content(owner, repo, fname, branch)
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
            branch,
            tree=tree,
            existing_services=services,
            existing_dependencies=dependencies,
            existing_mappings=file_mappings,
        )

        if not services:
            raise ValueError(f"No microservices could be discovered in {repo_url} (checked docker-compose, render.yaml, and directory structures).")

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
                entry_names = [
                    "main.py", "app.py", "server.js", "index.js",
                    "app/page.tsx", "pages/index.tsx", "pages/index.js",
                    "src/main.py", "src/app.py", "src/app.tsx", "src/index.js",
                    "src/index.ts", "src/main.go", "main.go"
                ]
                for p in tree:
                    clean_p = p.replace("\\", "/").strip("/")
                    if norm_prefix:
                        if clean_p.startswith(norm_prefix):
                            rel_p = clean_p[len(norm_prefix):]
                            if rel_p in entry_names or Path(clean_p).name in ["main.py", "app.py", "page.tsx", "index.js", "server.js"]:
                                matched_candidates.append(clean_p)
                    else:
                        if clean_p in entry_names:
                            matched_candidates.append(clean_p)

            fallback_candidates = [
                f"{prefix}/main.py",
                f"{prefix}/app.py",
                f"{prefix}/server.js",
                f"{prefix}/index.js",
                f"{prefix}/app/page.tsx",
                f"{prefix}/pages/index.tsx",
                f"{prefix}/src/main.py",
                f"{prefix}/src/index.js",
            ] if prefix else ["main.py", "app.py", "server.js", "index.js"]

            candidates = matched_candidates or fallback_candidates

            found = {}
            for cand in candidates:
                cand_clean = cand.lstrip("/")
                code = await self.gh_client.get_file_content(owner, repo, cand_clean, branch)
                if code:
                    found[cand_clean] = code
                    break  # Stop at first valid entrypoint file
            return sname, found

        results = await asyncio.gather(*(fetch_service_entrypoints(svc) for svc in services))
        for sname, found in results:
            service_files[sname] = found

        # 6. Validate connections across discovered services
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
        RegistryManager.set_project_context(repo_url, branch, source="repository")

        # 9. Persist initial architectural risk audit in Neo4j analysis history
        avg_score = round(sum(s.get("risk_score", 0) for s in services) / max(len(services), 1), 1)
        overall_severity = "CRITICAL" if any(s.get("risk_level") == "CRITICAL" for s in services) else ("HIGH" if avg_score >= 50 else ("MEDIUM" if avg_score >= 25 else "LOW"))

        try:
            await self.dep_graph.record_analysis(
                commit_sha=f"import-{branch[:12]}",
                service_names=[s["name"] for s in services],
                risk_score=avg_score,
                severity=overall_severity,
                changed_files=list(file_mappings.keys()) or ["repository_root"],
            )
        except Exception as e:
            logger.warning("Could not record initial architecture analysis: %s", e)

        return {
            "status": "success",
            "repo_url": repo_url,
            "branch": branch,
            "project_context": RegistryManager.get_project_context(),
            "compose_file": compose_filename or render_filename or "directory_inferred",
            "services_count": len(services),
            "dependencies_count": len(dependencies),
            "services": services,
            "dependencies": dependencies,
            "file_mappings": file_mappings,
            "connection_bugs": [b.to_dict() for b in connection_bugs],
        }

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
            ports = sconfig.get("ports", [])
            if ports and isinstance(ports, list):
                raw_port = str(ports[0])
                if ":" in raw_port:
                    try:
                        port = int(raw_port.split(":")[0].strip("'\""))
                    except ValueError:
                        pass
                else:
                    try:
                        port = int(raw_port)
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

