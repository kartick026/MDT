"""
MDT Backend Application
Main entry point for the Microservice Drift Tracker API
"""
import sys
import os
import asyncio
_backend_dir = os.path.dirname(os.path.abspath(__file__))
_root_dir = os.path.dirname(_backend_dir)
for _p in (_backend_dir, _root_dir):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from api import webhook, analysis, services, health, registry, auth
from core.config import settings
from core.database import init_databases
from core.middleware import RequestTracingMiddleware, JSONLogFormatter
import logging

# Configure root logger format & level
_log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
logging.basicConfig(level=_log_level)
if settings.LOG_FORMAT.lower() == "json":
    _root_logger = logging.getLogger()
    for _handler in _root_logger.handlers[:]:
        _root_logger.removeHandler(_handler)
    _json_handler = logging.StreamHandler(sys.stdout)
    _json_handler.setFormatter(JSONLogFormatter())
    _root_logger.addHandler(_json_handler)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler"""
    # Startup — databases first, then graph schema + seed
    await init_databases()

    from services.dependency_graph import DependencyGraph
    graph = DependencyGraph()
    await graph.init_schema()   # creates constraints + seeds known services
    from core.registry import RegistryManager
    if RegistryManager.get_project_context().get("source") == "local_demo":
        if hasattr(graph, "seed_demo_history"):
            await graph.seed_demo_history(RegistryManager.get_local_demo_smell_history())

    # Snapshotting is useful for trend detection, but it must not hold API
    # readiness hostage to optional service/OpenAPI probes.
    from services.smell_detector import SmellDetector
    snapshot_task = asyncio.create_task(SmellDetector().snapshot_current_state())

    yield

    # Shutdown
    if not snapshot_task.done():
        snapshot_task.cancel()
        await asyncio.gather(snapshot_task, return_exceptions=True)
    from core.database import close_databases
    await close_databases()


app = FastAPI(
    title="Microservice Drift Tracker",
    description="AI-Assisted Cross-Service Impact Analysis Framework",
    version="1.0.0",
    lifespan=lifespan
)

# Request tracing and latency logging middleware
app.add_middleware(RequestTracingMiddleware)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "X-Response-Time-MS"],
)

# Include routers
app.include_router(health.router, prefix="/health", tags=["Health"])
app.include_router(health.router, prefix="/api/v1/health", include_in_schema=False)
app.include_router(auth.router, prefix="/auth", tags=["Authentication"])
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
