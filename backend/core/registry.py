import copy
import json
import os
import re
import threading
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)

REGISTRY_FILE = Path(__file__).parent.parent / "data" / "registry.json"

DEFAULT_REGISTRY: Dict[str, Any] = {
    # The bundled graph represents this repository's local demo fleet.  This
    # context is deliberately persisted alongside the topology: a topology is
    # only meaningful for the repository from which it was imported.
    "project": {
        "repository_key": "github:kartick026/mdt",
        "repo_url": "https://github.com/kartick026/MDT",
        "branch": "main",
        "source": "local_demo",
    },
    "services": [
        {
            "name": "user-service",
            "port": 8001,
            "url": "http://user-service:8001",
            "language": "python",
            "description": "User management — CRUD for user accounts",
        },
        {
            "name": "order-service",
            "port": 8002,
            "url": "http://order-service:8002",
            "language": "python",
            "description": "Order processing — depends on user-service",
        },
        {
            "name": "payment-service",
            "port": 8003,
            "url": "http://payment-service:8003",
            "language": "python",
            "description": "Payment processing — depends on order-service",
        },
        {
            "name": "notification-service",
            "port": 8004,
            "url": "http://notification-service:8004",
            "language": "python",
            "description": "Notifications — depends on order-service and payment-service",
        },
        {
            "name": "inventory-service",
            "port": 9999,
            "url": "http://inventory-service:9999",
            "language": "python",
            "description": "Legacy inventory service — unresolvable host (broken link)",
            "is_broken": True,
            "status": "offline",
            "risk_level": "CRITICAL",
            "risk_score": 90.0,
        }
    ],
    "dependencies": [
        # Intentional local-demo anti-patterns.
        {"from": "order-service", "to": "user-service", "type": "http", "endpoint": "/users/{user_id}"},
        {"from": "notification-service", "to": "order-service", "type": "http", "endpoint": "/orders/{order_id}"},
        {"from": "user-service", "to": "order-service", "type": "http", "endpoint": "/orders/status"},
        {"from": "order-service", "to": "order-service", "type": "http", "endpoint": "/internal/order-sync"},
        {"from": "order-service", "to": "notification-service", "type": "http", "endpoint": "/notifications/order"},
        {"from": "notification-service", "to": "user-service", "type": "http", "endpoint": "/users/{user_id}"},
        {"from": "notification-service", "to": "notification-service", "type": "http", "endpoint": "/internal/dispatch"},
        # Broken link connection to unresolvable host
        {"from": "order-service", "to": "inventory-service", "type": "http", "endpoint": "/api/v1/inventory/reserve"},
        # Shared database connection targets
        {"from": "user-service", "to": "local-demo-postgres", "type": "postgresql", "endpoint": "postgresql://local-demo-postgres:5432/users"},
        {"from": "notification-service", "to": "local-demo-postgres", "type": "postgresql", "endpoint": "postgresql://local-demo-postgres:5432/notifications"},
    ],
    "connection_bugs": [
        {
            "source_service": "order-service",
            "target_service": "inventory-service",
            "target_url": "http://inventory-service:9999/api/v1/inventory/reserve",
            "bug_type": "UNRESOLVED_SERVICE_HOST",
            "severity": "CRITICAL",
            "description": "order-service calls unresolvable host 'inventory-service:9999' on endpoint '/api/v1/inventory/reserve' (Dead Host / Broken Link)",
            "file_path": "services/order_service/main.py",
            "line_number": 65,
            "suggestion": "Deploy inventory-service or remove dead dependency call",
        }
    ],
    "file_mappings": {
        "services/user_service": "user-service",
        "services/order_service": "order-service",
        "services/payment_service": "payment-service",
        "services/notification_service": "notification-service",
    }
}

