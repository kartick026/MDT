"""
Database initialization — Neo4j and ChromaDB.
Both imports are optional: the app starts fine without them
(Docker containers may not be running in local dev).
"""
import logging
import asyncio
from typing import Optional, Any, Dict

from core.config import settings

logger = logging.getLogger(__name__)

neo4j_driver: Optional[Any] = None
chroma_client: Optional[Any] = None


class MockNeo4jTransaction:
    """Mock transaction for What-If sandbox simulations without live Neo4j."""
    def run(self, query: str, **params):
        return []

    def rollback(self):
        pass

    def commit(self):
        pass


class MockNeo4jSession:
    """Mock session supporting both async and sync execution contexts."""
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        pass

    def begin_transaction(self):
        return MockNeo4jTransaction()

    async def run(self, query: str, **params):
        class MockResult:
            async def data(self):
                return []
            def __iter__(self):
                return iter([])
        return MockResult()


class MockNeo4jDriver:
    """Mock Neo4j Driver for standalone local execution and unit tests."""
    is_mock: bool = True

    def verify_connectivity(self):
        pass

    def session(self):
        return MockNeo4jSession()

    def close(self):
        pass


async def init_databases():
    """Initialize database connections with connection pooling, TLS, and retry."""
    global neo4j_driver, chroma_client

    import os
    is_testing = os.getenv("TESTING", "").lower() in ("1", "true") or settings.DEBUG
    conn_timeout = 2.0 if is_testing else 15.0
    retries = 1 if is_testing else 3

    neo4j_opts: Dict[str, Any] = {
        "max_connection_pool_size": 50,
        "connection_acquisition_timeout": 5.0 if is_testing else 30.0,
        "connection_timeout": conn_timeout,
        "max_connection_lifetime": 3600,
    }

    # If TLS or AuraDB URI (neo4j+s:// or bolt+s://)
    if settings.NEO4J_URI.startswith(("neo4j+s://", "bolt+s://")):
        neo4j_opts["encrypted"] = True

    for attempt in range(retries):

        try:
            from neo4j import GraphDatabase  # type: ignore
            driver = GraphDatabase.driver(
                settings.NEO4J_URI,
                auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
                **neo4j_opts
            )
            driver.verify_connectivity()
            neo4j_driver = driver
            logger.info("Neo4j connected successfully: %s (pool_size=50)", settings.NEO4J_URI)
            break
        except Exception as exc:
            if attempt < retries - 1:
                logger.info("Neo4j connection attempt %d failed (%s). Retrying in 2s...", attempt + 1, exc)
                await asyncio.sleep(2.0)
            else:
                logger.warning("Real Neo4j connection failed after %d attempts (%s). Using MockNeo4jDriver.", retries, exc)
                neo4j_driver = MockNeo4jDriver()

    # --- ChromaDB ---
    try:
        import chromadb  # type: ignore
        if settings.CHROMADB_MODE.lower() == "server":
            chroma_client = chromadb.HttpClient(
                host=settings.CHROMADB_HOST,
                port=settings.CHROMADB_PORT,
            )
            client_description = (
                f"HTTP server mode at {settings.CHROMADB_HOST}:{settings.CHROMADB_PORT}"
            )
        else:
            chroma_client = chromadb.PersistentClient(path="./chroma_db")
            client_description = "persistent local mode at ./chroma_db"
        chroma_client.heartbeat()
        logger.info("ChromaDB connected (%s)", client_description)
    except Exception as exc:
        logger.warning("ChromaDB initialization failed: %s", exc)


def get_neo4j_driver() -> Optional[Any]:
    """Return the Neo4j driver singleton, or MockNeo4jDriver if closed / not connected."""
    global neo4j_driver
    if neo4j_driver is not None and getattr(neo4j_driver, "_closed", False):
        neo4j_driver = MockNeo4jDriver()
    return neo4j_driver


def get_chroma_client() -> Optional[Any]:
    """Return the ChromaDB client singleton, or None if not connected."""
    return chroma_client


def check_neo4j_health() -> Dict[str, Any]:
    """Return Neo4j connectivity status and driver details."""
    global neo4j_driver
    if neo4j_driver is None:
        return {"status": "uninitialized", "is_mock": True, "connected": False}
    if isinstance(neo4j_driver, MockNeo4jDriver) or getattr(neo4j_driver, "is_mock", False):
        # A mock keeps the application usable for local development, but it is
        # not a live graph database and must never be reported as one.
        return {"status": "mock_mode", "is_mock": True, "connected": False, "note": "Local mock active"}
    try:
        neo4j_driver.verify_connectivity()
        return {"status": "healthy", "is_mock": False, "connected": True, "uri": settings.NEO4J_URI}
    except Exception as exc:
        return {"status": "unhealthy", "is_mock": False, "connected": False, "error": str(exc)}


def check_chroma_health() -> Dict[str, Any]:
    """Return ChromaDB connectivity status."""
    global chroma_client
    if chroma_client is None:
        return {"status": "uninitialized", "connected": False}
    try:
        hb = chroma_client.heartbeat()
        return {"status": "healthy", "connected": True, "heartbeat": hb}
    except Exception as exc:
        return {"status": "unhealthy", "connected": False, "error": str(exc)}


async def close_databases():
    """Close database connections on shutdown."""
    global neo4j_driver
    if neo4j_driver:
        try:
            neo4j_driver.close()
            logger.info("Neo4j connection closed")
        except Exception:
            pass
        neo4j_driver = None
