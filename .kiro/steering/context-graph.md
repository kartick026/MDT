# Microservice Drift Tracker — AI Context Graph

> This is the authoritative knowledge map of the project for AI agents.
> **Last updated:** Production Release (All Backend & Frontend Features Complete).
> Read this before touching any file.

---

## 1. Project Identity

| Field | Value |
|---|---|
| **Name** | Microservice Drift Tracker (MDT) |
| **Purpose** | AI-Assisted Cross-Service Impact Analysis & Architectural Health Governance — detects how code diffs ripple to dependent services, detects 10 architectural anti-patterns, and runs What-If sandbox simulations before deployment |
| **Version** | 1.0.0 |
| **Backend Stack** | FastAPI (Python 3.11/3.14), Neo4j 5 (Bolt / Cypher), ChromaDB, Multi-LLM (OpenAI GPT-4 / Google Gemini), Docker Compose |
| **Frontend Stack** | React 18, Vite, Lucide React, Cybernetic Glass Design System, Nginx container |
| **Testing** | Pytest (106 automated tests across API, AST, graph, auth, simulation, security), Pyright type validation |

---

## 2. System Status & Capabilities

| Module / Layer | Description | Status |
|---|---|---|
| **Docker Compose Fleet** | 8 services (backend, frontend, 4 demo microservices, Neo4j, ChromaDB) | ✅ Production Ready |
| **Four Microservices** | `user-service` (8001), `order-service` (8002), `payment-service` (8003), `notification-service` (8004) | ✅ Live & Probed |
| **Architecture Ingestion** | Ingests from GitHub URLs via `docker-compose.yml`, `render.yaml`, and monorepo folders | ✅ Live (`/api/registry/import`) |
| **HMDA Impact Engine** | Hierarchical Microservice Drift Analysis (10-step multi-factor risk scoring 0–100) | ✅ Complete (`/analysis/analyze`) |
| **10 Smell Detectors** | Cypher & heuristic detection for 10 anti-patterns with elementary cycle canonical deduplication | ✅ Complete (`/services/smells`) |
| **What-If Sandbox** | Non-destructive Neo4j transactional simulation with decoupled Commit Blast Radius vs. Smell Health | ✅ Complete (`/analysis/preview-fix`) |
| **Connection Validator** | AST static analysis detecting broken routes, port mismatches, unresolved hosts | ✅ Complete |
| **AI Reasoning** | Multi-provider LLM explainer (Google Gemini & OpenAI) with deterministic fallback | ✅ Live |
| **Client-Side Git Hook** | Pre-push Git hook (`mdt-hook/mdt_check.py`) blocking HIGH/CRITICAL drift pushes | ✅ Live (`MDT_FORCE=1` override) |
| **Cybernetic Dashboard** | Full-featured React SPA with SVG dependency graph, What-If dials, smell cards, history log | ✅ Production Ready |

---

## 3. Repository Layout

