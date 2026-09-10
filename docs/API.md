# Microservice Drift Tracker (MDT) — API Documentation

This document describes the REST API exposed by the MDT backend server (`http://localhost:8000`).

---

## 1. System Health & Observability

### `GET /health/`
Checks basic backend responsiveness and runtime environment.

### `GET /health/detailed`
Deep component diagnostics verifying:
- **Neo4j**: Live cluster/Aura connection or mock mode fallback
- **ChromaDB**: Local persistent vector index and indexed chunk count
- **LLM Engine**: Readiness status and model configuration
- **GitHub**: Integration status (Personal Access Token / GitHub App)

#### Global Request Tracing Headers
Every HTTP response returns tracing and latency metrics:
- `X-Request-ID`: Unique UUID tracking the request lifecycle across distributed components.
- `X-Response-Time-MS`: Precise elapsed execution latency in milliseconds.

---

## 2. Authentication & Authorization

### `POST /auth/login`
Authenticates user with username and password, returning an encrypted HS256 JWT access token.

#### Request Body
```json
{
  "username": "admin",
  "password": "admin123"
}
```

#### Response `200 OK`
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 86400,
  "user": {
    "username": "admin",
    "role": "admin",
    "is_active": true
  }
}
```

### `POST /auth/token`
Standard OAuth2 form-urlencoded endpoint (`username`, `password`) providing compatibility with OpenAPI / Swagger UI.

### `GET /auth/me`
Retrieves identity and role information for the currently authenticated bearer session.
*Requires `Authorization: Bearer <token>`.*

### `POST /auth/refresh`
Issues a fresh JWT token extending an active user session.
*Requires `Authorization: Bearer <token>`.*

---

## 3. Impact Analysis Pipeline

### `POST /analysis/analyze`
Executes Hierarchical Microservice Drift Analysis (HMDA) against a commit or branch ref. Automatically resolves branch references (`main`, `master`, `HEAD`, tags) to 40-character commit hashes and auto-detects changed files from the unified diff when not explicitly provided.

#### Request Body
```json
{
  "repo_url": "https://github.com/kartick026/MDT",
  "commit_sha": "main",
  "changed_files": []
}
```

#### Response `200 OK`
```json
{
  "status": "success",
  "commit": "0f1c420",
  "commit_sha": "0f1c4204c2f22d97d27b7a847b2fe057f36afd42",
  "branch_ref": "main",
  "repo_url": "https://github.com/kartick026/MDT",
  "risk_score": 75.0,
  "severity": "critical",
  "impacted_services": ["order-service", "user-service"],
  "confidence": 0.85,
  "explanation": "High risk detected due to API contract alterations in order-service...",
  "suggested_fixes": [
    "Deploy a backward-compatible facade for order-service before retiring routes"
  ],
  "connection_bugs": [],
  "affected_files": [
    {
      "path": "backend/api/registry.py",
      "change_type": "added",
      "lines_changed": 64,
      "additions": 64,
      "deletions": 0
    }
  ],
  "score_breakdown": {
    "file_count": 14,
    "impacted_services": 2,
    "confidence": 85,
    "connection_bugs": 0
  }
}
```

### `POST /analysis/preview-fix`
Executes a non-destructive What-If remediation simulation in an isolated Neo4j transaction sandbox. Measures before vs. after risk scores and resolved architectural smells without modifying production data.

#### Request Body
```json
{
  "edits": [
    {
      "action": "add_node",
      "from_service": "order-service_facade"
    },
    {
      "action": "add_edge",
      "from_service": "order-service_facade",
      "to_service": "order-service"
    }
  ],
  "baseline_risk_score": 75.0
}
```

#### Response `200 OK`
```json
{
  "success": true,
  "baseline_risk_score": 75.0,
  "projected_risk_score": 45.0,
  "risk_reduction": 30.0,
  "before_smell_count": 4,
  "after_smell_count": 2,
  "resolved_smells": [
    {
      "type": "Isolated Service",
      "count_before": 2,
      "count_after": 1,
      "resolved": 1
    }
  ],
  "applied_edits": 2
}
```

### `GET /analysis/history`
Retrieves paginated historical impact analyses from the session audit log.

#### Query Parameters
- `limit` *(int, default=20)*: Maximum items to return.
- `service` *(string, optional)*: Filter by impacted service name.

#### Response `200 OK`
```json
{
  "analyses": [
    {
      "commit": "0f1c420",
      "commit_sha": "0f1c4204c2f22d97d27b7a847b2fe057f36afd42",
      "risk_score": 75.0,
      "severity": "critical",
      "impacted_services": ["order-service", "user-service"],
      "timestamp": "2026-09-10T05:07:19Z",
      "changed_files": ["backend/api/registry.py"]
    }
  ],
  "total": 1,
  "limit": 20,
  "service_filter": null
}
```

---

## 4. Microservice Registry, Topology & Smells

### `POST /api/registry/import`
Discovers and models microservice architecture from arbitrary GitHub repositories. Parses `docker-compose.yml`, `render.yaml`, or polyglot monorepo directories (`backend/`, `frontend/`, `services/*`).

#### Request Body
```json
{
  "repo_url": "https://github.com/RahulNatesan/AI-Disease-Prediction.git",
  "branch": "main"
}
```

#### Response `200 OK`
```json
{
  "status": "success",
  "discovered_services": [
    {
      "name": "disease-prediction-api",
      "port": 8000,
      "language": "python",
      "routes": ["/health", "/api/analyze"]
    },
    {
      "name": "frontend",
      "port": 3000,
      "language": "javascript",
      "routes": ["/"]
    }
  ],
  "discovered_dependencies": [
    {
      "from": "frontend",
      "to": "disease-prediction-api",
      "endpoint": "/api/analyze"
    }
  ],
  "baseline_risk_score": 53.0
}
```

### `GET /services/`
Lists all registered microservices enriched with live `/health` check ping status and discovered OpenAPI route counts.

### `GET /services/graph`
Returns the active microservice dependency graph formatted for visual rendering, with node risk levels and broken link flags.

#### Response `200 OK`
```json
{
  "nodes": [
    {
      "id": "order-service",
      "label": "Order Service",
      "risk_level": "CRITICAL",
      "risk_score": 75.0,
      "port": 8002
    }
  ],
  "edges": [
    {
      "from": "order-service",
      "to": "user-service",
      "type": "http",
      "has_bug": false
    }
  ]
}
```

### `GET /services/smells`
Evaluates the graph and snapshot registry across the **10 architectural smell detectors**, returning severity, affected services, and Cypher path evidence:
1. `Circular Dependency` (`CRITICAL`)
2. `God / Bottleneck Service` (`HIGH`)
3. `High Coupling` (`MEDIUM`)
4. `Dead / Isolated Service` (`LOW`)
5. `Dependency Explosion` (`HIGH`)
6. `API Instability` (`HIGH` / `MEDIUM`)
7. `Shared Database` (`HIGH`)
8. `Chatty Communication` (`MEDIUM`)
9. `Missing Circuit Breaker` (`MEDIUM`)
10. `Hub-and-Spoke Centralization` (`HIGH`)

---

## 5. GitHub Webhook Ingestion

### `POST /webhook/github`
Receives push and pull request webhook payloads from GitHub with HMAC-SHA256 signature verification and IP rate-limiting.

#### Headers
- `X-GitHub-Event`: Event name (e.g., `push`, `pull_request`, `ping`).
- `X-Hub-Signature-256`: `sha256=<hex_hmac>`.

#### Response `200 OK`
```json
{
  "status": "success",
  "message": "Push event processed for commit a1b2c3d",
  "commit_sha": "a1b2c3d4e5f67890"
}
```
