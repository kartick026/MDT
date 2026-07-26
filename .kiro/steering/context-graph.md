# Microservice Drift Tracker — AI Context Graph

> This is the authoritative knowledge map of the project for AI agents.
> **Last updated:** Phase 6 (ChromaDB Retrieval) complete.
> Read this before touching any file.

---

## 1. Project Identity

| Field | Value |
|---|---|
| **Name** | Microservice Drift Tracker (MDT) |
| **Purpose** | AI-Assisted Cross-Service Impact Analysis — detects how a code change in one microservice ripples to dependent services *before* deployment |
| **Version** | 1.0.0 |
| **Stack** | FastAPI (Python 3.11), Neo4j 5, ChromaDB, OpenAI GPT-4, Docker Compose |
| **Frontend** | Not yet built (React 18 + Vite + TypeScript planned — Week 10) |

---

## 2. Phase Build Status

| Phase | Week | Description | Status |
|---|---|---|---|
| 1 | 1 | Project setup, Docker Compose, FastAPI skeleton | ✅ Done |
| 2 | 2–3 | Four demo microservices (user/order/payment/notification) | ✅ Done |
| 3 | 4 | GitHub Webhook — real payload parsing, signature verification, ping/push handling | ✅ Done |
| 4 | 5 | Git Diff Analyzer — GitHub API + gitpython, real AST extraction | ✅ Done |
| 5 | 6 | Neo4j Dependency Graph — schema, seeding, traversal, real depth scoring | ✅ Done |
| 6 | 7 | ChromaDB Retrieval — chunking, TF-IDF/OpenAI embeddings, risk_modifier | ✅ Done |
| 7 | 8 | HMDA risk engine — fully wired (depth from graph, confidence dynamic) | ✅ Done |
| 8 | 9 | LLM Explainer — OpenAI + fallback rule-based | ✅ Done (needs real API key) |
| 9 | 10 | React Dashboard | ❌ Not built |
| 10 | 11 | Testing suite | ❌ Not built |
| 11 | 12 | Final deployment docs / demo | ❌ Not built |

---

## 3. Repository Layout (current — after cleanup)

```
d:\microservice\
├── backend/                        ← Main FastAPI app (port 8000)
│   ├── app.py                      ← App factory, lifespan (init_databases + graph.init_schema), CORS, router mounts
│   ├── requirements.txt            ← fastapi, uvicorn, pydantic, openai, gitpython, httpx
│   ├── Dockerfile                  ← python:3.11-slim, git+curl, uvicorn app:app port 8000
│   ├── .env.example                ← All env var templates
│   ├── api/
│   │   ├── analysis.py             ← POST /analysis/analyze, GET /analysis/history, /severity-thresholds
│   │   ├── health.py               ← GET /health, /health/detailed (real component checks)
│   │   ├── services.py             ← GET /services/, /{name}, /{name}/dependencies, /{name}/affected-by
│   │   ├── webhook.py              ← POST /webhook/github (full pipeline), /webhook/test, /webhook/simulate
│   │   └── __init__.py
│   ├── core/
│   │   ├── config.py               ← Pydantic Settings — all env vars
│   │   ├── database.py             ← init_databases(), get_neo4j_driver(), get_chroma_client() — optional imports
│   │   └── __init__.py
│   ├── schemas/
│   │   ├── analysis.py             ← ImpactResult, SeverityLevel, DiffFile, DependencyInfo
│   │   ├── webhook.py              ← GitHubPushPayload, GitHubPingPayload, GitHubCommit, etc.
│   │   └── __init__.py
│   ├── services/
│   │   ├── git_analyzer.py         ← GitAnalyzer (GitHub API + gitpython), ASTAnalyzer, ChangeInfo
│   │   ├── impact_engine.py        ← ImpactEngine (HMDA 10-step), RiskFactors
│   │   ├── dependency_graph.py     ← DependencyGraph (Neo4j async/sync), seed data, static fallback
│   │   ├── retrieval.py            ← RetrievalEngine (ChromaDB + TF-IDF/OpenAI embeddings, chunking)
│   │   ├── llm_explainer.py        ← LLMExplainer (AsyncOpenAI + rule-based fallback)
│   │   └── __init__.py
│   └── tests/                      ← empty scaffold
│
├── services/                       ← Four demo microservices
│   ├── user_service/               ← Port 8001 — user CRUD, in-memory dict
│   ├── order_service/              ← Port 8002 — orders, calls user-service
│   ├── payment_service/            ← Port 8003 — payments, calls order-service
│   └── notification_service/       ← Port 8004 — email/sms/push notifications
│
├── tests/
│   └── __init__.py                 ← empty scaffold
│
├── docker-compose.yml
└── README.md

DELETED (cleaned up):
  - backend/main.py           (was just a comment)
  - backend/models/           (re-exported schemas nobody used)
  - backend/routers/          (placeholder, routes live in api/)
  - root __init__.py          (empty)
```

