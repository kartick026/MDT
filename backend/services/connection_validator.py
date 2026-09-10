import re
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Set

logger = logging.getLogger(__name__)

@dataclass
class ConnectionBug:
    source_service: str
    target_service: Optional[str]
    target_url: str
    bug_type: str        # ENDPOINT_NOT_FOUND_404 | UNRESOLVED_SERVICE_HOST | PORT_MISMATCH | PROTOCOL_ERROR
    severity: str        # HIGH | CRITICAL | MEDIUM
    description: str
    file_path: str
    line_number: int
    suggestion: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_service": self.source_service,
            "target_service": self.target_service,
            "target_url": self.target_url,
            "bug_type": self.bug_type,
            "severity": self.severity,
            "description": self.description,
            "file_path": self.file_path,
            "line_number": self.line_number,
            "suggestion": self.suggestion,
        }

class ConnectionValidator:
    """
    Validates inter-service HTTP/REST communication contracts across microservices.
    Identifies 404 dead endpoints, unresolved service hosts, and port mismatches.
    """

    # Patterns to match route definitions in Python, JS/TS, Go, Ruby, PHP, C#, Rust, Kotlin
    ROUTE_PATTERNS = [
        # FastAPI / Flask: @app.get('/users/{id}'), @router.post('/orders')
        re.compile(r"@(app|router|api_router)\.(get|post|put|delete|patch)\s*\(\s*['\"]([^'\"\?]+)['\"]", re.IGNORECASE),
        # Express.js: app.get('/users/:id', ...), router.post('/orders', ...)
        re.compile(r"\b(app|router)\.(get|post|put|delete|patch)\s*\(\s*['\"]([^'\"\?]+)['\"]", re.IGNORECASE),
        # Spring Boot: @GetMapping('/users/{id}'), @PostMapping('/orders')
        re.compile(r"@(Get|Post|Put|Delete|Patch)Mapping\s*\(\s*['\"]([^'\"\?]+)['\"]", re.IGNORECASE),
        # Go Gin / net/http: r.GET("/api/v1/users", ...), http.HandleFunc("/healthz", ...)
        re.compile(r"\b(?:r|router|engine|http)\.(?:GET|POST|PUT|DELETE|PATCH|HandleFunc|Handle)\s*\(\s*['\"]([^'\"\?]+)['\"]"),
        # Ruby on Rails: get '/products', to: ...
        re.compile(r"^\s*(?:get|post|put|patch|delete)\s+['\"]([^'\"\?]+)['\"]", re.IGNORECASE),
        # PHP Laravel: Route::get('/api/customers', ...), $app->post('/api/invoices', ...)
        re.compile(r"(?:Route::|\$app->|\$router->)(?:get|post|put|patch|delete)\s*\(\s*['\"]([^'\"\?]+)['\"]", re.IGNORECASE),
        # C# ASP.NET Core & Minimal API: [HttpGet("/api/accounts")], app.MapGet("/status", ...)
        re.compile(r"\[Http(?:Get|Post|Put|Patch|Delete)\s*\(\s*['\"]([^'\"\?]+)['\"]", re.IGNORECASE),
        re.compile(r"\b(?:app|endpoints)\.Map(?:Get|Post|Put|Patch|Delete)\s*\(\s*['\"]([^'\"\?]+)['\"]", re.IGNORECASE),
        # Rust Actix & Axum: #[get("/inventory")], .route("/ping", get(...))
        re.compile(r"#\[(?:get|post|put|patch|delete)\s*\(\s*['\"]([^'\"\?]+)['\"]", re.IGNORECASE),
        re.compile(r"\.route\s*\(\s*['\"]([^'\"\?]+)['\"]", re.IGNORECASE),
        # Kotlin Ktor: get("/api/catalog") { ... }
        re.compile(r"\b(?:get|post|put|patch|delete)\s*\(\s*['\"]([^'\"\?]+)['\"]\s*\)", re.IGNORECASE),
    ]


    # Patterns to match outbound HTTP calls / URLs: group(1)=host, group(2)=port, group(3)=path
    URL_CALL_PATTERNS = [
        re.compile(r"https?://([a-zA-Z0-9_\-\.]+)(?::(\d+))?(/[^'\"\s\)\,\`\<\>\{\}]*)?", re.IGNORECASE),
    ]

    @classmethod
    def extract_routes_from_code(cls, file_content: str) -> List[str]:
        """Extract all exposed API route paths from a source file."""
        routes = []
        for line in file_content.splitlines():
            for pattern in cls.ROUTE_PATTERNS:
                match = pattern.search(line)
                if match:
                    path = match.group(match.lastindex).strip()
                    if path and not path.startswith("/docs") and not path.startswith("/openapi"):
                        routes.append(cls._normalize_path(path))
        return list(dict.fromkeys(routes))

    @classmethod
    def extract_outbound_calls(cls, file_content: str, file_path: str = "") -> List[Dict[str, Any]]:
        """Extract outbound URLs and target endpoints from a source file."""
        calls = []
        for idx, line in enumerate(file_content.splitlines(), start=1):
            trimmed = line.strip()
            if trimmed.startswith("#") or trimmed.startswith("//"):
                continue

            # Ignore CORS origin whitelists, allowed hosts lists, and configuration arrays
            if re.search(r"\b(allowed_origins|allow_origins|origins|cors|whitelist|allowed_hosts)\b", trimmed, re.IGNORECASE):
                continue

            for pattern in cls.URL_CALL_PATTERNS:
                for match in pattern.finditer(line):
                    groups = match.groups()
                    host = groups[0]
                    port = int(groups[1]) if len(groups) > 1 and groups[1] else None
                    raw_path = groups[2] if len(groups) > 2 and groups[2] else "/"
                    clean_path = cls._clean_call_path(raw_path)

                    calls.append({
                        "host": host,
                        "port": port,
                        "path": clean_path,
                        "raw_url": match.group(0),
                        "line_number": idx,
                        "line_content": trimmed,
                        "file_path": file_path
                    })
        return calls

    @classmethod
    def validate_topology(
        cls,
        services: List[Dict[str, Any]],
        service_files: Dict[str, Dict[str, str]]
    ) -> List[ConnectionBug]:
        """
        Validate connections across all microservices.
        
        Args:
            services: list of registered service dicts (name, port, etc.)
            service_files: dict of {service_name: {file_path: file_content}}
        """
        service_routes: Dict[str, Set[str]] = {}
        service_info: Dict[str, Dict[str, Any]] = {}

        for svc in services:
            sname = svc["name"]
            service_info[sname] = svc
            service_routes[sname] = set()

        for sname, files in service_files.items():
            if sname not in service_routes:
                service_routes[sname] = set()
            for fpath, content in files.items():
                routes = cls.extract_routes_from_code(content)
                service_routes[sname].update(routes)

        bugs: List[ConnectionBug] = []

        for source_svc, files in service_files.items():
            if source_svc == "unknown":
                # Files not belonging to any recognized microservice (e.g. backend config, scripts)
                continue
            for fpath, content in files.items():
                calls = cls.extract_outbound_calls(content, file_path=fpath)
                for call in calls:
                    target_host = call["host"]
                    target_port = call["port"]
                    call_path = call["path"]

                    if not cls._is_internal_service_host(target_host, list(service_info.keys())):
                        continue

                    is_localhost = target_host.lower() in ("localhost", "127.0.0.1", "0.0.0.0")
                    target_svc_name = cls._resolve_host_to_service(target_host, target_port, service_info)

                    if is_localhost:
                        target_svc_obj = service_info.get(target_svc_name, {}) if target_svc_name else {}
                        resolved_port = target_port or target_svc_obj.get("port", 8000)
                        suggestion = (
                            f"Replace '{target_host}' with container service DNS '{target_svc_name}' "
                            f"(e.g., http://{target_svc_name}:{resolved_port}) so requests route through the Docker container network."
                            if target_svc_name else
                            f"Replace '{target_host}' with the target container service name (e.g., http://<service-name>:<port>)."
                        )
                        bugs.append(ConnectionBug(
                            source_service=source_svc,
                            target_service=target_svc_name,
                            target_url=call["raw_url"],
                            bug_type="UNRESOLVED_SERVICE_HOST",
                            severity="CRITICAL",
                            description=(
                                f"Service '{source_svc}' makes an HTTP call to '{target_host}' on port {target_port}. "
                                f"In Docker container networking, 'localhost' points to the container's internal loopback interface "
                                f"and cannot reach {target_svc_name or 'other services'}."
                            ),
                            file_path=fpath,
                            line_number=call["line_number"],
                            suggestion=suggestion,
                        ))
                        continue

                    if not target_svc_name:
                        bugs.append(ConnectionBug(
                            source_service=source_svc,
                            target_service=None,
                            target_url=call["raw_url"],
                            bug_type="UNRESOLVED_SERVICE_HOST",
                            severity="CRITICAL",
                            description=f"Service '{source_svc}' makes an HTTP call to unknown service '{target_host}'.",
                            file_path=fpath,
                            line_number=call["line_number"],
                            suggestion=f"Verify '{target_host}' is registered in the architecture and running in the network.",
                        ))
                        continue

                    target_svc = service_info.get(target_svc_name, {})

                    expected_port = target_svc.get("port")
                    if target_port and expected_port and target_port != expected_port:
                        bugs.append(ConnectionBug(
                            source_service=source_svc,
                            target_service=target_svc_name,
                            target_url=call["raw_url"],
                            bug_type="PORT_MISMATCH",
                            severity="HIGH",
                            description=f"Port mismatch: '{source_svc}' calls {target_svc_name} on port {target_port}, but {target_svc_name} listens on port {expected_port}.",
                            file_path=fpath,
                            line_number=call["line_number"],
                            suggestion=f"Update port in '{fpath}:{call['line_number']}' to port {expected_port}.",
                        ))

                    known_routes = service_routes.get(target_svc_name, set())
                    if known_routes and not cls._matches_any_route(call_path, known_routes):
                        bugs.append(ConnectionBug(
                            source_service=source_svc,
                            target_service=target_svc_name,
                            target_url=call["raw_url"],
                            bug_type="ENDPOINT_NOT_FOUND_404",
                            severity="HIGH",
                            description=f"Broken API contract: '{source_svc}' calls '{call_path}' on '{target_svc_name}', but this endpoint is not exposed.",
                            file_path=fpath,
                            line_number=call["line_number"],
                            suggestion=f"Available endpoints on {target_svc_name}: {', '.join(sorted(known_routes)) or 'None'}",
                        ))

        return bugs

    @classmethod
    def _normalize_path(cls, path: str) -> str:
        """Normalize /users/{id} or /users/:id to standard /users/{param}"""
        path = path.strip()
        if not path.startswith("/"):
            path = "/" + path
        path = re.sub(r":([a-zA-Z0-9_]+)", r"{\1}", path)
        if len(path) > 1 and path.endswith("/"):
            path = path[:-1]
        return path

    @classmethod
    def _clean_call_path(cls, path: str) -> str:
        """Extract clean path removing query params or trailing string quotes"""
        if "?" in path:
            path = path.split("?")[0]
        path = path.rstrip("'\"}")
        return cls._normalize_path(path)

    @classmethod
    def _matches_any_route(cls, call_path: str, known_routes: Set[str]) -> bool:
        """Check if an outbound call path matches any registered route (including param substitutions)."""
        if call_path in known_routes or call_path == "/" or call_path.startswith("/health"):
            return True

        call_parts = [p for p in call_path.strip("/").split("/") if p]

        for route in known_routes:
            route_parts = [p for p in route.strip("/").split("/") if p]
            if len(call_parts) != len(route_parts):
                continue
            
            match = True
            for cp, rp in zip(call_parts, route_parts):
                if rp.startswith("{") and rp.endswith("}"):
                    continue
                if cp != rp:
                    match = False
                    break
            if match:
                return True

        return False

    @classmethod
    def _is_internal_service_host(cls, host: str, known_services: List[str]) -> bool:
        """Filter whether a host is considered a microservice in our topology."""
        host_lower = host.lower()
        if host_lower in ("localhost", "127.0.0.1", "0.0.0.0"):
            return True
        if host_lower.endswith("-service") or host_lower.endswith("_service"):
            return True
        for s in known_services:
            if host_lower == s.lower() or host_lower.replace("-", "_") == s.lower().replace("-", "_"):
                return True
        return False

    @classmethod
    def _resolve_host_to_service(
        cls,
        host: str,
        port: Optional[int],
        service_info: Dict[str, Dict[str, Any]]
    ) -> Optional[str]:
        """Map host/port to a known registered service."""
        for sname, sdata in service_info.items():
            if host.lower() == sname.lower() or host.lower() == sname.replace("-", "_").lower():
                return sname
            if sdata.get("url") and host in sdata["url"]:
                return sname

        if host.lower() in ("localhost", "127.0.0.1") and port:
            for sname, sdata in service_info.items():
                if sdata.get("port") == port:
                    return sname

        return None
