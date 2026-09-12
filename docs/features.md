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

The **HMDA Engine** is MDT's core risk algorithm. It evaluates code modifications against graph topology and semantic historical context.

### Git Branch & Ref Resolution (`resolve_commit_sha`)
MDT eliminates the need for developers to manually look up 40-character commit hashes:
- **Sub-Second `git ls-remote` Resolution:** Leverages `git ls-remote <repo_url> <ref>` in an async threadpool to resolve branch names (`main`, `master`, `develop`, tags, or `HEAD`) into exact 40-character commit SHAs in <1.5s, completely immune to GitHub REST API token rate limits.
- **Commit Patch Fallback:** Inspects `https://github.com/{owner}/{repo}/commit/{ref}.patch` headers (`From <sha> ...`) to parse commit diffs even under anonymous rate limiting.
- **Auto-Diff Detection:** If `changed_files` is omitted, automatically extracts all modified, added, and deleted files directly from the unified commit diff.

### The 3 Scoring Pillars

$$\text{Total Risk Score} = \min(100, \text{Deterministic Score} + \text{Semantic Modifier})$$

#### 1. Deterministic Graph & Code Factors (Base 0–100 pts)
- **File Impact Factor (up to 30 pts):** Evaluates number of changed files and line change volumes ($\min(30, \text{files} \times 5)$).
- **Core Service Modification (adds 30 pts):** Extra weighting applied if the modified service acts as a primary dependency sink (high fan-in).
- **API Signature Changes (adds 25 pts):** AST parser checks if function definitions, route decorators, or request schemas changed.
- **Dependency Graph Depth (up to 15 pts):** Cypher shortest-path queries calculate the maximum depth of cascading downstream impact ($\min(15, \text{depth} \times 5)$).

#### 2. Semantic Code Retrieval (ChromaDB RAG)
- Changed code snippets are embedded and matched against historical PR changes in ChromaDB.
- Flags whether similar code modifications in the past induced outages or high defect rates.

#### 3. AI-Assisted Reasoning (LLM Explainer)
- Generates natural-language executive summaries explaining the exact cause of the risk score.
- Categorizes risk into 4 standardized tiers matching `config.py` (`RISK_LOW=25`, `RISK_MEDIUM=50`, `RISK_HIGH=75`):
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
- **Heuristic:** Outbound synchronous fan-out ($\ge 3$ downstream targets) without resilience patterns, event brokers, or circuit breakers.
- **Impact:** Fragile synchronous calls where a slow downstream service exhausts caller thread/connection pools.
- **Remediation:** Implement circuit breakers (e.g. Resilience4j, Polly, Hystrix pattern), retries, and fallback defaults.

### 10. Hub-and-Spoke Centralization (`HIGH`)
- **Heuristic:** A single central service connected to $\ge 60\%$ of all registered services in an ecosystem with $\ge 3$ services.
- **Impact:** Creates a distributed monolith where the central hub prevents team autonomy and creates an existential SPOF.
- **Remediation:** Decentralize business logic into bounded contexts using domain-driven event streaming.

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

## Feature 8: GitHub Webhook & GitHub App Automation

MDT integrates natively into developer workflows via GitHub Webhooks and GitHub Apps.

### Capabilities
- **Push Event Webhooks (`POST /webhook/github`):**
  - Verifies HMAC `X-Hub-Signature-256` payload signatures.
  - Automatically fetches commit diffs from the GitHub REST API.
  - Executes HMDA analysis and records history.
- **GitHub App Support:**
  - Authenticates via RS256 Private Key (`.pem`) and App ID.
  - Mints short-lived Installation Access Tokens on the fly without relying on personal developer accounts.
- **PR Check Gating:**
  - Can be integrated into GitHub Actions / status checks to block pull requests whose HMDA risk exceeds defined thresholds (e.g. `risk_score > 75`).

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

### Example: Simulating a Breaking Change in Payment Service
1. Navigate to the **Impact Analysis** tab.
2. In **Configure Analysis**, enter:
   - **Repository URL:** `https://github.com/kartick026/MDT`
   - **Commit SHA:** `main`
   - **Changed Files:** `services/payment_service/main.py`
3. Click **⚡ Run HMDA Analysis**.
4. The dashboard displays:
   - **Score:** `60 HIGH`
   - **Impacted Services:** `order-service`, `notification-service`, `user-service`.
   - **Integrity Alert:** Any broken URLs detected in code.
5. In the **Recommendations** tab, locate:
   `"Introduce resilience facade for 'order-service' to isolate downstream failure cascade."`
6. Click **⚡ Preview Fix Impact**:
   - The **What-If Remediation Preview** panel opens.
   - You observe the score drop from `60` to `25` (`▼ 35 pts Reduction`).
   - You confirm that isolated service smells decrease from `2 → 1`.
7. Once verified, developers proceed to apply the facade pattern in code with full confidence.