# Historical data belongs to the same four-service local demo fleet.  It is
# required for the two trend detectors and is seeded whenever that fleet is
# restored or started, rather than creating a separate lab topology.
LOCAL_DEMO_SMELL_HISTORY: Dict[str, Any] = {
    "dependency_snapshots": [
        {
            "signature": "local-demo-baseline-v1",
            "edges": [
                "order-service->user-service",
                "payment-service->order-service",
                "notification-service->order-service",
                "notification-service->payment-service",
            ],
            "created_at": "2025-01-01T00:00:00+00:00",
        },
        {
            "signature": "local-demo-current-v2",
            "edges": [
                f"{edge['from']}->{edge['to']}"
                for edge in DEFAULT_REGISTRY["dependencies"]
            ],
            "created_at": "2025-01-02T00:00:00+00:00",
        },
    ],
    "api_snapshots": [
        {
            "service": "order-service",
            "signature": "local-demo-order-api-v1",
            "endpoints": ["GET /health", "GET /orders/legacy", "POST /orders"],
            "created_at": "2025-01-01T00:00:00+00:00",
        },
        {
            "service": "order-service",
            "signature": "local-demo-order-api-v2",
            "endpoints": ["GET /health", "GET /orders/{order_id}", "POST /orders"],
            "created_at": "2025-01-02T00:00:00+00:00",
        },
    ],
}