---

## 4. Backend Module Deep-Dive

### 4.1 `app.py` — Application Entry Point

- `lifespan` calls `init_databases()` then `DependencyGraph().init_schema()` on startup
  - `init_schema()` creates Neo4j constraints + seeds 4 known services + 4 dependency edges
  - Both degrade gracefully if DBs are not running
- Router mounts: `/health`, `/webhook`, `/analysis`, `/services`
- CORS: `allow_origins=["*"]` — restrict in production
- `sys.path.insert(0, parent_dir)` so all imports are absolute from `backend/`

### 4.2 `core/config.py` — Settings

| Setting | Default | Purpose |
|---|---|---|
| `NEO4J_URI` | `bolt://localhost:7687` | Neo4j bolt URL |
| `NEO4J_USER` | `neo4j` | Neo4j auth |
| `NEO4J_PASSWORD` | `password` | Neo4j auth |
| `CHROMADB_HOST` | `localhost` | ChromaDB host |
| `CHROMADB_PORT` | `8000` | ChromaDB port (mapped to 8005 on host) |
| `GITHUB_WEBHOOK_SECRET` | `secret` | HMAC-SHA256 signature key |
| `GITHUB_TOKEN` | `""` | PAT for GitHub API diff fetching (optional) |
| `OPENAI_API_KEY` | `""` | OpenAI — optional, rule-based fallback if empty |
| `LLM_MODEL` | `gpt-4` | OpenAI chat model |
| `EMBEDDING_MODEL` | `text-embedding-ada-002` | OpenAI embedding model |
| `RISK_LOW` | `25` | LOW severity threshold |
| `RISK_MEDIUM` | `50` | MEDIUM severity threshold |
| `RISK_HIGH` | `75` | HIGH/CRITICAL boundary |
| `DEBUG` | `True` | Skips webhook signature verification |

### 4.3 `core/database.py` — DB Layer

- `neo4j` and `chromadb` packages are optional imports — app starts without them
- On startup: tries `neo4j.GraphDatabase.driver` + `verify_connectivity()`
- On startup: tries `chromadb.HttpClient` + `heartbeat()`
- Both log warnings on failure, never crash the app
- `get_neo4j_driver()` / `get_chroma_client()` return `None` when not connected

### 4.4 `schemas/webhook.py` — GitHub Webhook Schemas

Real GitHub push event models (NOT a wrapper):
```python
class GitHubPushPayload:
    ref: str              # "refs/heads/main"
    after: str            # head commit SHA
    before: str           # previous SHA
    commits: List[GitHubCommit]
    repository: GitHubRepository
    pusher: GitHubPusher
    head_commit: Optional[GitHubCommit]

    # Computed properties:
    .branch          → "main"
    .commit_sha      → after SHA
    .repo_url        → repository.clone_url
    .author          → pusher.name
    .commit_message  → head_commit.message
    .all_changed_files() → List[{path, change_type}]  # deduplicated across all commits
```

### 4.5 `services/git_analyzer.py` — Git Analysis ✅ Phase 4

**`ChangeInfo` dataclass** — primary DTO through the entire pipeline:
```python
@dataclass
class ChangeInfo:
    file_path: str
    change_type: str       # "added" | "modified" | "deleted"
    diff_content: str      # unified diff text
    additions: int
    deletions: int
    old_content: str
    new_content: str
    ast_metadata: Dict     # {language, functions[], classes[], imports[], exports[]}

    # Computed:
    .lines_changed  → additions + deletions
    .extension      → ".py"
    .language       → "python"
```

