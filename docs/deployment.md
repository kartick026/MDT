# Microservice Drift Tracker (MDT) — Production Deployment Guide

This guide details the end-to-end deployment, container orchestration, and security hardening process for **Microservice Drift Tracker (MDT)** in staging and production environments.

---

## 1. System Architecture & Port Allocations

A full MDT cluster consists of the drift engine, graph store, vector database, web dashboard, and optionally a fleet of sample microservices:

| Service Container | Internal Port | Host Port | Purpose |
|-------------------|---------------|-----------|---------|
| **`project1-frontend`** | `80` (nginx) | `5173` | React / Vite Dashboard with Glassmorphic UI |
| **`project1-backend`** | `8000` | `8000` | FastAPI Core API, HMDA Engine, AST Analyzers |
| **`project1-neo4j`** | `7474`, `7687` | `7474`, `7687` | Cypher Graph Database (Topology & Smell Detection) |
| **`project1-chroma`** | `8005` | `8005` | ChromaDB Vector Database (Semantic Context RAG) |
| **`user-service`** | `8001` | `8001` | Reference Microservice (User management) |
| **`order-service`** | `8002` | `8002` | Reference Microservice (Order processing) |
| **`payment-service`** | `8003` | `8003` | Reference Microservice (Payment gateway) |
| **`notification-service`**| `8004` | `8004` | Reference Microservice (Event dispatching) |

---

## 2. Environment Variables & Secrets Configuration

Create a production `.env` file in the root directory (or in `backend/.env`):

```bash
# ── NEO4J CONFIGURATION ──
NEO4J_URI=bolt://neo4j:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=StrongProductionPassword123!

# ── CHROMADB VECTOR DATABASE ──
CHROMADB_HOST=chroma
CHROMADB_PORT=8000 # Internal container port inside Docker network (use 8005 only if running backend directly on host machine)

# ── OPENAI / AI REASONING (OPTIONAL FOR LLM EXPLAINER) ──
OPENAI_API_KEY=sk-proj-your-openai-api-key

# ── GITHUB INTEGRATION ──
# Personal Access Token (for manual imports and commit fetching)
GITHUB_TOKEN=ghp_yourPersonalAccessTokenHere

# GitHub App Configuration (Recommended for Organizations)
GITHUB_APP_ID=123456
GITHUB_APP_PRIVATE_KEY="-----BEGIN RSA PRIVATE KEY-----\nMIIE...\n-----END RSA PRIVATE KEY-----"
GITHUB_WEBHOOK_SECRET=your-secure-random-webhook-secret-here

# ── APPLICATION SETTINGS ──
DEBUG=False
ALLOWED_ORIGINS=["http://localhost:5173","https://mdt.yourdomain.com"]
```

---

## 3. Deployment with Docker Compose

The standard deployment uses Docker Compose to orchestrate all containers on a shared bridge network (`project1-network`).

```bash
# 1. Clone repository
git clone https://github.com/kartick026/MDT.git
cd MDT

# 2. Configure production variables
cp backend/.env.example .env
nano .env

# 3. Build images and start all services in detached mode
docker compose up -d --build
```

### Checking Container Health
Verify that all containers are healthy:
```bash
docker compose ps
```
Output:
```
NAME                    IMAGE                       STATUS
project1-backend-1      project1-backend            Up (healthy)
project1-chroma-1       chromadb/chroma:0.4.22      Up
project1-frontend-1     project1-frontend           Up
project1-neo4j-1        neo4j:5.16-community        Up (healthy)
```

---

## 4. Reverse Proxy & SSL Configuration (Nginx / Cloudflare)

In production, place the frontend and backend behind a unified reverse proxy (such as Nginx or AWS ALB) terminating SSL:

```nginx
# Example Nginx Virtual Host
server {
    listen 443 ssl http2;
    server_name mdt.yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/mdt.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/mdt.yourdomain.com/privkey.pem;

    # Frontend Single Page App
    location / {
        proxy_pass http://127.0.0.1:5173;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Backend API & Webhooks
    location ~ ^/(services|analysis|api|webhook|health|openapi\.json|docs) {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

---

## 5. Persistent Volumes & Data Backups

Ensure the following Docker volumes are attached to persistent block storage:
- **`neo4j_data`**: Stores the topology graph, registered nodes, edges, and historical analysis events.
- **`chroma_data`**: Stores the code embeddings and semantic retrieval index.

To perform a backup of the Neo4j database:
```bash
docker compose exec neo4j neo4j-admin database dump neo4j --to-path=/var/lib/neo4j/import/backup.dump
```

---

## 6. Post-Deployment Verification Checklist

1. **Verify Backend Liveness:**
   ```bash
   curl -I http://localhost:8000/health
   # Expected: HTTP/1.1 200 OK
   ```
2. **Verify Detailed Subsystem Connectivity:**
   ```bash
   curl http://localhost:8000/health/detailed
   # Expected: {"status":"healthy","components":{"neo4j":"connected","chroma":"connected"}}
   ```
3. **Verify Web Dashboard:**
   Open `http://localhost:5173` in a browser. Ensure the top navbar displays `● All Systems Go` or `○ Services Imported` and the Overview cards load.
4. **Trigger a Test Analysis:**
   Run an impact analysis for `main` on the target repository to verify graph traversal, AI explanations, and What-If preview simulations.
