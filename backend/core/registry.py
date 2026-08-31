import json
import os
from pathlib import Path
from typing import Dict, List, Any

REGISTRY_FILE = Path(__file__).parent.parent / "data" / "registry.json"

DEFAULT_REGISTRY = {
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
        }
    ],
    "dependencies": [
        {"from": "order-service", "to": "user-service", "type": "http", "endpoint": "/users/{user_id}"},
        {"from": "payment-service", "to": "order-service", "type": "http", "endpoint": "/orders/{order_id}"},
        {"from": "notification-service", "to": "order-service", "type": "http", "endpoint": "/orders/{order_id}"},
        {"from": "notification-service", "to": "payment-service", "type": "http", "endpoint": "/payments/{payment_id}"},
    ],
    "file_mappings": {
        "services/user_service": "user-service",
        "services/order_service": "order-service",
        "services/payment_service": "payment-service",
        "services/notification_service": "notification-service",
    }
}

class RegistryManager:
    @staticmethod
    def load() -> Dict[str, Any]:
        if REGISTRY_FILE.exists():
            try:
                with open(REGISTRY_FILE, "r") as f:
                    return json.load(f)
            except Exception:
                pass
        return DEFAULT_REGISTRY.copy()

    @staticmethod
    def save(data: Dict[str, Any]):
        REGISTRY_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(REGISTRY_FILE, "w") as f:
            json.dump(data, f, indent=2)

    @classmethod
    def get_services(cls) -> List[Dict[str, Any]]:
        return cls.load().get("services", [])

    @classmethod
    def get_dependencies(cls) -> List[Dict[str, Any]]:
        return cls.load().get("dependencies", [])

    @classmethod
    def get_file_mappings(cls) -> Dict[str, str]:
        return cls.load().get("file_mappings", {})

    @classmethod
    def add_service(cls, service: Dict[str, Any]):
        data = cls.load()
        # Remove existing if any
        data["services"] = [s for s in data.get("services", []) if s["name"] != service["name"]]
        data["services"].append(service)
        cls.save(data)

    @classmethod
    def add_dependency(cls, from_svc: str, to_svc: str, dep_type: str = "http", endpoint: str = ""):
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
        data = cls.load()
        if "file_mappings" not in data:
            data["file_mappings"] = {}
        data["file_mappings"][prefix] = service_name
        cls.save(data)

    @classmethod
    def clear(cls):
        cls.save({"services": [], "dependencies": [], "file_mappings": {}})

registry_manager = RegistryManager()