**`GitAnalyzer.analyze_push(repo_url, commit_sha, changed_files)`**:
- Strategy 1: GitHub REST API — fetches commit diff + file contents in parallel (no clone). Used when URL contains `github.com`
- Strategy 2: gitpython shallow clone (`depth=2`) — used for non-GitHub or local repos
- Both strategies populate `diff_content`, `additions`, `deletions`, `old_content`, `new_content`, `ast_metadata`
- Fallback: returns minimal `ChangeInfo` so pipeline never crashes

**`GitHubAPIClient`**:
- `get_file_content(owner, repo, path, ref)` → base64 decode from GitHub API
- `get_commit_diff(owner, repo, sha)` → full diff via `application/vnd.github.diff`
- `_get_parent_sha()` → resolves first parent commit

**`ASTAnalyzer`**:
- Python: stdlib `ast.parse()` → accurate functions, classes, imports
- JS/TS: regex → named functions, arrow functions, classes, ES imports, exports
- Java: regex → methods, classes, imports
- Go: regex → `func` declarations, import paths
- Generic fallback for other languages

### 4.6 `services/dependency_graph.py` — Neo4j Layer ✅ Phase 5

**Graph schema:**
```
(:Service {name, port, url, language, description, updated_at})
(:File    {path, service, language, functions, classes, last_seen})
(:Analysis {commit_sha, risk_score, severity, changed_files, created_at})

(:Service)-[:DEPENDS_ON {type, endpoint, updated_at}]->(:Service)
(:Service)-[:DEFINES_FILE]->(:File)
(:Service)-[:HAS_ANALYSIS]->(:Analysis)
```

**Seeded on every startup (idempotent MERGE):**
```
user-service (8001)
order-service (8002)  --DEPENDS_ON--> user-service
payment-service (8003) --DEPENDS_ON--> order-service
notification-service (8004) --DEPENDS_ON--> order-service
                             --DEPENDS_ON--> payment-service
```

**Key methods:**
- `init_schema()` — constraints + indexes + seed
- `get_affected_services(file_path)` — 3-tier fallback:
  1. Neo4j graph traversal (owner + upstream dependants, up to 4 hops)
  2. Path-prefix static map (`services/payment_service/` → `payment-service`)
  3. All 4 services (safe maximum)
- `get_dependency_chain(service, depth=4)` → `List[{from, to, type, endpoint}]`
- `get_dependency_depth(service)` → int (used by ImpactEngine for risk scoring)
- `record_analysis(commit_sha, service, risk_score, severity, files)` → persists to graph
- `_get_dependants_from_static_map(service)` — pure-Python transitive closure, no Neo4j

**Async driver handling:**
- Tries `async with driver.session()` first (neo4j async driver)
- Falls back to `asyncio.to_thread` with sync driver
- Never crashes — always returns fallback data

**File-to-service mapping** (`FILE_SERVICE_MAP`):
```python
"services/user_service"        → "user-service"
"services/order_service"       → "order-service"
"services/payment_service"     → "payment-service"
"services/notification_service"→ "notification-service"
```

### 4.7 `services/retrieval.py` — ChromaDB Layer ✅ Phase 6

**Collection:** `"mdt_code_context"` with cosine similarity space

**Chunking:** 50-line windows, 10-line overlap → `chunk_id = MD5(file_path:start_line)[:16]`

**Embedding strategies:**
1. OpenAI `text-embedding-ada-002` — when `OPENAI_API_KEY` is set
2. TF-IDF cosine vectors (512-dim, L2-normalised) — pure Python fallback

**`index_change(file_path, content, service, change_type, language, functions, classes, risk_score)`:**
- Chunks content → embeds each chunk → upserts into ChromaDB
- Called automatically by `ImpactEngine._index_changes()` after every analysis
- Metadata stored per chunk: `file_path`, `service`, `language`, `functions`, `classes`, `risk_score`, `start_line`, `end_line`

**`retrieve_similar(changes, top_k=5)` → `{documents, metadatas, risk_modifier}`:**
- Query text built from: file path tokens + AST function names + class names
- Generates query embedding → queries ChromaDB
- `risk_modifier` = weighted-average of past `risk_score` in retrieved chunks, scaled to 0–10
  - Similarity (1 - cosine_distance) used as weight
  - Past risk 100 → +10 modifier; past risk 50 → +5

**`collection_stats()` → `{status, collection, count}`** — used by `/health/detailed`

### 4.8 `services/impact_engine.py` — HMDA Algorithm ✅ Phase 7