```
project 1/
├── backend/                             ← Main FastAPI application (port 8000)
│   ├── app.py                          ← Lifespan (DB init, graph schema, demo history seeding), middleware, router mounts
│   ├── requirements.txt                ← Core runtime requirements
│   ├── Dockerfile                      ← python:3.11-slim, git+curl, uvicorn
│   ├── .env.example                    ← Configuration template
│   ├── api/
│   │   ├── analysis.py                 ← POST /analysis/analyze, POST /analysis/preview-fix, GET /analysis/history
│   │   ├── auth.py                     ← POST /auth/login, POST /auth/refresh, POST /auth/token, GET /auth/me
│   │   ├── health.py                   ← GET /health (liveness), GET /health/detailed (component diagnostic checks)
│   │   ├── registry.py                 ← POST /api/registry/import (GitHub architecture discovery & monorepo parsing)
│   │   ├── services.py                 ← GET /services/, GET /services/graph, GET /services/smells
│   │   └── webhook.py                  ← POST /webhook/github (HMAC signature verification, push/ping handling)
│   ├── core/
│   │   ├── config.py                   ← Pydantic Settings (secrets, ports, thresholds, LLM configuration)
│   │   ├── auth.py                     ← JWT encoding/decoding, bcrypt password hashing, RBAC (admin/viewer)
│   │   ├── database.py                 ← Neo4j driver & ChromaDB client initialization
│   │   ├── middleware.py               ← Request tracing (X-Request-ID, X-Response-Time-MS), JSON logging
│   │   └── registry.py                 ← Active project context state manager
│   ├── schemas/
│   │   ├── analysis.py                 ← ImpactResult, GraphEdit, PreviewFixRequest, ScoreBreakdown
│   │   ├── auth.py                     ← Token, UserLogin, UserRegistration, UserOut
│   │   ├── registry.py                 ← ArchitectureImportRequest, ProjectContextResponse
│   │   ├── services.py                 ← ServiceHealth, DependencyGraphResponse, SmellResponse
│   │   └── webhook.py                  ← GitHubPushPayload, GitHubCommit, GitHubRepository
│   └── services/
│       ├── connection_validator.py     ← AST HTTP client caller inspection against live OpenAPI endpoints
│       ├── dependency_graph.py         ← Neo4j Cypher queries, topology caching, seeding, ghost node purging
│       ├── git_analyzer.py             ← Git ref resolution (ls-remote), patch parsing, AST change extraction
│       ├── impact_engine.py            ← HMDA 10-step scoring engine (AST + Graph + Chroma + Heuristics)
│       ├── llm_explainer.py            ← Gemini/OpenAI executive impact summaries & structured remediation
│       ├── remediation_simulator.py    ← Zero-risk sandbox What-If transaction simulator (rolled back automatically)
│       ├── retrieval.py                ← ChromaDB chunking, vector indexing, and cosine semantic drift modifier
│       └── smell_detector.py           ← 10 architectural smell detectors with elementary cycle deduplication
│
├── frontend/                            ← React 18 + Vite cybernetic glass web dashboard (port 5173 / Nginx 80)
│   ├── src/
│   │   ├── App.jsx                     ← Main shell, navigation tabs (Overview, Impact, Smells, Graph, History)
│   │   ├── App.css / index.css         ← Cybernetic Glass design tokens, glowing meters, dark-mode styling
│   │   ├── api.js                      ← Axios client with JWT interceptor, automatic token refresh, endpoints
│   │   ├── components/
│   │   │   ├── AnalysisHistory.jsx     ← Historical drift log table with commit details, risk tags, and filters
│   │   │   ├── ArchitecturalSmells.jsx ← 10 anti-pattern cards with severity filters and Cypher evidence inspect
│   │   │   ├── AuthPage.jsx            ← Secure login & registration portal with credentials showcase
│   │   │   ├── DependencyGraph.jsx     ← Animated SVG dependency graph with directional flows & zoom controls
│   │   │   ├── ErrorBoundary.jsx       ← Graceful UI error boundary
│   │   │   ├── ImpactForm.jsx          ← Primary impact analysis runner & What-If dual-dial simulation preview
│   │   │   ├── LoginModal.jsx          ← Quick modal login for expired sessions
│   │   │   ├── ServiceGrid.jsx         ← Fleet status overview, live health badges, endpoint counters
│   │   │   ├── SystemHealthModal.jsx   ← Deep diagnostics modal for Neo4j, ChromaDB, LLM, and tokens
│   │   │   └── Toast.jsx               ← Reactive alert notification toast
│   │   └── context/                    ← React Context (AuthContext for user state and token management)
│   ├── nginx.conf                      ← Production reverse proxy routing API requests to backend:8000
│   └── Dockerfile                      ← Node build stage + Nginx alpine serving stage
│
├── services/                            ← Four polyglot demo microservices
│   ├── user_service/                   ← Port 8001 (FastAPI user authentication & profiles)
│   ├── order_service/                  ← Port 8002 (FastAPI order lifecycle; central communication hub)
│   ├── payment_service/                ← Port 8003 (FastAPI payment transactions & gateway)
│   └── notification_service/           ← Port 8004 (FastAPI email/SMS/push notifications)
│
├── mdt-hook/                            ← Git Pre-Push Client Hook
│   └── mdt_check.py                    ← Executes before push; queries /analysis/analyze to block HIGH/CRITICAL drift
│
├── scripts/
│   └── run_microservices.py            ← Local multi-process runner (starts all 4 services locally without Docker)
│
├── docs/                                ← Authoritative Markdown documentation
│   ├── ARCHITECTURE.md                 ← System architecture, HMDA formulas, Cypher algorithms
│   ├── API.md                          ← REST API endpoint reference and payload examples
│   ├── features.md                     ← Feature-by-feature deep technical manual
│   ├── deployment.md                   ← Production Docker, ports, scaling, and reverse proxy setup
│   └── github_app.md                   ← Enterprise GitHub App setup & webhook guide
│
├── tests/                               ← 106 automated tests (API integration, type safety, auth, AST, graph, smells)
├── docker-compose.yml                  ← Orchestrates all 8 containers
└── README.md                           ← Project overview, architecture diagrams, quick-start guide
```

