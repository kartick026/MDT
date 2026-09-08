# Microservice Drift Tracker (MDT) — Features Guide

Welcome to the comprehensive features guide for **Microservice Drift Tracker (MDT)**. MDT is an AI-assisted cross-service impact analysis and drift governance platform engineered to detect architectural degradation, connection integrity issues, and breaking downstream blast radius **before code is deployed**.

---

## Table of Contents

1. [Platform Overview & Core Value](#platform-overview--core-value)
2. [Feature Matrix](#feature-matrix)
3. [Feature 1: Auto-Discovery & Architecture Ingestion](#feature-1-auto-discovery--architecture-ingestion)
4. [Feature 2: Connection Integrity & Broken Endpoint Validation](#feature-2-connection-integrity--broken-endpoint-validation)
5. [Feature 3: HMDA (Hierarchical Microservice Drift Analysis) Engine](#feature-3-hmda-hierarchical-microservice-drift-analysis-engine)
6. [Feature 4: What-If Remediation Simulation Sandbox](#feature-4-what-if-remediation-simulation-sandbox)
7. [Feature 5: Architectural Smells & Anti-Pattern Detection](#feature-5-architectural-smells--anti-pattern-detection)
8. [Feature 6: Interactive Dependency Graph & Link Diagnostics](#feature-6-interactive-dependency-graph--link-diagnostics)
9. [Feature 7: Analysis History & Historical Audit Trail](#feature-7-analysis-history--historical-audit-trail)
10. [Feature 8: GitHub Webhook & GitHub App Automation](#feature-8-github-webhook--github-app-automation)
11. [Feature 9: Cybernetic Glassmorphic Dashboard & Real-Time Monitoring](#feature-9-cybernetic-glassmorphic-dashboard--real-time-monitoring)
12. [API Reference & Schema Specifications](#api-reference--schema-specifications)
13. [End-to-End Workflow Examples](#end-to-end-workflow-examples)

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
| **Architecture Ingestion** | `RegistryManager`, `git_analyzer.py` | Python, Docker Compose Parser | Zero-config import from any GitHub repository |
| **Connection Integrity** | `connection_validator.py` | AST Parsing, Regex, OpenAPI | Catches 404s, wrong ports, and hardcoded `localhost` |
| **HMDA Drift Engine** | `impact_engine.py` | Neo4j, Cypher, ChromaDB, OpenAI | Computes 0-100 risk score and blast-radius depth |
| **What-If Sandbox** | `remediation_simulator.py` | Rolled-back Neo4j TXs, Heuristics | Previews score reduction before code is committed |
| **Smell Detection** | `smell_detector.py` | Cypher Graph Algorithms | Flags cyclic dependencies, bottleneck services, and dead code |
| **Dependency Graph** | `DependencyGraph.jsx` | React, SVG, CSS Animations | Visual graph with animated flows and broken-link indicators |
| **Analysis History** | `AnalysisHistory.jsx` | FastAPI in-memory / Neo4j | Audit log of all drift analyses across repositories |
| **GitHub Automation** | `webhook.py`, GitHub App | RS256 JWT, HMAC Webhooks | Automatic PR checks and automated review comments |
| **Glassmorphic UI** | `App.jsx`, `ImpactForm.jsx` | Vanilla CSS, Space Grotesk, JetBrains Mono | Dark glass design, sticky docking, tabbed inspection |

---

## Feature 1: Auto-Discovery & Architecture Ingestion

MDT eliminates tedious manual YAML mapping by automatically scanning repository architectures directly from GitHub.

### How It Works
1. **GitHub Ingestion (`POST /api/registry/import`):**
   - Provide a repository URL (e.g. `https://github.com/kartick026/MDT` or `https://github.com/serhiiur/Event-Driven-Microservices-Example`) and a target branch (e.g. `main`).
   - MDT fetches and parses `docker-compose.yml` or service configuration files using either GitHub App installation tokens or a Personal Access Token.
2. **Dynamic Topology Extraction:**
   - Detects all microservice nodes, container ports, environment variables, and `depends_on` relationships.
   - Extracts file path prefix mappings (e.g., `services/order_service/` maps to `order-service`).
3. **Graph Reconciliation & Ghost Node Purging:**
   - When switching repositories, MDT calls `purge_unregistered_services()`, clearing obsolete ghost nodes from past imports so Neo4j reflects only the currently active project.
4. **OpenAPI Route Reflection:**
   - Concurrently pings each live service's `/openapi.json` to inspect endpoints and report real route counts (e.g. `4 endpoints`) rather than dummy zeros.

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

### Visual Diagnostics
- Highlighted red alert banner in the **Overview** tab.
- Integrated error diagnostic cards inside the **Impact Analysis** report.
- Broken edges rendered as pulsing red dashed lines with `⚠ Broken Link` badges on the **Dependency Graph**.

---

## Feature 3: HMDA (Hierarchical Microservice Drift Analysis) Engine

The **HMDA Engine** is MDT's core risk algorithm. It evaluates code modifications against graph topology and semantic historical context.

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
- **Visual Sandbox Comparison:**
  - **Dual SVG Gauges:** Renders `Before (Smell Risk)` vs `After (Smell Risk)` scores side-by-side.
  - **Delta Reduction Badge:** Prominently highlights points reduction (e.g. `▼ 5 pts Reduction` or `— Unchanged`).
  - **Smells Resolution Table:** Displays exact anti-patterns resolved (e.g., `Isolated Service: 2 → 1 (-1 resolved)`).

---

## Feature 5: Architectural Smells & Anti-Pattern Detection

MDT runs continuous Cypher graph algorithms to identify structural architectural smells:

```
┌────────────────────────────────────────────────────────────────────────────┐
│                       ARCHITECTURAL SMELLS DETECTED                        │
├────────────────────────┬───────────────────────────────────────────────────┤
│ Circular Dependency    │ Call cycle detected: A -> B -> C -> A             │
│ God / Bottleneck       │ Single service handles disproportionate fan-in     │
│ High Coupling          │ Excessive bidirectional HTTP chatter              │
│ Dependency Explosion   │ Single service depends on too many downstreams    │
│ Dead / Isolated Service│ Service completely disconnected from graph        │
│ API Instability        │ Endpoints undergoing rapid unversioned drift      │
└────────────────────────┴───────────────────────────────────────────────────┘
```

### Evidence Inspection
Each smell includes:
- **Severity Badge** (`CRITICAL`, `HIGH`, `MEDIUM`, `LOW`).
- **Involved Services** tags.
- **Raw Cypher Evidence Inspector:** Expandable `<details>` view with the underlying graph path metrics.

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

## Feature 9: Cybernetic Glassmorphic Dashboard & Real-Time Monitoring

Designed with modern aesthetics for high technical clarity:

### UI Highlights
- **Curated Dark Palette:** Deep navy backgrounds (`#050810`), Space Grotesk headings, JetBrains Mono code badges, and cyan/green accents.
- **Custom Glass Scrollbars:** Translucent dark scrollbars (`rgba(10, 13, 26, 0.5)`) on all containers, eliminating native white scrollbars.
- **Sticky Form Docking:** The left configuration panel stays anchored in view while scrolling through extensive analysis reports on the right.
- **Segmented Detail Switcher:** Replaces clunky vertical scrollboxes with tabbed navigation:
  - `💡 Recommendations (N)`
  - `📁 Affected Files (N)` with live real-time filename search filter
  - `🌐 Blast Radius (N)`
  - `📋 View All`
- **Real-Time Health Polling (every 5–6s):**
  - Clearly differentiates **Container Availability** (`○ 5 Services Imported (Offline)`) from **Architectural Risk** (`🔴 CRITICAL`).

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