**10-step pipeline** (`analyze_impact(changes)`):

| Step | Action |
|---|---|
| 1 | `_calculate_deterministic_risk(changes)` → `RiskFactors` |
| 2 | `_get_impacted_services_with_depth(changes)` → `(services[], max_depth)` from Neo4j |
| 3 | `_retrieve_context(changes)` → ChromaDB similar chunks |
| 4 | `_compute_base_risk(factors)` → deterministic score |
| 5 | Add `semantic_boost` from ChromaDB `risk_modifier` (0–10 pts) |
| 6 | `_get_severity(final_risk)` → `SeverityLevel` |
| 7 | `_generate_explanation(...)` → LLM or rule-based string |
| 8 | `_suggest_fixes(...)` → up to 5 fix strings |
| 9 | `_compute_confidence(services, depth)` → dynamic 0.5–0.95 |
| 10 | `_index_changes(changes, risk_score)` → ChromaDB indexing for future retrieval |
| bonus | `_record_to_graph(...)` → Neo4j Analysis node for history |

**`_compute_base_risk` scoring:**
- +5 per changed file, capped at 30
- +25 if file path contains: `api`, `route`, `endpoint`, `controller`, `handler`
- +30 if `core_service_impact=True` (path contains `user_service`, `payment_service`, `order_service`)
- +5 × `dependency_depth` from real Neo4j query, capped at 15

**Confidence formula:**
- No services found → 0.50
- Services found, depth > 0 (real Neo4j) → min(0.95, 0.75 + depth×0.05)
- Services found, depth = 0 (static map) → 0.70

### 4.9 `services/llm_explainer.py` — LLM Layer ✅ Phase 8

- `AsyncOpenAI` client — only created when `OPENAI_API_KEY` is set
- `explain(changes, impacted_services, risk_score, context)` → str
  - Temperature 0.3, max_tokens 500
  - Prompt includes: risk score, changed files, impacted services, retrieved context snippets
  - Falls back to `_fallback_explanation()` — deterministic rule-based string
- `suggest_remediation(impacted_services, changes, risk_score)` → `List[str]`
  - Temperature 0.4, max_tokens 300
  - Falls back to `_fallback_remediation()`

---

## 5. API Reference (current)

### Backend (port 8000)

| Method | Path | Status | Description |
|---|---|---|---|
| GET | `/` | ✅ | Service name, version, status |
| GET | `/health` | ✅ | `{"status": "healthy"}` |
| GET | `/health/detailed` | ✅ | Real Neo4j + ChromaDB connectivity + indexed chunk count |
| POST | `/webhook/github` | ✅ | GitHub push/ping handler — full pipeline |
| POST | `/webhook/test` | ✅ | Connectivity test — returns debug_mode, signature_verification |
| POST | `/webhook/simulate` | ✅ | Simulate push without GitHub (dev/demo) |
| POST | `/analysis/analyze` | ✅ | Manual analysis trigger |
| GET | `/analysis/history` | ⚠️ | Stub — returns empty list (no persistence yet) |
| GET | `/analysis/severity-thresholds` | ✅ | Returns current threshold config |
| GET | `/services/` | ✅ | All services from Neo4j (or static fallback) |
| GET | `/services/{name}` | ✅ | Real health check via httpx |
| GET | `/services/{name}/dependencies` | ✅ | Real Neo4j dependency chain |
| GET | `/services/{name}/affected-by` | ✅ | Which services are impacted if this one changes |

### GitHub Webhook (`POST /webhook/github`):
1. Raw body read once → `json.loads(body)`
2. `DEBUG=False`: HMAC-SHA256 signature verified against `GITHUB_WEBHOOK_SECRET`
3. `ping` event → `{"status": "pong", ...}`
4. `push` event → `GitHubPushPayload` parsed → files extracted with change_types → `GitAnalyzer.analyze_push()` → `ImpactEngine.analyze_impact()` → full result returned

### Demo Microservices

| Service | Port | Key Endpoints |
|---|---|---|
| user-service | 8001 | POST/GET/PUT/DELETE `/users`, GET `/users/{id}` |
| order-service | 8002 | POST/GET `/orders`, GET `/orders/{id}`, PATCH `/orders/{id}/status` |
| payment-service | 8003 | POST `/payments`, GET `/payments/{id}`, POST `/payments/{id}/refund`, GET `/payments/order/{order_id}` |
| notification-service | 8004 | POST `/notifications`, GET `/notifications`, GET `/notifications/{id}`, POST `/notifications/order/{id}/confirmation`, POST `/notifications/payment/{id}/receipt` |

