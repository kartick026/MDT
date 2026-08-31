"""
MDT Backend Application
Main entry point for the Microservice Drift Tracker API
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from api import webhook, analysis, services, health, registry
from core.config import settings
from core.database import init_databases


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler"""
    # Startup — databases first, then graph schema + seed
    await init_databases()

    from services.dependency_graph import DependencyGraph
    graph = DependencyGraph()
    await graph.init_schema()   # creates constraints + seeds known services

    from services.smell_detector import SmellDetector
    await SmellDetector().snapshot_current_state()

    yield

    # Shutdown
    from core.database import close_databases
    await close_databases()


app = FastAPI(
    title="Microservice Drift Tracker",
    description="AI-Assisted Cross-Service Impact Analysis Framework",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(health.router, prefix="/health", tags=["Health"])
app.include_router(webhook.router, prefix="/webhook", tags=["Webhook"])
app.include_router(analysis.router, prefix="/analysis", tags=["Analysis"])
app.include_router(services.router, prefix="/services", tags=["Services"])
app.include_router(registry.router, prefix="/registry", tags=["Registry"])


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "name": "Microservice Drift Tracker",
        "version": "1.0.0",
        "status": "running"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
