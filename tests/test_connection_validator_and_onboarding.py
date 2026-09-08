import sys
import unittest
from pathlib import Path

# Ensure backend is on sys.path
backend_dir = str(Path(__file__).parent.parent / "backend")
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from services.connection_validator import ConnectionValidator
from services.repo_onboarding import RepoOnboarder


class TestConnectionValidator(unittest.TestCase):

    def test_extract_routes(self):
        sample_code = """
from fastapi import FastAPI
app = FastAPI()

@app.get("/users/{user_id}")
def get_user(user_id: int):
    pass

@app.post("/checkout")
def checkout():
    pass
"""
        routes = ConnectionValidator.extract_routes_from_code(sample_code)
        self.assertIn("/users/{user_id}", routes)
        self.assertIn("/checkout", routes)

    def test_detect_404_and_port_mismatch(self):
        services = [
            {"name": "user-service", "port": 8001, "url": "http://user-service:8001"},
            {"name": "order-service", "port": 8002, "url": "http://order-service:8002"},
        ]

        # order-service calls a non-existent route and wrong port on user-service
        user_code = """
@app.get("/users/{user_id}")
def get_user(user_id: int): pass
"""
        order_code = """
import httpx
# 1. 404 dead endpoint
resp1 = httpx.get("http://user-service:8001/unknown/endpoint")
# 2. Port mismatch (calls 8005 instead of 8001)
resp2 = httpx.get("http://user-service:8005/users/123")
# 3. Unresolved host
resp3 = httpx.get("http://phantom-service:9000/api")
"""
        service_files = {
            "user-service": {"main.py": user_code},
            "order-service": {"main.py": order_code},
        }

        bugs = ConnectionValidator.validate_topology(services, service_files)
        bug_types = [b.bug_type for b in bugs]

        self.assertIn("ENDPOINT_NOT_FOUND_404", bug_types)
        self.assertIn("PORT_MISMATCH", bug_types)
        self.assertIn("UNRESOLVED_SERVICE_HOST", bug_types)

    def test_detect_localhost_container_networking_bug(self):
        services = [
            {"name": "user-service", "port": 8001, "url": "http://user-service:8001"},
            {"name": "order-service", "port": 8002, "url": "http://order-service:8002"},
        ]
        # order-service calls user-service via http://localhost:8001 which is invalid inside Docker networks
        order_code = """
import requests
resp = requests.get("http://localhost:8001/users/42")
"""
        service_files = {
            "order-service": {"api.py": order_code},
        }

        bugs = ConnectionValidator.validate_topology(services, service_files)
        self.assertEqual(len(bugs), 1)
        self.assertEqual(bugs[0].bug_type, "UNRESOLVED_SERVICE_HOST")
        self.assertEqual(bugs[0].severity, "CRITICAL")
        self.assertIn("localhost", bugs[0].description)
        self.assertIn("user-service", bugs[0].suggestion)

    def test_ignore_cors_whitelists_and_unknown_files(self):
        services = [
            {"name": "user-service", "port": 8001, "url": "http://user-service:8001"},
        ]
        # CORS whitelist array in config
        config_code = """
ALLOWED_ORIGINS = ["http://localhost:5173", "http://localhost:3000"]
"""
        service_files = {
            "unknown": {"backend/core/config.py": config_code},
        }

        bugs = ConnectionValidator.validate_topology(services, service_files)
        self.assertEqual(len(bugs), 0)


class TestRepoOnboarder(unittest.TestCase):

    def test_parse_compose(self):
        sample_compose = """
version: '3.8'
services:
  auth-service:
    build:
      context: ./services/auth
    ports:
      - "8010:8010"
  billing-service:
    build:
      context: ./services/billing
    ports:
      - "8020:8020"
    depends_on:
      - auth-service
  redis:
    image: redis:alpine
"""
        onboarder = RepoOnboarder()
        services, deps, file_maps = onboarder._parse_compose(sample_compose)

        service_names = [s["name"] for s in services]
        self.assertIn("auth-service", service_names)
        self.assertIn("billing-service", service_names)
        self.assertNotIn("redis", service_names)  # Infra filtered out

        # Check port
        auth_svc = next(s for s in services if s["name"] == "auth-service")
        self.assertEqual(auth_svc["port"], 8010)

        # Check dependency
        self.assertEqual(len(deps), 1)
        self.assertEqual(deps[0]["from"], "billing-service")
        self.assertEqual(deps[0]["to"], "auth-service")

        # Check file mapping
        self.assertEqual(file_maps.get("services/auth"), "auth-service")


if __name__ == "__main__":
    unittest.main()
