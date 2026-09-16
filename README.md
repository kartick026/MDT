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
- **🪝 Automated Git Pre-Push Hook (`mdt-hook/`):** Client-side Git hook queries the MDT analysis engine to evaluate changed files before code reaches remote repositories, blocking `HIGH` or `CRITICAL` risk pushes unless explicitly overridden (`MDT_FORCE=1 git push` or `$env:MDT_FORCE="1"; git push` in PowerShell).
- **🛡 Clean Architectural Smell Isolation:** Filters out internal self-loops (`from == to`) from mutual chatter and fan-out metrics, preventing false-positive smells while isolating commit impact risk from baseline service node health.
- **🔌 Polyglot Connection Integrity & Broken Endpoint Checks:** AST static analysis inspects microservice HTTP client calls against live OpenAPI endpoints, flagging `[UNRESOLVED_SERVICE_HOST]`, `[PORT_MISMATCH]`, and `[ENDPOINT_MISMATCH]` errors before production deployment. Automatically filters CORS whitelists and dynamic template ports (`:{port}`) to eliminate false positives.
- **⚡ HMDA (Hierarchical Microservice Drift Analysis):** Proprietary multi-pillar scoring engine combining deterministic code change volumes, dependency graph traversal depth, ChromaDB semantic retrieval, and LLM reasoning into a normalized 0–100 risk score (`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`).
- **🔍 Git Ref & Branch Resolution:** Native resolution of branch names (`main`, `master`, tags, `HEAD`) to concrete 40-character commit hashes via ultra-fast `git ls-remote` (<1.5s) and commit patch parsing.
- **🧪 What-If Remediation Simulation Sandbox:** Test proposed architectural refactorings (e.g. adding circuit breakers or resilience facades) in an isolated transaction sandbox. Renders before vs. after risk score gauges with decoupled Git Commit Blast Radius vs. Architecture Smell Risk, delivering honest smell resolution metrics in real time with zero database side-effects.
- **⚠ 10 Architectural Smells & Anti-Pattern Detectors:** Continuous Cypher graph queries and heuristic algorithms detect 10 critical distributed anti-patterns across microservices, using strict elementary cycle filtering and canonical deduplication to eliminate composite cycle bloat.
- **🌐 Interactive Dependency Graph:** Visual SVG topology graph with animated directional flow lines, zoom controls, blast-radius interactive highlighting, and risk-coded service nodes.
- **📜 Analysis History & Audit Trail:** Session-wide historical log of all drift analyses with full diff breakdowns, affected files, confidence metrics, and AI explanations.
- **🔐 Enterprise JWT Authentication & RBAC:** Production-grade HS256 JWT tokens, bcrypt password hashing, role-based access control (`admin`, `engineer`), and secure mutation route protection.
- **⏱ Distributed Request Tracing & Observability:** High-resolution execution timing headers (`X-Request-ID`, `X-Response-Time-MS`), JSON structured logging, and deep component diagnostic checks (`/health/detailed`).
- **🤖 GitHub App & Webhook Automation:** Native support for GitHub Webhooks and GitHub Apps (RS256 JWT installation tokens) for automated PR status check gating and review comments.

---

## ⚡ Hierarchical Microservice Drift Analysis (HMDA) Scoring Model

MDT quantifies cross-service architectural impact using a normalized 0–100 risk score that synthesizes deterministic AST metrics, graph traversal depth, and semantic vector context.

### The HMDA Formula

$$\text{Final Risk Score} = \max\left(0.0, \min\left(100.0, \text{Deterministic Base Risk} + \text{Semantic Modifier}\right)\right)$$

$$\text{Deterministic Base Risk} = \min\left(100, F_{\text{files}} + F_{\text{api}} + F_{\text{core}} + F_{\text{depth}} + F_{\text{schema}} + F_{\text{config}}\right)$$

### The 7 HMDA Scoring Factors

