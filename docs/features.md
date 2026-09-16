# Microservice Drift Tracker (MDT) — Features Guide

Welcome to the comprehensive features guide for **Microservice Drift Tracker (MDT)**. MDT is an AI-assisted cross-service impact analysis and drift governance platform engineered to detect architectural degradation, connection integrity issues, and breaking downstream blast radius **before code is deployed**.

---

## Table of Contents

1. [Platform Overview & Core Value](#platform-overview--core-value)
2. [Feature Matrix](#feature-matrix)
3. [Feature 1: Auto-Discovery & Resilient Architecture Ingestion](#feature-1-auto-discovery--resilient-architecture-ingestion)
4. [Feature 2: Connection Integrity & Broken Endpoint Validation](#feature-2-connection-integrity--broken-endpoint-validation)
5. [Feature 3: HMDA Engine & Git Branch Resolution](#feature-3-hmda-engine--git-branch-resolution)
6. [Feature 4: What-If Remediation Simulation Sandbox](#feature-4-what-if-remediation-simulation-sandbox)
7. [Feature 5: The 10 Architectural Smells & Anti-Pattern Detectors](#feature-5-the-10-architectural-smells--anti-pattern-detectors)
8. [Feature 6: Interactive Dependency Graph & Link Diagnostics](#feature-6-interactive-dependency-graph--link-diagnostics)
9. [Feature 7: Analysis History & Historical Audit Trail](#feature-7-analysis-history--historical-audit-trail)
10. [Feature 8: GitHub Webhook & GitHub App Automation](#feature-8-github-webhook--github-app-automation)
11. [Feature 9: Cybernetic Glassmorphic Dashboard & Real-Time Monitoring](#feature-9-cybernetic-glassmorphic-dashboard--real-time-monitoring)
12. [Feature 10: Enterprise JWT Authentication & RBAC](#feature-10-enterprise-jwt-authentication--rbac)
13. [Feature 11: Distributed Request Tracing & Deep Observability](#feature-11-distributed-request-tracing--deep-observability)
14. [API Reference & Schema Specifications](#api-reference--schema-specifications)
15. [End-to-End Workflow Examples](#end-to-end-workflow-examples)
16. [Known Limitations & Architectural Trade-offs](#known-limitations--architectural-trade-offs)

---

## Platform Overview & Core Value

Modern microservice architectures evolve through distributed codebases, multi-repo setups, and independent deployment pipelines. In this decentralized workflow, developers often lack full visibility into how an internal service edit propagates through upstream and downstream callers. 

**MDT solves this by acting as an architectural pre-flight safety net:**
- **Pre-Merge Validation:** Analyzes Git pull requests and commits before deployment.
- **Hybrid Intelligence:** Couples graph topology (Neo4j) with semantic code vectors (ChromaDB) and LLM reasoning.
- **Non-Destructive Simulation:** Developers can simulate architectural fixes in an isolated sandbox without modifying production databases.

---

## Feature Matrix

| Feature | Primary Component | Technology Stack | Key Benefit |
|---------|-------------------|------------------|-------------|
| **Architecture Ingestion** | `repo_onboarding.py`, `git_analyzer.py` | Compose/Render Parser, GitPython | Zero-config import; immune to GitHub API 60 req/hr limits |
| **Connection Integrity** | `connection_validator.py` | AST Parsing, Regex, OpenAPI | Catches 404s, wrong ports, and hardcoded `localhost` |
| **HMDA Drift Engine** | `impact_engine.py`, `git_analyzer.py` | Neo4j, Cypher, ChromaDB, `git ls-remote` | 0-100 risk score, sub-second ref resolution, blast depth |
| **What-If Sandbox** | `remediation_simulator.py` | Rolled-back Neo4j TXs, Heuristics | Previews score reduction before code is committed |
| **10 Architectural Smells** | `smell_detector.py` | Cypher Graph Algorithms | Flags cyclic dependencies, shared DBs, chatty calls, bottlenecks |
| **Dependency Graph** | `DependencyGraph.jsx` | React, SVG, CSS Animations | Visual graph with animated flows and broken-link indicators |
| **Analysis History** | `AnalysisHistory.jsx` | FastAPI in-memory / Neo4j | Audit log of all drift analyses across repositories |
| **GitHub Automation** | `webhook.py`, GitHub App | RS256 JWT, HMAC Webhooks | Automatic PR checks and automated review comments |
| **Enterprise JWT Auth** | `auth.py`, `LoginModal.jsx` | Bcrypt, HS256 JWT, Axios Interceptor | Protected mutation routes and role-based access control |
| **Distributed Tracing** | `middleware.py`, `health.py` | UUID4 Tracing, JSON Logs | `X-Request-ID`, `X-Response-Time-MS`, `/health/detailed` |
| **Glassmorphic UI** | `App.jsx`, `ImpactForm.jsx` | Vanilla CSS, Space Grotesk, JetBrains Mono | Dark glass design, sticky docking, tabbed inspection |

---

## Feature 1: Auto-Discovery & Resilient Architecture Ingestion

MDT eliminates tedious manual YAML mapping by automatically discovering and modeling distributed microservice architectures directly from any GitHub repository.

### How It Works
1. **Multi-Manifest Ingestion (`POST /api/registry/import`):**
   - Provide a repository URL (e.g. `https://github.com/kartick026/MDT` or `https://github.com/RahulNatesan/AI-Disease-Prediction.git`) and an optional branch ref (e.g. `main`).
   - Supports `docker-compose.yml` / `docker-compose.yaml` (services, ports, environment variables, `depends_on`).
   - Supports `render.yaml` / `render.yml` (multi-service definitions, root directories, runtime languages, and exposed ports).
   - Supports Polyglot Monorepo & Directory Discovery: automatically scans `backend/`, `frontend/`, `services/*`, `apps/*`, `packages/*`, and single-service repositories.
2. **GitHub API Rate-Limit Immunity:**
   - Unauthenticated GitHub REST API calls to `/git/trees` encounter a strict 60 req/hr rate limit. MDT features an automatic, resilient fallback that executes a shallow clone (`git clone --depth 1`) using GitPython and extracts file trees via `git ls-files`, guaranteeing 100% reliable onboarding without requiring personal tokens.
3. **Static Route & Endpoint Extraction:**
   - Statically inspects service entrypoints (`main.py`, `app.py`, `page.tsx`, etc.) across 8 programming languages to discover public API routes (e.g. `🔌 2 endpoints: /health, /api/analyze`) even when external containers are not locally running.
4. **Baseline Architectural Risk Scoring:**
   - Automatically evaluates static code quality and contract defect indicators upon import, computing an immediate baseline risk score (e.g. `53/100 MEDIUM`) and logging the initial architectural assessment into session history.
5. **Graph Reconciliation & Ghost Node Purging:**
   - When importing a new repository, MDT calls `purge_unregistered_services()`, clearing obsolete ghost nodes from past imports so Neo4j reflects only the currently active project.

---

## Feature 2: Connection Integrity & Broken Endpoint Validation

Static dependency declarations in Compose files often hide runtime bugs: a service may declare a dependency, but call a nonexistent URL or a hardcoded `localhost`. MDT runs deep code introspection to catch connection integrity errors.

### Detected Integrity Bugs
- **`[UNRESOLVED_SERVICE_HOST]`**:
  Flags HTTP calls targeting hardcoded `localhost` or unknown service hostnames inside container networks (e.g. calling `http://localhost:8000` from within an isolated Docker container instead of the internal service DNS `http://backend:8000`).
- **`[PORT_MISMATCH]`**:
  Detects when a service initiates requests to a port different from the registered target service's exposed port.
- **`[ENDPOINT_MISMATCH]`**:
  Cross-checks HTTP request paths against the OpenAPI path registry. If `order-service` calls `GET /api/v2/users` but `user-service` only serves `/users`, MDT flags an immediate broken endpoint alert.

### False-Positive Suppression & Intelligent Filtering
- **Dynamic Template Ports:** Ignores string template variables (e.g. `http://localhost:{port}`, `http://127.0.0.1:${PORT}`) where the port is resolved dynamically at runtime.
- **CORS Whitelists & Frontend Clients:** Ignores browser frontend origin declarations (`localhost:3000`, `localhost:5173`) in CORS configurations so valid development origins are not flagged as broken backend container links.
- **Variable Path Resolution:** Evaluates path constants and variables to reconstruct actual runtime request paths (e.g. `/users/{user_id}`).

### Visual Diagnostics
- Highlighted red alert banner in the **Overview** tab.
- Integrated error diagnostic cards inside the **Impact Analysis** report.
- Broken edges rendered as pulsing red dashed lines with `⚠ Broken Link` badges on the **Dependency Graph**.

---

## Feature 3: HMDA Engine & Git Branch Resolution

The **HMDA Engine** is MDT's core risk algorithm. It evaluates code modifications against graph topology, semantic historical context, and architectural smell metrics.

### Git Branch & Ref Resolution (`resolve_commit_sha`)
MDT eliminates the need for developers to manually look up exact 40-character commit hashes:
- **Comprehensive Ref Resolution Support:**
  - **Branch Names & Tags:** `main`, `master`, `develop`, `release/v2.1`, tags.
  - **Short Git SHAs (7 to 39 hex characters):** Native prefix matching (e.g. `c876e48`, `0f1c420`) resolved to canonical 40-character objects.
  - **Full 40-character SHAs:** Direct commit object inspection.
  - **Relative Git Revisions:** Evaluates relative ancestor syntax such as `HEAD~1` (previous commit), `HEAD~2`, or `main~1`.
  - **Root Commits:** Detects initial repository commits with zero parents and diffs against the Git empty tree hash (`4b825dc642cb6eb9a060e54bf8d69288fbee4904`), preventing crash failures on initial commits.
- **Sub-Second `git ls-remote` Resolution:** Leverages `git ls-remote <repo_url> <ref>` in an async threadpool to resolve remote branch names into exact commit SHAs in <1.5s, completely immune to GitHub REST API token rate limits.
- **Direct Local `.git` Fast-Path (<50ms):** When operating on a local repository, bypasses remote network calls entirely and inspects the local `.git` object database directly.
- **Commit Patch Fallback:** Inspects `https://github.com/{owner}/{repo}/commit/{ref}.patch` headers (`From <sha> ...`) to parse commit diffs even under anonymous rate limiting.
- **Auto-Diff Detection:** If `changed_files` is omitted, automatically extracts all modified, added, and deleted files directly from the unified commit diff.

### The 3 Scoring Pillars

$$\text{Total Risk Score} = \min(100, \text{Deterministic Score} + \text{Semantic Modifier})$$

#### 1. Deterministic Graph & Code Factors (Base 0–100 pts)
Configured via dynamic settings in `backend/core/config.py`:
- **File Impact Factor (up to 30 pts):** Evaluates number of changed files and line change volumes ($\min(30, \text{files} \times \text{HMDA\_FILE\_WEIGHT})$).
- **Core Service Modification (adds 30 pts):** Extra weighting applied if the modified service acts as a primary dependency sink (high fan-in $\ge 3$).
- **API Signature Changes (adds 25 pts):** AST parser checks if function definitions, route decorators, or request schemas changed.
- **Dependency Graph Depth (up to 15 pts):** Cypher shortest-path queries calculate the maximum depth of cascading downstream impact ($\min(15, \text{depth} \times \text{HMDA\_DEPTH\_WEIGHT})$).
- **Database Schema & Migration DDL (adds 15 pts):** Flags database migration scripts, Alembic revisions, or SQL schema alterations.
- **Infrastructure & Deployment Config (adds 10 pts):** Flags changes to `docker-compose.yml`, Kubernetes manifests, Helm charts, or cloud deployment specs.

#### 2. Semantic Code Retrieval (ChromaDB RAG)
- Changed code snippets are embedded and matched against historical PR changes in ChromaDB.
- Flags whether similar code modifications in the past induced outages or high defect rates.
- In offline mode, persists locally to DuckDB/Parquet disk storage (`chroma_db/`) without external cloud vector databases.

#### 3. AI-Assisted Reasoning (LLM Explainer) vs. Deterministic Heuristics
- **Online Mode:** Generates natural-language executive summaries via Gemini 2.5 Flash / GPT-4o explaining the root-cause of the score.
- **Offline Mode:** Uses pure deterministic heuristic generation to output concrete, actionable refactoring steps and risk justifications without external API calls.
- Standardized risk tiers matching `config.py`:
  - **`LOW` (0–24):** Localized edits, minimal downstream caller exposure.
  - **`MEDIUM` (25–49):** Moderate blast radius or intermediate dependency depth.
  - **`HIGH` (50–74):** Broad blast radius or breaking API schema changes.
  - **`CRITICAL` (75–100):** Core dependency sink modification, severe call cascades, or connection integrity failures.

---

## Feature 4: What-If Remediation Simulation Sandbox

MDT allows architects to test architectural remediations in a **zero-risk sandbox** before touching production code.

### Key Capabilities
- **Non-Destructive Simulation (`POST /analysis/preview-fix`):**
  - Executes proposed graph modifications inside an isolated Neo4j transaction that is **automatically rolled back**.
  - Live graph topology is never modified during simulation.
- **Architectural Smell Risk Metric:**
  - Evaluates topological anti-patterns (circular dependencies $\times 30$, bottlenecks $\times 20$, excessive coupling $\times 15$, isolated services $\times 5$, capped at 100).
  - Explicitly disambiguated in the UI as **Architectural Smell Risk** to avoid confusion with the commit-level HMDA drift risk score.
- **Verified Measurement Honesty (Zero Fabrication):**
  - If a simulated graph edit does not resolve any tracked anti-patterns, the system honestly reports `0.0 → 0.0` with `measurable_change: false` and a `"No measurable change in tracked architectural smells"` notice.
  - No synthetic or invented improvements are ever presented to developers or auditors.
- **Dual-Mode Simulator:**
  - Operates against live Neo4j database transactions or a deterministic in-memory heuristic when running in offline/mock mode.
- **Dynamic Service Resolution:**
  - Reconnecting dead or isolated services dynamically binds to an active central hub service detected in the architecture registry, adapting seamlessly to any imported GitHub repository without hardcoding.
- **Supported Graph Edits:**
  - `add_node`: Adds proxy nodes (e.g. resilience facades or circuit breakers).
  - `add_edge`: Re-routes callers through fault-tolerant paths.
  - `remove_edge`: Sever unneeded or circular links.
- **Visual Sandbox Comparison & Decoupled Dials:**
  - **Decoupled Metric Display:** Git Commit Blast Radius (driven by code diffs) and Graph Architecture Health (driven by smells) are presented as independent metrics.
  - **Dual SVG Gauges:** Renders `Before (Smell Risk)` vs `After (Smell Risk)` scores side-by-side.
  - **Delta Reduction Badge:** Prominently highlights points reduction (e.g. `▼ 55.1 pts Reduction` or `— Unchanged`).
  - **Commit Blast Radius Banner:** Explicitly clarifies when Git Commit Risk remains high (e.g. `Git Commit Risk Remains 100/100 (CRITICAL)` because 57 source files are being deployed), preventing confusion between code-change volume and topological health.
  - **Smells Resolution Table:** Displays exact anti-patterns resolved (e.g., `Circular Dependency: 4 → 3 (-1 resolved)`).

---

## Feature 5: The 10 Architectural Smells & Anti-Pattern Detectors

MDT runs continuous Cypher graph algorithms and contract snapshot inspections to identify 10 critical microservice anti-patterns:

### 1. Circular Dependency (`CRITICAL`)
- **Heuristic:** `MATCH path = (s:Service)-[:DEPENDS_ON*2..8]->(s)` detects cyclic dependency loops ($A \rightarrow B \rightarrow C \rightarrow A$).
- **Elementary Cycle & Canonical Deduplication:**
  - Raw Cypher variable-length traversals can return redundant composite walks (such as figure-8 or cloverleaf loops visiting a central service multiple times).
  - MDT filters traversals to strict **elementary cycles** (`len(cycle_nodes) == len(set(cycle_nodes))`), dropping any composite walks with repeated intermediate services.
  - Applies **canonical rotation** (normalizing the cycle to start with the lexicographically smallest service) so that identical cycles starting from different node perspectives are grouped into a single canonical finding.
- **Impact:** Causes distributed deadlocks, synchronous cascading timeouts, and tight deployment coupling.
- **Remediation:** Extract shared contracts, introduce asynchronous message queues, or decouple via event-driven pub/sub.

### 2. God / Bottleneck Service (`HIGH`)
- **Heuristic:** Inbound callers $\ge 3$ or total degree $\ge 5$ (excluding API gateways/facades).
- **Impact:** Concentrates excessive architectural gravity into a single failure domain and scaling bottleneck.
- **Remediation:** Decompose business capabilities into discrete sub-services or deploy caching facades.

### 3. High Coupling (`MEDIUM`)
- **Heuristic:** Direct outbound dependencies $\ge 4$.
- **Impact:** Violates single responsibility and loose coupling; changes in downstream services cause ripple effects.
- **Remediation:** Introduce an API Gateway Aggregator pattern to consolidate downstream interactions.

### 4. Dead / Isolated Service (`LOW`)
- **Heuristic:** Registered service with in-degree $= 0$ and out-degree $= 0$ in an ecosystem with $\ge 2$ services.
- **Impact:** Unused compute resource overhead, forgotten dead code, or unintegrated orphan components.
- **Remediation:** Decommission abandoned microservice or wire missing HTTP routes into the gateway.

### 5. Dependency Explosion (`HIGH`)
- **Heuristic:** A change snapshot adding $\ge 3$ new dependencies in a single commit, or transitive call depth $\ge 5$.
- **Impact:** Exponential expansion of blast radius, latency amplification, and combinatorial failure modes.
- **Remediation:** Adopt event-driven choreography to flatten deep synchronous call trees.

### 6. API Instability (`HIGH` / `MEDIUM`)
- **Heuristic:** Deleted OpenAPI endpoints (`HIGH`) or $\ge 3$ endpoint modifications (`MEDIUM`) across revisions without API versioning.
- **Impact:** Breaking contract changes break downstream microservice consumers and frontend clients without warning.
- **Remediation:** Maintain backward-compatible route aliases, version endpoints (`/v1/`, `/v2/`), and issue deprecation notices.

### 7. Shared Database (`HIGH`)
- **Heuristic:** Multiple distinct microservices connecting directly to the same database host or port (`5432`, `3306`, `27017`, `6379`).
- **Impact:** Violates microservice data isolation; schema alterations by one service silently crash other services.
- **Remediation:** Enforce Database-per-Service; expose data access through private service APIs or domain events.

### 8. Chatty Communication (`MEDIUM`)
- **Heuristic:** Mutual bidirectional calls ($A \rightarrow B$ and $B \rightarrow A$) or $\ge 3$ distinct connections between the same pair of services.
- **Impact:** High round-trip network chatter, elevated serialization overhead, and tight temporal coupling.
- **Remediation:** Consolidate fine-grained endpoints into coarse-grained batch APIs or adopt gRPC/GraphQL streaming.

### 9. Missing Circuit Breaker (`MEDIUM`)
- **Heuristic:** Dynamic percolation scale $\theta_{cb}(N) = \max(2, \lceil\sqrt{N}\rceil)$, modulated by statistical outlier bounds $\min(\theta_{percolation}, \max(2, \lceil \bar{k}_{out} + \sigma_{out} \rceil))$ without resilience flags (`has_circuit_breaker`/`resilient`).
- **Impact:** Fragile synchronous calls where a slow downstream service exhausts caller thread/connection pools.
- **Remediation:** Implement circuit breakers (e.g. Resilience4j, Polly, Hystrix pattern), retries, and fallback defaults.

### 10. Hub-and-Spoke Centralization (`HIGH`)
- **Heuristic:** Freeman degree centrality $\tau(N) = \max(0.60, 1.0 - 1/\sqrt{N})$, critical hub degree $\theta_{hub}(N) = \max(2, \lceil \tau(N) \cdot (N-1) \rceil)$, and topological dominance condition ($\text{degree} > \bar{k}$) in fleets with $\ge 3$ microservices.
- **Impact:** Creates a distributed monolith where the central hub prevents team autonomy and creates an existential SPOF.
- **Remediation:** Decentralize business logic into bounded contexts using domain-driven event streaming or API gateways.

### Evidence Inspection & Hygiene Rules
Each smell includes:
- **Severity Badge** (`CRITICAL`, `HIGH`, `MEDIUM`, `LOW`).
- **Involved Services** tags.
- **Raw Cypher Evidence Inspector:** Expandable `<details>` view with the underlying graph path metrics.
- **Self-Loop Exclusion:** Internal service self-calls (`from == to`) are automatically excluded from bidirectional communication, downstream fan-out counts, bottleneck degrees, and hub-and-spoke ratios, guaranteeing zero self-call false positives.
- **Node Risk Score Isolation:** Impact analysis evaluations measure the blast-radius risk of specific commits without contaminating the baseline static architectural health of every individual microservice node in the graph.

---

## Feature 6: Interactive Dependency Graph & Link Diagnostics

The **Dependency Graph** tab provides a real-time visual map of the entire microservice ecosystem.

### Features
- **Dynamic Grid Layout:**
  - Known services use calibrated coordinates.
  - Dynamically imported services from external GitHub repos automatically populate into a clean, collision-free multi-column layout.
- **Risk-Coded Node Cards:**
  - Node borders glow according to their risk level:
    - 🟢 `LOW`
    - 🟡 `MEDIUM`
    - 🟠 `HIGH`
    - 🔴 `CRITICAL`
    - ⚪ `UNANALYZED` (explicitly shown for newly imported services prior to drift analysis)
- **Live Directional Arrows:**
  - Dashed SVG flow lines animate in the direction of dependency ($A \rightarrow B$).
  - Problematic connections pulse in red with `Broken Link` indicators.

---

## Feature 7: Analysis History & Historical Audit Trail

Located in the **Analysis History** tab, this view maintains an audit log of all HMDA analyses executed during the session:
- **Auto-Refreshing (every 8 seconds):** Automatically polls backend for newly completed analyses.
- **Accordion Inspection:**
  - Overall score and severity badge.
  - Target repository and short commit hash (`@7a8bc9d`).
  - Natural language AI explanation.
  - Impacted downstream services list.
  - Full list of affected files with line change counts.
  - Score breakdown metrics (file count score, semantic risk, confidence percentage).

---

## Feature 8: Git Hooks, Webhooks & GitHub App Automation

MDT integrates natively into developer workflows before commit, before push, and across remote pull requests.

### 1. Client-Side Git Hook CLI (`mdt-hook/mdt_check.py`)
MDT provides a zero-dependency Python utility (`mdt-hook/mdt_check.py`) that acts as both an interactive developer tool and an automated Git lifecycle hook.

- **Pre-Commit Hook (`--install-hook pre-commit`):**
  - Installs an executable wrapper script at `.git/hooks/pre-commit`.
  - Analyzes files staged via `git add` (`git diff --cached --name-only`).
  - Blocks `git commit` if the computed HMDA risk is `HIGH` or `CRITICAL`.
- **Pre-Push Hook (`--install-hook pre-push`):**
  - Installs an executable wrapper script at `.git/hooks/pre-push`.
  - Analyzes outgoing changes (`HEAD~1..HEAD`) before transmission to remote branches.
  - Blocks `git push` if high-risk architectural drift is detected.
- **Interactive Flags & Modes:**
  - `python mdt-hook/mdt_check.py --staged`: Evaluates staged files.
  - `python mdt-hook/mdt_check.py --working`: Evaluates all modified/added files in the working directory against `HEAD`.
  - `python mdt-hook/mdt_check.py file1.py file2.py`: Evaluates specific paths.
  - `python mdt-hook/mdt_check.py --dry-run`: Previews HMDA score and colorized severity report without returning an exit error.
- **Bypass & Configuration Environment Variables:**
  - `MDT_FORCE=1`: Overrides high-risk blocks during emergencies (e.g. `MDT_FORCE=1 git commit -m "Emergency fix"` or `$env:MDT_FORCE="1"` in PowerShell).
  - `MDT_SKIP=1`: Skips MDT hook execution entirely.
  - `MDT_API_URL`: Points to a remote or containerized MDT backend (default: `http://localhost:8000`).

### 2. GitHub Webhook Ingestion (`POST /webhook/github`)
- **HMAC Signature Verification:** Verifies payload integrity via `X-Hub-Signature-256` using the configured `WEBHOOK_SECRET`.
- **Sliding-Window Rate Limiting:** Enforces in-memory IP rate limiting (`RATE_LIMIT_WEBHOOK_PER_MINUTE: 30`) and rejects payloads exceeding 25MB.
- **Event Handling:** Ingests `push` and `pull_request` events, running unified diff extraction and logging the results into the persistent session history.

### 3. Enterprise GitHub App Integration
- **Key-Based Authentication:** Authenticates via RS256 private key (`.pem`) and GitHub App ID.
- **Dynamic JWT Token Exchange:** Automatically mints short-lived Installation Access Tokens on the fly, eliminating reliance on developer Personal Access Tokens (PATs).
- **PR Check Gating & Automated Comments:** Updates commit status checks (`pending`, `success`, `failure`) and publishes structured review comments with architectural drift breakdown and smell warnings.

---

## Feature 10: Enterprise JWT Authentication & RBAC

MDT provides enterprise-grade authentication and route security:
- **HS256 JWT Token Workflow:**
  - Secure `/auth/login` endpoint verifying credentials against bcrypt-hashed passwords.
  - Configurable expiration (default 24 hours), token refresh via `/auth/refresh`, and active session inspection via `/auth/me`.
  - OAuth2-compatible `/auth/token` endpoint for native Swagger UI documentation.
- **Role-Based Access Control (RBAC):**
  - Distinguishes between `admin` (full permissions) and `engineer` (analysis execution).
- **Route Protection & UI Integration:**
  - Mutation endpoints (`/api/registry/import`, `/analysis/analyze`, `/analysis/preview-fix`) enforce bearer token validation.
  - Frontend `AuthPage.jsx` and `LoginModal.jsx` provide dedicated sign-in tabs, user avatar indicators, and automatic Axios interceptors for JWT header injection.

---

## Feature 11: Distributed Request Tracing & Deep Observability

Built for enterprise production telemetry:
- **Request Tracing Middleware (`core/middleware.py`):**
  - Automatically tags every incoming HTTP request with a unique `X-Request-ID` (UUID4).
  - Measures execution latency with microsecond precision and appends `X-Response-Time-MS` to response headers.
- **Structured JSON Logging:**
  - `JSONLogFormatter` formats log lines into JSON records (`timestamp`, `level`, `request_id`, `message`, `module`) for seamless ingestion into Datadog, ELK, or CloudWatch.
- **Deep Health Diagnostics (`GET /health/detailed`):**
  - Component-by-component health checks for Neo4j cluster connectivity, ChromaDB vector indexing, LLM availability, and GitHub token quotas.

---

## API Reference & Schema Specifications

### Core Endpoints

#### 1. Services & Graph
- **`GET /services/`**: Returns all registered services enriched with live `/health` ping status and OpenAPI route counts.
- **`GET /services/graph`**: Returns graph nodes and dependency edges with broken link flags.
- **`GET /services/smells`**: Executes Cypher smell detection heuristics.
- **`POST /api/registry/import`**: Ingests a GitHub repository by parsing its `docker-compose.yml`.

#### 2. Impact Analysis
- **`POST /analysis/analyze`**: Runs manual HMDA impact analysis.
  ```json
  {
    "repo_url": "https://github.com/kartick026/MDT",
    "commit_sha": "main",
    "changed_files": ["services/payment_service/main.py"]
  }
  ```
- **`POST /analysis/preview-fix`**: Executes a What-If remediation simulation.
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
    ]
  }
  ```
- **`GET /analysis/history`**: Returns historical analysis runs.

#### 3. System Health
- **`GET /health`**: Basic liveness probe.
- **`GET /health/detailed`**: Deep status check verifying connectivity to Neo4j and ChromaDB.

---

## End-to-End Workflow Examples

### Workflow 1: Operating Offline (Air-Gapped & Local Development)
**Scenario:** A developer works in a secure air-gapped corporate network without external internet or OpenAI API keys.

1. **Launch Local Infrastructure:**
   ```bash
   docker compose up -d neo4j chromadb backend frontend
   ```
2. **Launch Reference Microservices Fleet:**
   ```bash
   python scripts/run_microservices.py
   ```
   Runs `user-service` (8001), `order-service` (8002), `payment-service` (8003), and `notification-service` (8004) concurrently via Python multiprocessing.
3. **Execute Local Git Pre-Flight Check:**
   When editing `services/payment_service/main.py`, the developer runs:
   ```bash
   python mdt-hook/mdt_check.py --working
   ```
   MDT queries the local `.git` repository in under 50ms, computes the 100% deterministic HMDA score (`HMDA_FILE_WEIGHT`, `HMDA_CORE_SERVICE_WEIGHT`, etc.), runs the 10 Cypher smell queries locally against Neo4j, and returns a concrete heuristic mitigation plan with zero cloud API dependencies.

---

### Workflow 2: Operating Online (Cloud Ingestion, GitHub App & LLM Reasoning)
**Scenario:** An engineering organization governance team audits a multi-service repository hosted on GitHub.

1. **Import Remote Repository:**
   In the **Overview** tab, the architect imports `https://github.com/kartick026/MDT` on branch `main`.
   MDT authenticates via GitHub App (RS256 JWT) or Personal Access Token (`GITHUB_TOKEN`), shallow-clones the tree, parses `docker-compose.yml`, and maps all 4 microservices and their dependencies into Neo4j.
2. **Run AI-Augmented Drift Analysis:**
   In **Impact Analysis**, the architect triggers HMDA analysis. MDT calculates graph shortest paths, embeds changed code into ChromaDB, and queries Google Gemini (`gemini-2.5-flash`) or OpenAI.
3. **Executive Explanation:**
   The dashboard displays a structured executive narrative detailing the exact cascading risks across upstream and downstream services, broken endpoint alerts, and recommended code patterns.

---

### Workflow 3: Operating Before Commit (Pre-Commit Governance & Simulation)
**Scenario:** A developer edits `services/order_service/main.py` by removing an endpoint, risking cascading 404s for upstream callers.

1. **Install Git Pre-Commit Hook:**
   ```bash
   python mdt-hook/mdt_check.py --install-hook pre-commit
   ```
2. **Stage Changes:**
   ```bash
   git add services/order_service/main.py
   ```
3. **Attempt Commit:**
   ```bash
   git commit -m "Refactor order status endpoint"
   ```
   The `.git/hooks/pre-commit` hook automatically executes `mdt-hook/mdt_check.py --staged`. MDT detects `[ENDPOINT_MISMATCH]` and an API Instability smell:
   ```text
   ━━━ MDT HMDA Pre-Commit Analysis (Staged Files) ━━━
     Risk score : 85/100
     Severity   : CRITICAL
     Impacted   : order-service, user-service, notification-service

   MDT: Commit/Push blocked — risk score is 85/100 (CRITICAL).
        Fix the architectural issues or bypass with:  MDT_FORCE=1 git commit
   ```
4. **Simulate Graph Remediation in What-If Sandbox:**
   The developer opens the dashboard's **What-If Simulation** tab, tests adding an `order-service_facade` to maintain route backward compatibility, observes the risk score decrease from `85 → 45`, and implements the adapter in code before committing cleanly.

---

### Workflow 4: Operating After Commit (Target Commit SHA, Pre-Push & CI/CD)
**Scenario:** A tech lead reviews a specific committed revision (`c876e48`) and enforces push gating across the engineering team.

1. **Install Git Pre-Push Hook:**
   ```bash
   python mdt-hook/mdt_check.py --install-hook pre-push
   ```
   Prevents unvetted outgoing commits (`HEAD~1..HEAD`) from being pushed to remote branches if risk exceeds `HIGH` (50) or `CRITICAL` (75).
2. **Target Commit / Revision Inspection in Dashboard:**
   In the **Impact Analysis** form, the tech lead inputs:
   - **Repository URL:** `https://github.com/kartick026/MDT`
   - **Target Commit / Revision:** `c876e48` (or `HEAD~1`)
   - Leaves **Manual File Overrides** empty.
   MDT automatically extracts the exact unified diff introduced by `c876e48`, resolves the revision, and presents the full impact blast radius.
3. **CI/CD Pull Request Automation:**
   The team registers `mdt-hook/mdt_check.py --working` into `.github/workflows/mdt-gate.yml`. When PRs are created, MDT analyzes the branch diff and blocks merges if the HMDA score exceeds the team's risk threshold.


---

## Known Limitations & Architectural Trade-offs

Engineering a robust distributed architectural tracking platform requires clear trade-offs between rapid onboarding and security hardening. This section openly documents known architectural trade-offs, deliberate design decisions, and planned evolutionary upgrades.

### 1. Client-Side JWT Storage in `localStorage` (Security Trade-off)
- **Current Pattern**:
  The React SPA client in `frontend/src/api.js` persists authentication credentials (`mdt_token`, `mdt_user`) in browser `localStorage`. Outgoing API requests automatically attach the token via an Axios request interceptor (`Authorization: Bearer <token>`).
- **Trade-off Analysis**:
  - *Benefits*: Highly ergonomic for Single-Page Application (SPA) development, avoids cross-origin cookie configuration hurdles during multi-domain or local container development, simplifies session hydration, and eliminates the immediate need for synchronized anti-CSRF token handling.
  - *Risk*: `localStorage` is accessible to any script running within the same origin. If an unmitigated Cross-Site Scripting (XSS) vulnerability exists anywhere within the application or its third-party frontend dependencies, an attacker could potentially extract the stored JWT.
- **Production Hardening Path**:
  Prior to enterprise production deployment, the recommended architectural path is:
  1. Migrate token issuance to set `httpOnly`, `Secure`, and `SameSite=Strict` (or `SameSite=Lax`) session cookies on the backend (`/auth/login` and `/auth/refresh`).
  2. Implement anti-CSRF protection (e.g. Double Submit Cookie pattern or stateful CSRF token exchange header).
  3. Ensure JavaScript execution contexts cannot directly read the sensitive session credential.

### 2. Multi-Language AST Parsing: Python Native AST vs. Regex Heuristics
- **Current Pattern**:
  - **Python (`.py`)**: Parsed with 100% syntactic fidelity using Python's native `ast` module (`ast.parse()`). MDT accurately extracts class definitions, function decorators (e.g. FastAPI `@app.get`, `@router.post`, Flask `@app.route`), docstrings, and call arguments.
  - **Polyglot Services (JavaScript/TypeScript, Go, Java, Rust)**: Non-Python languages are analyzed via high-performance regex heuristics in `git_analyzer.py` and `repo_onboarding.py`. These heuristics identify standard route definitions (e.g. `app.get('/path', ...)`, Express routers, Spring annotations, Go `http.HandleFunc`).
- **Documented Limitation**:
  Regex heuristics, while dependency-free, fast, and resilient across varied file layouts, cannot build full abstract syntax trees for dynamic metaprogramming, complex nested factory functions, or non-standard routing frameworks in TypeScript/Go.
- **Next Architectural Evolution (Tree-sitter Upgrade)**:
  The designated next step for deeper multi-language accuracy is integrating `tree-sitter` (via `tree-sitter` Python bindings with grammar libraries for JavaScript, TypeScript, Go, Java, and C#). Tree-sitter generates concrete syntax trees (CSTs) incrementally without requiring external runtime compilers or language runtimes installed on the host.

### 3. Multi-Strategy Fallback Exception Observability
- **Traceability Guarantee**:
  MDT relies on multi-stage fallback chains across operations like Git branch resolution (trying branch candidates, commit SHAs, remote refs, and symbolic heads) and container port extraction. All fallback branches are instrumented with explicit `logger.debug(...)` output. If every strategy in a fallback chain fails, the complete debug trail is captured in system logs rather than silently discarded.

