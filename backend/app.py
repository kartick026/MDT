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

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from api import webhook, analysis, services, health, registry, auth, projects
from core.auth import get_current_user
from core.store import get_store
from core.config import settings
from core.database import init_databases
from core.middleware import RequestTracingMiddleware, JSONLogFormatter, RequestSizeLimitMiddleware
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

    get_store()  # Fail readiness when durable storage is unavailable.
    tasks = []
    if settings.RUNTIME_PROFILE == "local":
        from services.dependency_graph import DependencyGraph
        from core.registry import RegistryManager
        from services.smell_detector import SmellDetector
        graph = DependencyGraph()
        await graph.init_schema()
        if RegistryManager.get_project_context().get("source") == "local_demo":
            await graph.seed_demo_history(RegistryManager.get_local_demo_smell_history())
        tasks.append(asyncio.create_task(SmellDetector().snapshot_current_state()))
    if os.getenv("TESTING", "").lower() not in {"1", "true"}:
        tasks.append(asyncio.create_task(projects.run_worker()))
    try:
        yield
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
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
app.add_middleware(RequestSizeLimitMiddleware)

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
app.include_router(projects.router, prefix="/v1", tags=["Projects and jobs"])
if settings.RUNTIME_PROFILE == "local":
    app.include_router(webhook.router, prefix="/webhook", tags=["Webhook"])
    for router, prefix, tag in ((analysis.router, "/analysis", "Analysis"), (services.router, "/services", "Services"), (registry.router, "/registry", "Registry")):
        app.include_router(router, prefix=prefix, tags=[tag], dependencies=[Depends(get_current_user)])


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