| Factor | Description & Detection Logic | Default Weight / Formula | Config Key in `backend/core/config.py` |
|---|---|:---:|---|
| **1. File Count ($F_{\text{files}}$)** | Scales risk with the volume of modified files in the change. | $\min(30, \text{file\_count} \times 5)$ | `HMDA_MAX_FILE_PTS: 30`<br>`HMDA_WEIGHT_FILE: 5` |
| **2. API Alterations ($F_{\text{api}}$)** | Triggered when modified files alter HTTP routes, controllers, or endpoints (`api`, `route`, `endpoint`, `controller`, `handler`). | $+25\text{ pts}$ | `HMDA_PTS_API_CHANGE: 25` |
| **3. Core Service Impact ($F_{\text{core}}$)** | Triggered when modified files belong to high-centrality dependency sinks ($\text{in-degree} \ge \max(2, \lceil\bar{k}_{\text{in}}\rceil)$). | $+30\text{ pts}$ | `HMDA_PTS_CORE_SERVICE: 30` |
| **4. Dependency Depth ($F_{\text{depth}}$)** | Variable-length shortest-path traversal across the Neo4j graph calculating maximum cascading call depth. | $\min(15, \text{max\_depth} \times 5)$ | `HMDA_MAX_DEPTH_PTS: 15`<br>`HMDA_WEIGHT_DEPTH: 5` |
| **5. Database Schema / DDL ($F_{\text{schema}}$)** | Triggered when changes touch database migration scripts, Alembic, Flyway, Prisma, or `.sql` definitions. | $+15\text{ pts}$ | `HMDA_PTS_SCHEMA_CHANGE: 15` |
| **6. Infrastructure & Config ($F_{\text{config}}$)** | Triggered when changes modify `docker-compose`, Kubernetes manifests, Helm charts, terraform, or `.env` configs. | $+10\text{ pts}$ | `HMDA_PTS_CONFIG_CHANGE: 10` |
| **7. Semantic Modifier ($S_{\text{semantic}}$)** | Cosine similarity against historical outage and incident code vectors retrieved from ChromaDB. | $+0.0 \text{ to } +10.0\text{ pts}$<br>($\text{round}(10 \times \text{similarity}, 1)$) | Embedded ChromaDB RAG |

### Standardized Severity Tiers

The final score maps to 4 standardized severity tiers configured in `backend/core/config.py`:
- 🟢 **`LOW` (0.0 – 24.9):** Localized changes with minimal downstream impact.
- 🟡 **`MEDIUM` (25.0 – 49.9):** Moderate blast radius or intermediate dependency depth (`RISK_LOW = 25`).
- 🟠 **`HIGH` (50.0 – 74.9):** Broad blast radius or breaking API contract changes (`RISK_MEDIUM = 50`).
- 🔴 **`CRITICAL` (75.0 – 100.0):** Core dependency sink modification, deep cascading chains, or connection integrity failures (`RISK_HIGH = 75`).

---

## The 10 Architectural Smells Detected by MDT

MDT continuously analyzes the live Neo4j graph topology, OpenAPI contract snapshots, and dependency declarations to detect 10 distributed microservice anti-patterns:

