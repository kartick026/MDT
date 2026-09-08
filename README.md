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

- **🚀 Automated Architecture Ingestion:** Scan any GitHub repository URL to auto-register microservices, container ports, dependency links, and file mappings directly from `docker-compose.yml`.
- **🔌 Connection Integrity & Broken Endpoint Checks:** AST static analysis checks microservice HTTP calls against live OpenAPI endpoints, flagging `[UNRESOLVED_SERVICE_HOST]`, `[PORT_MISMATCH]`, and `[ENDPOINT_MISMATCH]` errors before production deployment.
- **⚡ HMDA (Hierarchical Microservice Drift Analysis):** Proprietary 3-pillar scoring engine combining deterministic code change volumes, dependency graph traversal depth, ChromaDB semantic retrieval, and LLM reasoning into a 0–100 risk score (`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`).
- **🧪 What-If Remediation Simulation Sandbox:** Test proposed architectural refactorings (e.g. adding circuit breakers or resilience facades) in an isolated sandbox. Renders before vs. after risk score gauges and smell resolution metrics in real time with zero database side-effects.
- **⚠ Architectural Smells & Anti-Pattern Detection:** Continuous Cypher queries detect 6 distributed anti-patterns: *Circular Dependencies*, *God / Bottleneck Services*, *High Coupling*, *Dependency Explosions*, *Dead / Isolated Services*, and *API Instability*.
- **🌐 Interactive Dependency Graph:** Visual SVG topology graph with animated directional flow lines, broken connection diagnostics, and risk-coded service nodes.
- **📜 Analysis History & Audit Trail:** Session-wide historical log of all drift analyses with full diff breakdowns, affected files, confidence metrics, and AI explanations.
- **🤖 GitHub App & Webhook Integration:** Native support for GitHub Webhooks and GitHub Apps (RS256 JWT installation tokens) for automated PR status check gating and review comments.
- **💎 Cybernetic Glassmorphic Dashboard:** Modern dark theme interface featuring custom translucent glass scrollbars, sticky docked controls, and segmented tab navigation.

---

## Detailed Documentation

Comprehensive documentation guides are available in the [`docs/`](./docs) directory:

- 📖 **[Features Guide (`docs/features.md`)](./docs/features.md):** In-depth technical breakdown of each feature, mathematical scoring formulas, detection algorithms, and API schemas.
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
| `GET` | `/health` | Liveness health check |
| `GET` | `/health/detailed` | Deep status check for Neo4j and ChromaDB |
| `GET` | `/services/` | Returns registered services with live `/health` pings and route counts |
| `GET` | `/services/graph` | Returns full dependency nodes and edges with broken link flags |
| `GET` | `/services/smells` | Returns architectural anti-patterns with Cypher evidence |
| `POST` | `/api/registry/import` | Ingests microservice architecture from a GitHub repository |
| `POST` | `/analysis/analyze` | Executes HMDA risk scoring and connection validation on a commit diff |
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