---

## 4. Key Architectural Patterns & Algorithms

### 4.1 HMDA (Hierarchical Microservice Drift Analysis)
Normalizes change blast radius to a 0–100 risk score:
- **File Change Factor:** Up to 30 pts based on modified file volume.
- **API Alterations:** +25 pts for route/endpoint schema modifications.
- **Core Service Modification:** +30 pts when modifying foundational services (`order`, `user`, `payment`).
- **Dependency Depth:** Traversed via Neo4j variable-length path queries (`depth * 5`, max 15 pts).
- **Database / Schema Changes:** +15 pts for DDL/migration files.
- **Infrastructure Changes:** +10 pts for Docker, Kubernetes, Helm configs.
- **Semantic Drift:** 0–10 pts via ChromaDB cosine similarity against past incidents.

### 4.2 The 10 Architectural Smells
Continuous Neo4j Cypher and OpenAPI contract snapshot evaluations:
1. **Circular Dependency (`CRITICAL`):**
   - Traversals are strictly filtered to **elementary cycles** (`len(cycle_nodes) == len(set(cycle_nodes))`).
   - Cycles are canonicalized via rotation (starting at the lexicographically lowest service) to prevent duplicate "figure-8" or cloverleaf paths.
2. **God / Bottleneck Service (`HIGH`):** Inbound fan-in $\ge 3$ or total degree $\ge 5$.
3. **High Coupling (`MEDIUM`):** Outbound dependencies $\ge 4$.
4. **Dead / Isolated Service (`LOW`):** In-degree $= 0$ and out-degree $= 0$.
5. **Dependency Explosion (`HIGH`):** Adding $\ge 3$ dependencies in one commit or transitive depth $\ge 5$.
6. **API Instability (`HIGH` / `MEDIUM`):** Route deletions or $\ge 3$ endpoint modifications across snapshots.
7. **Shared Database (`HIGH`):** Multiple services connecting to the same DB port or datastore host.
8. **Chatty Communication (`MEDIUM`):** Mutual cyclic chatter ($A \leftrightarrow B$) or $\ge 3$ connections between the pair.
9. **Missing Circuit Breaker (`MEDIUM`):** Synchronous fan-out to $\ge 3$ downstream targets without resilience proxies.
10. **Hub-and-Spoke Centralization (`HIGH`):** Single non-gateway service connected to $\ge 60\%$ of the entire fleet.

### 4.3 What-If Remediation Simulation Sandbox (`POST /analysis/preview-fix`)
- Runs in an isolated Neo4j transaction that is **always rolled back**.
- **Decoupled Metric Architecture:**
  - Evaluates **Architectural Smell Risk** reduction independently from **Git Commit Blast Radius**.
  - Clearly explains that Git Commit Risk remains driven by the number of changed source files being deployed (e.g. 57 files), while showing topological improvement (e.g. Smell Risk $100 \rightarrow 45$).

---

## 5. Development & Running Commands

| Target | Command |
|---|---|
| **Run Full Docker Stack** | `docker compose up -d` |
| **Rebuild Backend Container** | `docker compose build backend; docker compose up -d backend` |
| **Rebuild Frontend Container** | `docker compose build frontend; docker compose up -d frontend` |
| **Run 4 Microservices Locally (No Docker)** | `python scripts/run_microservices.py` |
| **Backend Local Dev** | `cd backend && uvicorn app:app --reload --port 8000` |
| **Frontend Local Dev** | `cd frontend && npm run dev` |
| **Run Full Test Suite** | `pytest tests` |
| **Run Type Check** | `npx pyright` |
| **Override Git Pre-Push Hook** | `$env:MDT_FORCE="1"; git push` (PowerShell) or `MDT_FORCE=1 git push` (Bash) |
