# Microservice Drift Tracker (MDT)

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![FastAPI](https://img.shields.io/badge/Backend-FastAPI-009688.svg?logo=fastapi)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/Frontend-React%2018%20%2B%20Vite-61DAFB.svg?logo=react)](https://reactjs.org/)
[![Neo4j](https://img.shields.io/badge/Graph-Neo4j%205.16-008CC1.svg?logo=neo4j)](https://neo4j.com/)
[![ChromaDB](https://img.shields.io/badge/VectorDB-ChromaDB-FF6B6B.svg)](https://www.trychroma.com/)
[![Docker](https://img.shields.io/badge/Orchestration-Docker%20Compose-2496ED.svg?logo=docker)](https://www.docker.com/)

**Microservice Drift Tracker (MDT)** is an AI-assisted cross-service impact analysis and architectural governance platform. It automatically detects how code modifications in one microservice propagate through upstream and downstream callers **before deployment**, preventing cascading outages, broken endpoints, and architectural debt.

---

## Architecture Overview

```
Developer Push / PR
        │
        ▼
 GitHub Webhook / App ───► HMAC Signature Validation (RS256)
                                  │
                                  ▼
FastAPI Backend Core ────► Git Diff Analyzer & AST Inspector
                                  │
        ┌─────────────────────────┼─────────────────────────┐
        ▼                         ▼                         ▼
   Neo4j 5.16 Graph          ChromaDB Vector          HMDA Risk Engine
 (Topological Depth &      (Semantic History &      (Deterministic + AI
  Architectural Smells)     Code Context Embeddings) Scoring: 0 to 100)
        │                         │                         │
        └─────────────────────────┼─────────────────────────┘
                                  ▼
                     LLM Reasoning & Remediation
                                  │
        ┌─────────────────────────┴─────────────────────────┐
        ▼                                                   ▼
 What-If Simulation Sandbox                      Cybernetic Glass Dashboard
(Non-Destructive Rolled-back TX)              (Real-Time Blast Radius & Graph)
```

---

## Key Features

- **🚀 Resilient Multi-Manifest Architecture Ingestion:** Scan any public or private GitHub repository URL to auto-register microservices, container ports, dependency links, and file mappings from `docker-compose.yml`, `render.yaml`/`render.yml`, or polyglot monorepo directories (`backend/`, `frontend/`, `services/*`, `apps/*`). Immune to GitHub REST API 60 req/hr rate limits via automated shallow clone and `git ls-files` fallback.
- **🔌 Polyglot Connection Integrity & Broken Endpoint Checks:** AST static analysis inspects microservice HTTP client calls against live OpenAPI endpoints, flagging `[UNRESOLVED_SERVICE_HOST]`, `[PORT_MISMATCH]`, and `[ENDPOINT_MISMATCH]` errors before production deployment.
- **⚡ HMDA (Hierarchical Microservice Drift Analysis):** Proprietary multi-pillar scoring engine combining deterministic code change volumes, dependency graph traversal depth, ChromaDB semantic retrieval, and LLM reasoning into a normalized 0–100 risk score (`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`).
- **🔍 Git Ref & Branch Resolution:** Native resolution of branch names (`main`, `master`, tags, `HEAD`) to concrete 40-character commit hashes via ultra-fast `git ls-remote` (<1.5s) and commit patch parsing.
- **🧪 What-If Remediation Simulation Sandbox:** Test proposed architectural refactorings (e.g. adding circuit breakers or resilience facades) in an isolated transaction sandbox. Renders before vs. after risk score gauges and smell resolution metrics in real time with zero database side-effects.
- **⚠ 10 Architectural Smells & Anti-Pattern Detectors:** Continuous Cypher graph queries and heuristic algorithms detect 10 critical distributed anti-patterns across microservices.
- **🌐 Interactive Dependency Graph:** Visual SVG topology graph with animated directional flow lines, zoom controls, blast-radius interactive highlighting, and risk-coded service nodes.
- **📜 Analysis History & Audit Trail:** Session-wide historical log of all drift analyses with full diff breakdowns, affected files, confidence metrics, and AI explanations.
- **🔐 Enterprise JWT Authentication & RBAC:** Production-grade HS256 JWT tokens, bcrypt password hashing, role-based access control (`admin`, `engineer`), and secure mutation route protection.
- **⏱ Distributed Request Tracing & Observability:** High-resolution execution timing headers (`X-Request-ID`, `X-Response-Time-MS`), JSON structured logging, and deep component diagnostic checks (`/health/detailed`).
- **🤖 GitHub App & Webhook Automation:** Native support for GitHub Webhooks and GitHub Apps (RS256 JWT installation tokens) for automated PR status check gating and review comments.

---

## The 10 Architectural Smells Detected by MDT

MDT continuously analyzes the live Neo4j graph topology, OpenAPI contract snapshots, and dependency declarations to detect 10 distributed microservice anti-patterns:

| # | Architectural Smell | Severity | Heuristic & Detection Logic | Risk & Impact |
|---|:---|:---:|:---|:---|
| **1** | **Circular Dependency** | `CRITICAL` | Cypher cyclic path traversal: `(s:Service)-[:DEPENDS_ON*2..8]->(s)` detects closed loops between microservices (e.g., $A \rightarrow B \rightarrow C \rightarrow A$). | Causes distributed deadlocks, cascading timeout failures, tightly coupled deployment locks, and prevents isolated service testing. |
| **2** | **God / Bottleneck Service** | `HIGH` | Services with high inbound fan-in ($\ge 3$ callers) or total degree $\ge 5$ (excluding API gateways/facades). | Creates a severe single point of failure (SPOF) and scalability bottleneck; if this service degrades, multiple upstream business domains collapse. |
| **3** | **High Coupling** | `MEDIUM` | Services with excessive direct outbound dependencies ($\ge 4$ downstream targets). | Violates single responsibility and loose coupling; alterations in downstream services frequently trigger ripple breaking changes. |
| **4** | **Dead / Isolated Service** | `LOW` | Registered services with total degree $= 0$ (in-degree $= 0$ and out-degree $= 0$) in an ecosystem of $\ge 2$ services. | Represents abandoned microservices, dead code, incomplete deployment manifests, or unintegrated orphan components wasting infrastructure resources. |
| **5** | **Dependency Explosion** | `HIGH` | Commits or snapshot transitions adding $\ge 3$ new dependencies in a single change, or transitive call chains exceeding depth $\ge 5$. | Drastically expands failure blast radius, compounds network latency, and causes combinatorial deployment complexity. |
| **6** | **API Instability** | `HIGH` / `MEDIUM` | OpenAPI snapshot diff tracking deleted routes or $\ge 3$ endpoint modifications between consecutive revisions without API versioning. | Breaking contract changes without semantic versioning immediately break downstream microservice consumers and mobile/web clients. |
| **7** | **Shared Database** | `HIGH` | Multiple microservices directly reading or writing to the same database host, datastore port (`5432`, `3306`, `27017`, `6379`), or DB connection string. | Violates microservice data encapsulation; schema migrations by one service silently break other services; bypasses API validation rules. |
| **8** | **Chatty Communication** | `MEDIUM` | Mutual bidirectional calls ($A \rightarrow B$ and $B \rightarrow A$) or excessive fine-grained connections ($\ge 3$ distinct connections) between the same pair. | Excessive round-trips create ping-pong network chatter, latency amplification, and tight temporal coupling between services. |
| **9** | **Missing Circuit Breaker** | `MEDIUM` | Outbound synchronous fan-out ($\ge 3$ downstream targets) without resilience patterns, event brokers, or circuit breakers. | Fragile synchronous calls where a slow downstream service exhausts caller thread/connection pools, inducing cascading outage across the fleet. |
| **10** | **Hub-and-Spoke Centralization** | `HIGH` | A single central service connected to $\ge 60\%$ of all registered services in an ecosystem of $\ge 3$ microservices. | Monolith disguised as microservices; concentrates excessive architectural gravity into a pseudo-monolith, preventing team autonomy. |

---

## Detailed Documentation

Comprehensive documentation guides are available in the [`docs/`](./docs) directory:

- 📖 **[Architecture Guide (`docs/ARCHITECTURE.md`)](./docs/ARCHITECTURE.md):** Architectural design, HMDA scoring algorithm, 10 smell detectors, and What-If simulation mechanics.
- 📡 **[API Reference (`docs/API.md`)](./docs/API.md):** Complete OpenAPI REST endpoints, request/response models, and status codes.
- 🛠 **[Features Guide (`docs/features.md`)](./docs/features.md):** In-depth technical breakdown of each feature, mathematical scoring formulas, detection algorithms, and API schemas.
- 🚀 **[Deployment Guide (`docs/deployment.md`)](./docs/deployment.md):** Production orchestration, port allocations, Nginx reverse proxy SSL configuration, and container scaling.
- 🔐 **[GitHub App Integration (`docs/github_app.md`)](./docs/github_app.md):** Step-by-step enterprise GitHub App registration, RS256 token exchange, and automated PR gating workflows.

---

## Quick Start with Docker Compose

### Prerequisites
- [Docker & Docker Compose](https://docs.docker.com/get-docker/) (v2.20+)
- Git
- Optional: OpenAI API Key (for LLM executive explanations)

### 1. Clone and Configure
```bash
git clone https://github.com/kartick026/MDT.git
cd MDT

# Copy environment template
cp backend/.env.example .env
```

Edit `.env` to supply optional tokens:
```bash
# Optional: Set GitHub token for private repositories or high rate limits
GITHUB_TOKEN=ghp_yourPersonalAccessTokenHere

# Optional: Set OpenAI key for AI-assisted reasoning
OPENAI_API_KEY=sk-yourOpenAiKey
```

### 2. Launch Cluster
```bash
docker compose up -d --build
```

### 3. Access MDT Services
Once the containers are running:
- **🖥 React Web Dashboard:** [http://localhost:5173](http://localhost:5173)
- **⚡ Backend Core API:** [http://localhost:8000](http://localhost:8000)
- **📖 OpenAPI Swagger Docs:** [http://localhost:8000/docs](http://localhost:8000/docs)
- **🌐 Neo4j Graph Browser:** [http://localhost:7474](http://localhost:7474) (`neo4j` / `password`)
- **📦 ChromaDB Vector Store:** [http://localhost:8005](http://localhost:8005)

---

## Reference Microservices Fleet

MDT includes 4 reference microservices running on Docker for testing cross-service blast radius:

| Service | Port | Dependencies | Role |
|---------|------|--------------|------|
| **`user-service`** | `8001` | None | User profiles, authentication schemas |
| **`order-service`** | `8002` | `user-service` | Order orchestration & checkout pipeline |
| **`payment-service`** | `8003` | `order-service` | Transaction settlement & payment gateways |
| **`notification-service`** | `8004` | `order-service`, `payment-service` | Event-driven customer notifications |

---

## Core API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Liveness health check with `X-Request-ID` and `X-Response-Time-MS` |
| `GET` | `/health/detailed` | Deep status check for Neo4j, ChromaDB, LLM, and GitHub tokens |
| `POST` | `/auth/login` | Authenticate with username & password, returns JWT token |
| `GET` | `/auth/me` | Current authenticated user profile and roles |
| `POST` | `/auth/refresh` | Extend active session with fresh JWT access token |
| `GET` | `/services/` | Returns registered services with live `/health` pings and route counts |
| `GET` | `/services/graph` | Returns full dependency nodes and edges with broken link flags |
| `GET` | `/services/smells` | Returns architectural anti-patterns with Cypher evidence |
| `POST` | `/api/registry/import` | Ingests microservice architecture from a GitHub repository |
| `POST` | `/analysis/analyze` | Executes HMDA risk scoring and connection validation on a commit/branch |
| `POST` | `/analysis/preview-fix` | Runs non-destructive What-If remediation simulation |
| `GET` | `/analysis/history` | Returns historical drift analysis runs |
| `POST` | `/webhook/github` | Receives GitHub push and pull request webhooks |

---

## Project Structure

```
MDT/
├── backend/
│   ├── api/                     # FastAPI route handlers
│   │   ├── analysis.py          # Impact analysis & What-If endpoints
│   │   ├── registry.py          # GitHub architecture ingestion
│   │   ├── services.py          # Live service health & graph queries
│   │   └── webhook.py           # GitHub webhook & HMAC verification
│   ├── core/                    # App config, database connectors
│   ├── schemas/                 # Pydantic schemas (ImpactResult, GraphEdit)
│   ├── services/                # Business logic engines
│   │   ├── connection_validator.py  # AST connection & broken link checker
│   │   ├── dependency_graph.py      # Neo4j Cypher queries & ghost purging
│   │   ├── git_analyzer.py          # Git diff extraction & AST parsing
│   │   ├── impact_engine.py         # HMDA 3-pillar risk scoring algorithm
│   │   ├── llm_explainer.py         # OpenAI reasoning & remediation logic
│   │   ├── remediation_simulator.py # Sandbox What-If simulator (rolled-back TX)
│   │   ├── retrieval.py             # ChromaDB vector embedding & RAG
│   │   └── smell_detector.py        # Cypher architectural anti-pattern detection
│   └── app.py                   # FastAPI application initialization
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── AnalysisHistory.jsx     # Analysis session audit trail
│   │   │   ├── ArchitecturalSmells.jsx # Anti-pattern cards & evidence viewer
│   │   │   ├── DependencyGraph.jsx     # Animated interactive SVG topology graph
│   │   │   ├── ImpactForm.jsx          # HMDA analysis, tabs, What-If preview
│   │   │   └── ServiceGrid.jsx         # Service cards, auto-discovery drawer
│   │   ├── App.jsx                     # Navbar, operational health status, layout
│   │   ├── App.css                     # Component design system
│   │   └── index.css                   # Theme tokens, custom dark glass scrollbars
│   └── Dockerfile               # Multi-stage Vite + Nginx production container
├── docs/                        # Comprehensive documentation
│   ├── deployment.md            # Production deployment & Nginx SSL guide
│   ├── features.md              # Exhaustive feature matrix & technical guide
│   └── github_app.md            # Enterprise GitHub App setup & PR gating
├── services/                    # Reference microservices fleet
│   ├── user_service/
│   ├── order_service/
│   ├── payment_service/
│   └── notification_service/
├── tests/                       # Unit and integration test suite
├── docker-compose.yml           # Complete container cluster definition
└── README.md                    # Project documentation entry point
```

---

## Testing

Run the automated test suite locally:

```bash
# Run backend test suite
pytest tests/ -v
```

All tests cover:
- HMDA deterministic risk calculations
- AST connection integrity and broken link detection
- Neo4j Cypher smell detection heuristics
- What-If remediation simulation schema validation and score delta calculations

---

## Contributing

1. Fork the repository.
2. Create a feature branch (`git checkout -b feature/resilience-facade`).
3. Commit your changes (`git commit -m "Add resilience facade pattern"`).
4. Push to the branch (`git push origin feature/resilience-facade`).
5. Open a Pull Request.

---

## License

Distributed under the **MIT License**. See `LICENSE` for more information.