| # | Architectural Smell | Severity | Heuristic & Detection Logic | Risk & Impact |
|---|:---|:---:|:---|:---|
| **1** | **Circular Dependency** | `CRITICAL` | Cypher cyclic path traversal: `(s:Service)-[:DEPENDS_ON*2..8]->(s)` filtered to strict elementary cycles (`len(cycle_nodes) == len(set(cycle_nodes))`) and canonical rotations to eliminate duplicate composite walks. | Causes distributed deadlocks, cascading timeout failures, tightly coupled deployment locks, and prevents isolated service testing. |
| **2** | **God / Bottleneck Service** | `HIGH` | Services with high inbound fan-in ($\ge 3$ callers) or total degree $\ge 5$ (excluding API gateways/facades). | Creates a severe single point of failure (SPOF) and scalability bottleneck; if this service degrades, multiple upstream business domains collapse. |
| **3** | **High Coupling** | `MEDIUM` | Services with excessive direct outbound dependencies ($\ge 4$ downstream targets). | Violates single responsibility and loose coupling; alterations in downstream services frequently trigger ripple breaking changes. |
| **4** | **Dead / Isolated Service** | `LOW` | Registered services with total degree $= 0$ (in-degree $= 0$ and out-degree $= 0$) in an ecosystem of $\ge 2$ services. | Represents abandoned microservices, dead code, incomplete deployment manifests, or unintegrated orphan components wasting infrastructure resources. |
| **5** | **Dependency Explosion** | `HIGH` | Commits or snapshot transitions adding $\ge 3$ new dependencies in a single change, or transitive call chains exceeding depth $\ge 5$. | Drastically expands failure blast radius, compounds network latency, and causes combinatorial deployment complexity. |
| **6** | **API Instability** | `HIGH` / `MEDIUM` | OpenAPI snapshot diff tracking deleted routes or $\ge 3$ endpoint modifications between consecutive revisions without API versioning. | Breaking contract changes without semantic versioning immediately break downstream microservice consumers and mobile/web clients. |
| **7** | **Shared Database** | `HIGH` | Multiple microservices directly reading or writing to the same database host, datastore port (`5432`, `3306`, `27017`, `6379`), or DB connection string. | Violates microservice data encapsulation; schema migrations by one service silently break other services; bypasses API validation rules. |
| **8** | **Chatty Communication** | `MEDIUM` | Mutual bidirectional calls ($A \rightarrow B$ and $B \rightarrow A$) or excessive fine-grained connections ($\ge 3$ distinct connections) between the same pair. | Excessive round-trips create ping-pong network chatter, latency amplification, and tight temporal coupling between services. |
| **9** | **Missing Circuit Breaker** | `MEDIUM` | Dynamic percolation scale $\theta_{cb}(N) = \max(2, \lceil\sqrt{N}\rceil)$, modulated by statistical outlier bounds $\min(\theta_{percolation}, \max(2, \lceil \bar{k}_{out} + \sigma_{out} \rceil))$ without resilience flags (`has_circuit_breaker`/`resilient`). | Fragile synchronous calls where a slow downstream service exhausts caller thread/connection pools, inducing cascading outage across the fleet. |
| **10** | **Hub-and-Spoke Centralization** | `HIGH` | Freeman degree centrality $\tau(N) = \max(0.60, 1.0 - 1/\sqrt{N})$, critical hub degree $\theta_{hub}(N) = \max(2, \lceil \tau(N) \cdot (N-1) \rceil)$, and topological dominance condition ($\text{degree} > \bar{k}$) in fleets with $\ge 3$ microservices. | Monolith disguised as microservices; concentrates excessive architectural gravity into a pseudo-monolith, preventing team autonomy. |

---

## 🚀 Operating MDT: Offline vs. Online, Before vs. After Commit

MDT is engineered to function seamlessly across **four operational quadrants**, adapting whether you are working in an air-gapped local environment without external APIs, or orchestrating enterprise CI/CD workflows across cloud repositories.

### Operational Quadrant Matrix

| Operational Quadrant | Primary Interface / Tool | Network Dependency | Primary Use Case & Capabilities |
|---|---|---|---|
| **Offline + Before Commit** | `mdt-hook/mdt_check.py --staged`<br>Dashboard Manual Overrides | **None (Zero Network)**<br>Local `.git` + Local Backend | Inspect uncommitted/staged code, local HMDA deterministic scoring (<50ms), What-If sandbox simulations. |
| **Offline + After Commit** | `mdt-hook/mdt_check.py --pre-push`<br>Dashboard Target Commit SHA | **None (Zero Network)**<br>Local Git Object Database | Evaluate local commits (`HEAD~1..HEAD`, short SHAs, relative refs) against local Neo4j topology before pushing. |
| **Online + Before Commit** | PR Gating CI Workflows<br>Developer CLI (`MDT_API_URL`) | **Target Backend / Cloud LLM** | Pre-merge PR simulation, Gemini/OpenAI executive risk summaries, remote architecture contract verification. |
| **Online + After Commit** | GitHub App (RS256 JWT)<br>Webhooks (`/webhook/github`) | **GitHub API + Cloud LLM** | Automated commit & PR webhook ingestion, persistent historical audit trail, automated PR status checks & review comments. |

---

### 1. Operating Offline (Air-Gapped & Local Development)

MDT is fully operational in 100% offline or air-gapped environments with zero external network connectivity or cloud subscriptions.

