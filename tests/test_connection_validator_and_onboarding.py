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

    def test_extract_polyglot_routes(self):
        # 1. Go Gin & net/http
        go_code = """
package main
func setupRoutes(r *gin.Engine) {
    r.GET("/api/v1/users", listUsers)
    r.POST("/api/v1/orders", createOrder)
    http.HandleFunc("/healthz", healthHandler)
}
"""
        go_routes = ConnectionValidator.extract_routes_from_code(go_code)
        self.assertIn("/api/v1/users", go_routes)
        self.assertIn("/api/v1/orders", go_routes)
        self.assertIn("/healthz", go_routes)

        # 2. Ruby on Rails
        ruby_code = """
Rails.application.routes.draw do
  get '/products', to: 'products#index'
  post '/checkout', to: 'checkout#process'
end
"""
        ruby_routes = ConnectionValidator.extract_routes_from_code(ruby_code)
        self.assertIn("/products", ruby_routes)
        self.assertIn("/checkout", ruby_routes)

        # 3. PHP Laravel
        php_code = """
<?php
Route::get('/api/customers', [CustomerController::class, 'index']);
$app->post('/api/invoices', 'InvoiceController@store');
"""
        php_routes = ConnectionValidator.extract_routes_from_code(php_code)
        self.assertIn("/api/customers", php_routes)
        self.assertIn("/api/invoices", php_routes)

        # 4. C# ASP.NET Core & Minimal API
        csharp_code = """
[ApiController]
public class UsersController : ControllerBase {
    [HttpGet("/api/accounts")]
    public IActionResult GetAccounts() => Ok();

    [HttpPost("api/payments")]
    public IActionResult Pay() => Ok();
}
app.MapGet("/status", () => "OK");
"""
        csharp_routes = ConnectionValidator.extract_routes_from_code(csharp_code)
        self.assertIn("/api/accounts", csharp_routes)
        self.assertIn("/api/payments", csharp_routes)
        self.assertIn("/status", csharp_routes)

        # 5. Rust Actix & Axum
        rust_code = """
#[get("/inventory")]
async fn get_inventory() -> impl Responder {}

#[post("/inventory/restock")]
async fn restock() -> impl Responder {}

let app = Router::new().route("/ping", get(ping_handler));
"""
        rust_routes = ConnectionValidator.extract_routes_from_code(rust_code)
        self.assertIn("/inventory", rust_routes)
        self.assertIn("/inventory/restock", rust_routes)
        self.assertIn("/ping", rust_routes)

        # 6. Kotlin Ktor
        kotlin_code = """
routing {
    get("/api/catalog") {
        call.respondText("Catalog")
    }
    post("/api/cart") {
        call.respondText("Cart")
    }
}
"""
        kotlin_routes = ConnectionValidator.extract_routes_from_code(kotlin_code)
        self.assertIn("/api/catalog", kotlin_routes)
        self.assertIn("/api/cart", kotlin_routes)

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

    def test_infer_service_language(self):
        self.assertEqual(RepoOnboarder._infer_service_language({"image": "python:3.11-slim"}), "python")
        self.assertEqual(RepoOnboarder._infer_service_language({"image": "node:18-alpine"}), "javascript")
        self.assertEqual(RepoOnboarder._infer_service_language({"image": "golang:1.21"}), "go")
        self.assertEqual(RepoOnboarder._infer_service_language({"image": "openjdk:17-jdk"}), "java")
        self.assertEqual(RepoOnboarder._infer_service_language({"image": "rust:1.75"}), "rust")
        self.assertEqual(RepoOnboarder._infer_service_language({"image": "mcr.microsoft.com/dotnet/aspnet:8.0"}), "csharp")
        self.assertEqual(RepoOnboarder._infer_service_language({"image": "ruby:3.2"}), "ruby")
        self.assertEqual(RepoOnboarder._infer_service_language({"image": "php:8.2-fpm"}), "php")

    async def _async_test_infer_from_file_tree(self):
        from unittest.mock import AsyncMock
        onboarder = RepoOnboarder()
        mock_paths = [
            "services/order-service/go.mod",
            "services/order-service/main.go",
            "services/payment-service/requirements.txt",
            "services/payment-service/main.py",
            "docs/README.md",
            "tests/test_api.py"
        ]
        onboarder.gh_client.get_repo_tree = AsyncMock(return_value=mock_paths)
        onboarder.gh_client.get_file_content = AsyncMock(return_value="http://order-service:8001/checkout")

        services, deps, file_maps = await onboarder._infer_from_file_tree("test-owner", "test-repo", "main")

        names = [s["name"] for s in services]
        self.assertIn("order-service", names)
        self.assertIn("payment-service", names)
        self.assertNotIn("docs", names)
        self.assertNotIn("tests", names)

        order_svc = next(s for s in services if s["name"] == "order-service")
        self.assertEqual(order_svc["language"], "go")

        pay_svc = next(s for s in services if s["name"] == "payment-service")
        self.assertEqual(pay_svc["language"], "python")

        self.assertEqual(file_maps.get("services/order-service"), "order-service")
        self.assertEqual(file_maps.get("services/payment-service"), "payment-service")

    def test_infer_from_file_tree(self):
        import asyncio
        asyncio.run(self._async_test_infer_from_file_tree())

    def test_inference_preserves_compose_dependencies(self):
        import asyncio
        from unittest.mock import AsyncMock

        onboarder = RepoOnboarder()
        onboarder.gh_client.get_file_content = AsyncMock(return_value="")
        services, dependencies, _ = asyncio.run(onboarder._infer_from_file_tree(
            "owner",
            "repo",
            "main",
            tree=["services/order-service/main.py"],
            existing_services=[
                {"name": "user-service", "port": 8001},
                {"name": "order-service", "port": 8002},
            ],
            existing_dependencies=[
                {"from": "order-service", "to": "user-service", "type": "http"},
            ],
            existing_mappings={"services/order-service": "order-service"},
        ))

        self.assertEqual([service["name"] for service in services], ["user-service", "order-service"])
        self.assertEqual(dependencies, [{"from": "order-service", "to": "user-service", "type": "http"}])


if __name__ == "__main__":
    unittest.main()
