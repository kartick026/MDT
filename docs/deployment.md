# Microservice Drift Tracker (MDT) Deployment Guide

This guide details the deployment process for MDT in a production environment.

## 1. Environment Preparation

Ensure the following environment variables are properly configured in your `.env` file before deploying:

- `OPENAI_API_KEY`: Required for LLM explanations and accurate semantic embeddings.
- `GITHUB_WEBHOOK_SECRET`: Used to verify payload signatures. Ensure it is a secure random string.
- `GITHUB_TOKEN`: Ensure this PAT has read access to the target repositories.
- `NEO4J_PASSWORD`: Change from default `password`.
- `DEBUG`: Must be set to `False` in production to enforce webhook signature verification.

## 2. Security Hardening

- **CORS Policy:** The backend CORS policy has been restricted. Ensure `ALLOWED_ORIGINS` in `backend/core/config.py` matches your production frontend URLs. 
- **Webhook Exposure:** The backend exposes `/webhook/github`. It is recommended to put this behind an API gateway or reverse proxy (e.g., Nginx, Cloudflare) with rate limiting enabled.

## 3. Infrastructure & Deployment

The easiest way to deploy MDT is via Docker Compose.

```bash
# 1. Clone the repository on the production server
git clone https://github.com/kartick026/MDT.git
cd MDT

# 2. Configure environment
cp backend/.env.example backend/.env
nano backend/.env # Set secrets

# 3. Build and run detached
docker-compose up -d --build
```

### Component Scaling

- **ChromaDB**: Needs a persistent volume (`chroma_data`).
- **Neo4j**: Needs a persistent volume (`neo4j_data`).
- **Backend API**: Can be scaled horizontally. Ensure they all point to the same Neo4j and ChromaDB instances.

## 4. Monitoring

Monitor the `/health/detailed` endpoint to verify connectivity to Neo4j and ChromaDB. This endpoint returns the status of the semantic context index and graph database seeding.
