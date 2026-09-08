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

class RepoOnboarder:
    """
    Auto-discovers and imports microservice architectures from GitHub repositories.
    Parses docker-compose.yml or repository file trees to extract services, ports,
    dependencies, file mappings, and validates inter-service connections.
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

        # 1. Try to find and parse docker-compose
        compose_content = None
        compose_filename = None
        for fname in COMPOSE_FILENAMES:
            content = await self.gh_client.get_file_content(owner, repo, fname, branch)
            if content:
                compose_content = content
                compose_filename = fname
                break

        services = []
        dependencies = []
        file_mappings = {}
        service_files: Dict[str, Dict[str, str]] = {}

        if compose_content:
            logger.info("Found %s in %s/%s", compose_filename, owner, repo)
            services, dependencies, file_mappings = self._parse_compose(compose_content)
        else:
            logger.info("No docker-compose found in %s/%s, inferring from repo structure", owner, repo)
            services, dependencies, file_mappings = await self._infer_from_file_tree(owner, repo, branch)

        if not services:
            raise ValueError(f"No microservices could be discovered in {repo_url} (checked docker-compose and directories).")

        # 2. Fetch primary source code files for each service concurrently
        async def fetch_service_entrypoints(svc: Dict[str, Any]) -> tuple[str, Dict[str, str]]:
            sname = svc["name"]
            prefix = ""
            for pref, mapped_name in file_mappings.items():
                if mapped_name == sname:
                    prefix = pref.rstrip("/")
                    break

            candidates = [
                f"{prefix}/main.py",
                f"{prefix}/app.py",
                f"{prefix}/server.js",
                f"{prefix}/index.js",
                f"{prefix}/src/main.py",
                f"{prefix}/src/index.js",
            ] if prefix else ["main.py", "app.py", "server.js", "index.js"]

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

        # 3. Validate connections across discovered services
        connection_bugs = ConnectionValidator.validate_topology(services, service_files)

        # 4. Save to RegistryManager and Neo4j (Wipe previous project so architectures never mix)
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

        return {
            "status": "success",
            "repo_url": repo_url,
            "branch": branch,
            "compose_file": compose_filename,
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
                # Format: "8001:8001" or 8001
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
                "language": "python" if "py" in str(sconfig) else "unknown"
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

    async def _infer_from_file_tree(
        self, owner: str, repo: str, branch: str
    ) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, str]]:
        """Fallback when no docker-compose: inspect directory structure for service folders."""
        services = []
        dependencies = []
        file_mappings = {}

        # Default fallback to existing registry if empty
        existing = RegistryManager.get_services()
        existing_deps = RegistryManager.get_dependencies()
        existing_maps = RegistryManager.get_file_mappings()
        return existing, existing_deps, existing_maps