- **Local `.git` Repository Fast-Path:** When analyzing local repositories, MDT's `git_analyzer.py` directly queries the local `.git` filesystem via GitPython and subprocess calls. Diffs, file trees, and commit metadata resolve in under 50ms without hitting the GitHub REST API or consuming rate limits.
- **Deterministic HMDA Risk Scoring:** When `OPENAI_API_KEY` is not provided or omitted in `.env`, MDT automatically executes its high-precision deterministic scoring engine:
  - 10 Cypher graph queries run locally against the Neo4j container (`bolt://localhost:7687`) or embedded mock fallback.
  - AST connection integrity checks analyze source code locally across 8 languages without external linters.
  - Heuristic-based remediation suggestions and concrete mitigation rules are generated with zero external API calls.
- **Local Persistent Vector Store:** ChromaDB runs in embedded persistent disk mode (`chroma_db/`), maintaining historical code embeddings locally without external vector SaaS dependencies.
- **Local Microservices Fleet:** Run the reference microservice fleet locally via the multi-process runner:
  ```bash
  # Run user, order, payment, and notification services locally on ports 8001-8004
  python scripts/run_microservices.py
  ```

---

### 2. Operating Online (Cloud, GitHub App & LLM Integration)

In connected cloud environments, MDT unlocks automated repository ingestion, AI-driven executive remediation, and repository-wide webhook governance.

- **Multi-Manifest GitHub Ingestion:** Ingest any public or private GitHub repository URL via `POST /api/registry/import`. Automatically parses `docker-compose.yml`, `render.yaml`, or polyglot monorepo service directories.
- **GitHub App & PAT Integration:** Authenticates via GitHub App using RS256 private key JWT exchange, or via Personal Access Tokens (`GITHUB_TOKEN` in `.env`) for private repo access and high rate-limit allowances.
- **Cloud AI Executive Reasoning:** Connects to Google Gemini (`gemini-2.5-flash`) or OpenAI models to generate natural-language executive summaries, risk root-cause explanations, and step-by-step refactoring guides.
- **Automated Webhook Ingestion (`POST /webhook/github`):**
  - Validates GitHub webhook payloads using HMAC SHA-256 signatures (`X-Hub-Signature-256`).
  - Automatically analyzes `push` and `pull_request` events, storing historical drift assessments in the audit trail.
  - Posts automated PR status checks and warning comments when high-risk architectural drift is detected.

---

### 3. Operating Before Commit (Pre-Commit Governance & Local Previews)

Catching architectural drift *before* code is committed prevents costly branch rollbacks, broken downstream contracts, and polluted git histories.

#### Developer CLI Check (`mdt-hook/mdt_check.py`)
Run the interactive pre-flight CLI directly from your terminal:

```bash
# 1. Analyze files currently staged with `git add`
python mdt-hook/mdt_check.py --staged

# 2. Analyze all modified working tree files (staged & unstaged vs HEAD)
python mdt-hook/mdt_check.py --working

# 3. Analyze specific candidate files
python mdt-hook/mdt_check.py backend/api/orders.py services/user_service/main.py

# 4. Dry-run preview (displays HMDA score without exiting with error code)
python mdt-hook/mdt_check.py --dry-run
```

#### Automated Git Pre-Commit Hook
Install the automated pre-commit hook with a single command:

```bash
# Automatically creates executable .git/hooks/pre-commit
python mdt-hook/mdt_check.py --install-hook pre-commit
```
Whenever a developer runs `git commit`, the hook automatically evaluates the staged files against the MDT analysis engine. If the risk score is `HIGH` ($\ge 50$) or `CRITICAL` ($\ge 75$), the commit is **blocked**:

```text
━━━ MDT HMDA Pre-Commit Analysis (Staged Files) ━━━
  Risk score : 85/100
  Severity   : CRITICAL
  Impacted   : order-service, user-service, notification-service

  High risk detected due to API contract alterations in order-service...

MDT: Commit/Push blocked — risk score is 85/100 (CRITICAL).
     Fix the architectural issues or bypass with:  MDT_FORCE=1 git commit
```

