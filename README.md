# Microservice Drift Tracker (MDT)

An AI-Assisted Cross-Service Impact Analysis Framework for Microservice Architectures.

## Project Vision

Develop an intelligent software engineering platform that automatically detects how code changes in one microservice may affect other dependent microservices **before deployment**, helping developers identify risks early and reduce production failures.

## Architecture

```
Developer Push → GitHub Webhook → FastAPI Backend → Git Diff Analyzer → AST Parser
                                              ↓
                        ┌─────────────────────┴─────────────────────┐
                        ↓                      ↓                      ↓
                   Neo4j Graph           ChromaDB               HMDA Engine
                (Dependency Graph)    (Semantic Retrieval)    (Risk Scoring)
                        ↓                      ↓                      ↓
                        └──────────┬───────────┴───────────┬──────────┘
                                   ↓                        ↓
                              LLM Explanation     React Dashboard
```

## Quick Start

### Prerequisites
- Docker & Docker Compose
- Python 3.11+ (for local development)
- GitHub account with webhook access

### Run with Docker Compose

```bash
docker-compose up -d
```

This starts:
- **Backend API**: http://localhost:8000
- **User Service**: http://localhost:8001
- **Order Service**: http://localhost:8002
- **Payment Service**: http://localhost:8003
- **Notification Service**: http://localhost:8004
- **Neo4j**: http://localhost:7474
- **ChromaDB**: http://localhost:8005

### Local Development

```bash
# Backend
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# User Service
cd services/user_service
pip install -r requirements.txt
uvicorn main:app --reload --port 8001
```

## Microservices

| Service | Port | Description |
|---------|------|-------------|
| User Service | 8001 | User management |
| Order Service | 8002 | Order processing (depends on User) |
| Payment Service | 8003 | Payment processing (depends on Order) |
| Notification Service | 8004 | Notifications (depends on Order, Payment) |

## API Endpoints

### Backend API
- `GET /` - Service info
- `GET /health` - Health check
- `POST /webhook/github` - GitHub webhook endpoint
- `POST /analysis/analyze` - Manual impact analysis
- `GET /services/{name}` - Service health

### User Service (8001)
- `POST /users` - Create user
- `GET /users` - List users
- `GET /users/{id}` - Get user
- `PUT /users/{id}` - Update user
- `DELETE /users/{id}` - Delete user

## Environment Variables

Create `.env` files based on `.env.example` templates:

```
# Neo4j
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=password

# ChromaDB
CHROMADB_HOST=localhost

# GitHub
GITHUB_WEBHOOK_SECRET=your_secret

# OpenAI (optional)
OPENAI_API_KEY=your_key
```

## Project Structure

```
├── backend/
│   ├── api/           # FastAPI routes
│   ├── core/          # Configuration, database
│   ├── schemas/       # Pydantic models
│   ├── services/      # Business logic
│   │   ├── git_analyzer.py      # Git diff analysis
│   │   ├── impact_engine.py     # HMDA algorithm
│   │   ├── dependency_graph.py # Neo4j operations
│   │   ├── retrieval.py         # ChromaDB operations
│   │   └── llm_explainer.py     # LLM explanations
│   ├── main.py
│   └── requirements.txt
├── services/
│   ├── user_service/
│   ├── order_service/
│   ├── payment_service/
│   └── notification_service/
├── docker-compose.yml
└── README.md
```

## HMDA Algorithm (Hybrid Microservice Drift Algorithm)

The core innovation that combines:

1. **Deterministic Risk Scoring**
   - File count analysis
   - API change detection
   - Dependency depth calculation

2. **Semantic Retrieval (RAG)**
   - ChromaDB for code context
   - Similar change history
   - Risk modifier calculation

3. **AI-Assisted Reasoning**
   - LLM-generated explanations
   - Targeted remediation suggestions

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## License

MIT