---

## 6. Data Models

### `schemas/analysis.py`

```python
class SeverityLevel(str, Enum):
    LOW = "low" | MEDIUM = "medium" | HIGH = "high" | CRITICAL = "critical"

class DiffFile(BaseModel):
    path: str
    change_type: str        # added | modified | deleted
    lines_changed: int
    additions: int
    deletions: int

class ImpactResult(BaseModel):
    risk_score: float        # 0–100, rounded to 1dp
    severity: SeverityLevel
    impacted_services: List[str]
    confidence: float        # 0.5–0.95, dynamic from graph depth
    explanation: Optional[str]
    suggested_fixes: List[str]
    affected_files: List[DiffFile]
    dependency_chain: List[DependencyInfo]
```

---

## 7. Service Dependency Map

```
user-service (8001)          ← no dependencies
    ▲
    │ HTTP /users/{id}
order-service (8002)
    ▲
    │ HTTP /orders/{id}
payment-service (8003)
    ▲
    │ HTTP /orders/{id} + /payments/{id}
notification-service (8004)
```

**Impact propagation example** — change `payment_service/main.py`:
- Detected owner: `payment-service`
- Dependants: `notification-service` (depends on payment-service)
- Result: `["payment-service", "notification-service"]`

---

## 8. Infrastructure (Docker Compose)

| Container | Port | Notes |
|---|---|---|
| backend | 8000 | Main FastAPI app |
| user-service | 8001 | |
| order-service | 8002 | depends_on: user-service |
| payment-service | 8003 | |
| notification-service | 8004 | |
| neo4j | 7474 (HTTP), 7687 (bolt) | Persistent volume `neo4j_data` |
| chroma | 8005→8000 | Persistent volume `chroma_data` |

**To run full stack:** `docker-compose up -d`
**Backend local dev:** `cd backend && py -m uvicorn app:app --reload --port 8000`

---

## 9. Remaining TODOs

| Location | Gap | Priority |
|---|---|---|
| `api/analysis.py:get_analysis_history` | Returns empty list — no persistence | Phase 9 |
| `frontend/src/` | React dashboard not built | Phase 9 |
| `tests/` | Zero test files | Phase 10 |
| CORS `allow_origins=["*"]` | Must be restricted before production | Pre-deploy |
| `services/user_service/requirements.txt` | Has `sqlalchemy` but uses in-memory dict | Low |

---

## 10. Coding Conventions

- **Python**: PEP 8, `async/await` throughout, `logging.getLogger(__name__)` per module
- **Error handling**: `try/except` with graceful degradation — never crash on missing DB
- **Imports**: Optional DB packages (`neo4j`, `chromadb`) imported inside `try` blocks
- **Pydantic v2**: all schemas and settings use Pydantic v2
- **Import style**: absolute from `backend/` root (`sys.path` patched in `app.py`)
- **Fallback chain**: Neo4j → static map → safe maximum (for every graph operation)
- **Port convention**: backend=8000, user=8001, order=8002, payment=8003, notification=8004, chroma=8005

---

## 11. Environment Variables

```env
# Required for full AI features
OPENAI_API_KEY=sk-...
GITHUB_WEBHOOK_SECRET=your_secret
GITHUB_TOKEN=ghp_...          # PAT for GitHub API (optional — public repos work without)
NEO4J_PASSWORD=your_password

# Docker Compose defaults (work out of the box)
NEO4J_URI=bolt://neo4j:7687
NEO4J_USER=neo4j
CHROMADB_HOST=chroma
CHROMADB_PORT=8000

# Risk tuning (optional)
RISK_LOW=25
RISK_MEDIUM=50
RISK_HIGH=75
DEBUG=true
```

---

## 12. Webhook Setup (done)

- **Tunnel**: Cloudflare (`cloudflared tunnel --url http://localhost:8000`)
- **GitHub webhook URL**: `https://<tunnel>.trycloudflare.com/webhook/github`
- **Content-Type**: `application/json`
- **Secret**: matches `GITHUB_WEBHOOK_SECRET` in config
- **Event**: push only
- **Status**: ✅ Live — ping verified successful delivery