class RegistryManager:
    """
    Central microservice registry with thread-safe in-memory caching and atomic file persistence.
    """
    _cache: Optional[Dict[str, Any]] = None
    _lock = threading.Lock()

    @classmethod
    def load(cls) -> Dict[str, Any]:
        with cls._lock:
            if cls._cache is not None:
                return copy.deepcopy(cls._cache)

            if REGISTRY_FILE.exists():
                try:
                    with open(REGISTRY_FILE, "r", encoding="utf-8") as f:
                        cls._cache = json.load(f)
                        return copy.deepcopy(cls._cache)
                except Exception as exc:
                    logger.warning("Failed to load registry file %s: %s. Using default.", REGISTRY_FILE, exc)

            cls._cache = copy.deepcopy(DEFAULT_REGISTRY)
            return copy.deepcopy(cls._cache)

    @classmethod
    def save(cls, data: Dict[str, Any]):
        with cls._lock:
            cls._cache = copy.deepcopy(data)
            REGISTRY_FILE.parent.mkdir(parents=True, exist_ok=True)
            temp_file = REGISTRY_FILE.with_suffix(".tmp")
            try:
                with open(temp_file, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
                # Atomic rename on Windows/POSIX
                if os.path.exists(REGISTRY_FILE):
                    os.replace(temp_file, REGISTRY_FILE)
                else:
                    temp_file.rename(REGISTRY_FILE)
            except Exception as exc:
                logger.error("Failed to save registry to file: %s", exc)
                if temp_file.exists():
                    try:
                        temp_file.unlink()
                    except Exception:
                        pass

    @classmethod
    def reload(cls) -> Dict[str, Any]:
        """Force flush cache and reload from disk."""
        with cls._lock:
            cls._cache = None
        return cls.load()

    @classmethod
    def get_services(cls) -> List[Dict[str, Any]]:
        return cls.load().get("services", [])

    @classmethod
    def get_dependencies(cls) -> List[Dict[str, Any]]:
        return cls.load().get("dependencies", [])

    @classmethod
    def get_file_mappings(cls) -> Dict[str, str]:
        return cls.load().get("file_mappings", {})

    @staticmethod
    def repository_key(repo_url: str) -> str:
        """Return a stable, comparison-safe identity for a repository URL.

        GitHub's HTTPS and SSH URL forms refer to the same repository, so a
        trailing ``.git``, slash, casing, or transport must not create a new
        architecture context.  For local paths and other Git hosts we retain a
        normalized path/URL rather than guessing an unrelated identity.
        """
        value = (repo_url or "").strip().replace("\\", "/")
        value = value.rstrip("/")
        if value.lower().endswith(".git"):
            value = value[:-4]

        github_match = re.search(r"github\.com[:/]([^/]+)/([^/]+)$", value, re.IGNORECASE)
        if github_match:
            owner, repo = github_match.groups()
            return f"github:{owner}/{repo}".lower()

        return value.lower()

    @classmethod
    def get_project_context(cls) -> Dict[str, Any]:
        """Return the repository that owns the currently active topology."""
        data = cls.load()
        context = data.get("project")
        if isinstance(context, dict) and context.get("repository_key"):
            return json.loads(json.dumps(context))

        # Registries created before project scoping existed can still be the
        # bundled demo graph.  Preserve that expected local workflow without
        # treating an unknown imported graph as safe for every repository.
        default_names = {service["name"] for service in DEFAULT_REGISTRY["services"]}
        current_names = {service.get("name") for service in data.get("services", [])}
        if current_names == default_names:
            return json.loads(json.dumps(DEFAULT_REGISTRY["project"]))
        return {}

    @classmethod
    def set_project_context(cls, repo_url: str, branch: str = "main", source: str = "repository"):
        """Associate the active registry topology with one repository."""
        data = cls.load()
        data["project"] = {
            "repository_key": cls.repository_key(repo_url),
            "repo_url": repo_url.strip(),
            "branch": (branch or "main").strip() or "main",
            "source": source,
        }
        cls.save(data)

    @classmethod
    def validate_service(cls, service: Dict[str, Any]) -> None:
        """Validate service schema rules."""
        name = service.get("name")
        if not name or not isinstance(name, str):
            raise ValueError("Service must have a non-empty string 'name'")
        clean_name = name.strip()
        if not re.match(r"^[a-zA-Z0-9_\-]+$", clean_name):
            raise ValueError(f"Invalid service name '{name}': only alphanumeric, '-' and '_' allowed")

        port = service.get("port")
        if port is not None:
            try:
                port_int = int(port)
                if not (1 <= port_int <= 65535):
                    raise ValueError(f"Port {port} out of range [1, 65535]")
            except (TypeError, ValueError):
                raise ValueError(f"Port must be an integer, got '{port}'")

    @classmethod
    def add_service(cls, service: Dict[str, Any]):
        cls.validate_service(service)
        data = cls.load()
        # Remove existing if any
        data["services"] = [s for s in data.get("services", []) if s["name"] != service["name"]]
        data["services"].append(service)
        cls.save(data)

    @classmethod
    def add_dependency(cls, from_svc: str, to_svc: str, dep_type: str = "http", endpoint: str = ""):
        if not from_svc or not to_svc:
            raise ValueError("Both 'from' and 'to' service names are required")
        data = cls.load()
        deps = data.get("dependencies", [])
        # Remove duplicate edge
        deps = [d for d in deps if not (d["from"] == from_svc and d["to"] == to_svc)]
        deps.append({
            "from": from_svc,
            "to": to_svc,
            "type": dep_type,
            "endpoint": endpoint
        })
        data["dependencies"] = deps
        cls.save(data)

    @classmethod
    def add_file_mapping(cls, prefix: str, service_name: str):
        if prefix is None or not service_name or not service_name.strip():
            raise ValueError("Both prefix and service_name are required")
        data = cls.load()
        if "file_mappings" not in data:
            data["file_mappings"] = {}
        data["file_mappings"][prefix.strip()] = service_name.strip()
        cls.save(data)

    @classmethod
    def get_connection_bugs(cls) -> List[Dict[str, Any]]:
        return cls.load().get("connection_bugs", [])

    @classmethod
    def set_connection_bugs(cls, bugs: List[Dict[str, Any]]):
        data = cls.load()
        data["connection_bugs"] = bugs
        cls.save(data)

    @classmethod
    def clear(cls):
        cls.save({
            "project": {},
            "services": [],
            "dependencies": [],
            "file_mappings": {},
            "connection_bugs": [],
        })

    @classmethod
    def reset_to_default(cls):
        """Reset registry back to DEFAULT_REGISTRY."""
        cls.save(json.loads(json.dumps(DEFAULT_REGISTRY)))

    @classmethod
    def get_local_demo_smell_history(cls) -> Dict[str, Any]:
        """Return immutable-style copies of the local fleet's drift history."""
        return json.loads(json.dumps(LOCAL_DEMO_SMELL_HISTORY))


class ServiceRegistry:
    """Helper wrapper around RegistryManager providing dictionary-based access."""
    def list_services(self) -> Dict[str, Dict[str, Any]]:
        services = RegistryManager.get_services()
        return {s["name"]: s for s in services if "name" in s}

    def get_service(self, name: str) -> Optional[Dict[str, Any]]:
        services = self.list_services()
        return services.get(name)


registry_manager = RegistryManager()