- **Emergency Override:**
  - Bash / Linux / macOS: `MDT_FORCE=1 git commit -m "Hotfix for billing outage"`
  - PowerShell (Windows): `$env:MDT_FORCE="1"; git commit -m "Hotfix for billing outage"`
  - Skip completely: `MDT_SKIP=1 git commit -m "..."`

#### Dashboard Manual File Override & What-If Sandbox
- **Manual File Overrides:** In the React dashboard's **Impact Analysis** form, toggle *Manual File Overrides* and paste candidate file paths to simulate blast radius before writing code.
- **What-If Simulation Sandbox:** In the **What-If Simulation** tab, propose graph refactorings (e.g. inserting an API facade node or severing a cyclic edge) to test how they reduce architectural smell risk in an isolated, rolled-back transaction.

---

### 4. Operating After Commit (Target Commit SHA, Pre-Push Hook & CI/CD)

Once code has been committed, MDT governs code promotions, verifies specific revisions, gates remote pushes, and audits historical drift.

#### Dashboard Target Commit / Revision Analysis
The MDT Web Dashboard features a dedicated **Target Commit / Revision** input field supporting multiple ref formats:

- **Short Git SHA (7–39 hex characters):** e.g. `c876e48`
- **Full 40-character Git SHA:** e.g. `0f1c4204c2f22d97d27b7a847b2fe057f36afd42`
- **Relative Revisions:** e.g. `HEAD~1` (previous commit), `HEAD~2`, `main~1`
- **Branch Names & Tags:** e.g. `main`, `master`, `v1.2.0`
- **Root Commits:** MDT detects initial repository root commits with no parents and diffs against the Git empty tree (`4b825dc642cb6eb9a060e54bf8d69288fbee4904`).

When a revision is provided, MDT extracts the exact commit diff from the repository and runs full HMDA scoring against that specific historical snapshot.

#### Automated Git Pre-Push Hook
Install the automated pre-push hook to prevent high-risk commits from reaching remote repositories:

```bash
# Automatically creates executable .git/hooks/pre-push
python mdt-hook/mdt_check.py --install-hook pre-push
```
When running `git push`, the hook analyzes the changes introduced in the outgoing commit (`HEAD~1..HEAD`). If the risk is `HIGH` or `CRITICAL`, the push is halted before touching GitHub/GitLab.

#### CI/CD Pull Request Gating (GitHub Actions)
Add MDT to your `.github/workflows/mdt-gate.yml` to automatically gate PR merges:

```yaml
name: MDT Architectural Governance Gate

on:
  pull_request:
    branches: [ main, master ]

jobs:
  mdt-analysis:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout Code
        uses: actions/checkout@v4
        with:
          fetch-depth: 50

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Run MDT HMDA Drift Gate
        env:
          MDT_API_URL: ${{ secrets.MDT_API_URL || 'http://mdt.internal.company.com:8000' }}
        run: |
          python mdt-hook/mdt_check.py --working
```

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

MDT includes a live Docker microservices fleet for testing cross-service blast radius and architectural smells:

| Service | Port | Status | Baseline Risk | Dependencies | Role & Architecture Note |
|---|:---:|:---:|:---:|---|---|
| **`user-service`** | `8001` | `HEALTHY` | `25.0 (LOW)` | `order-service` (cyclic) | Core user account management and CRUD operations |
| **`order-service`** | `8002` | `HEALTHY` | `85.0 (CRITICAL)` | `user-service`, `notification-service`, `inventory-service:9999` | Order orchestration; contains intentional dead-host call to port 9999 |
| **`payment-service`** | `8003` | `HEALTHY` | `10.0 (LOW)` | Independent | Transaction settlement & payment gateways (isolated service) |
| **`notification-service`** | `8004` | `HEALTHY` | `35.0 (MEDIUM)` | `order-service`, `user-service`, `local-demo-postgres` | Event-driven notifications; participates in shared database pattern |
| **`inventory-service`** | `9999` | `OFFLINE` | `90.0 (CRITICAL)` | Independent | Legacy inventory service — dead host demonstrating contract defect detection |

> [!TIP]
> **Running Demo Microservices Locally (Without Docker):**  
> You can also run all 4 demo microservices concurrently on ports 8001–8004 using Python's multiprocessing runner:
> ```bash
> python scripts/run_microservices.py
> ```

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
