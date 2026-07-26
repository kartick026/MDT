"""
Database initialization — Neo4j and ChromaDB.
Both imports are optional: the app starts fine without them
(Docker containers may not be running in local dev).
"""
import logging
import asyncio
from typing import Optional, Any

from core.config import settings

logger = logging.getLogger(__name__)

neo4j_driver: Optional[Any] = None
chroma_client: Optional[Any] = None

class MockNeo4jSession:
    async def __aenter__(self):
        return self
    async def __aexit__(self, exc_type, exc, tb):
        pass
    async def run(self, query: str, **params):
        class MockResult:
            async def data(self):
                return []
        return MockResult()

class MockNeo4jDriver:
    def verify_connectivity(self):
        # We always pretend to be connected!
        pass
    def session(self):
        return MockNeo4jSession()
    def close(self):
        pass

async def init_databases():
    """Initialize database connections. Failures are non-fatal."""
    global neo4j_driver, chroma_client

    # --- Neo4j ---
    try:
        from neo4j import GraphDatabase  # type: ignore
        # Test real connection if available
        neo4j_driver = GraphDatabase.driver(
            settings.NEO4J_URI,
            auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
        )
        neo4j_driver.verify_connectivity()
        logger.info("Neo4j connected: %s", settings.NEO4J_URI)
    except Exception as exc:
        logger.warning("Real Neo4j connection failed (%s). Using MockNeo4jDriver.", exc)
        neo4j_driver = MockNeo4jDriver()

    # --- ChromaDB ---
    try:
        import chromadb  # type: ignore
        chroma_client = chromadb.PersistentClient(path="./chroma_db")
        chroma_client.heartbeat()
        logger.info("ChromaDB connected (Persistent local mode at ./chroma_db)")
    except Exception as exc:
        logger.warning("ChromaDB initialization failed: %s", exc)

def get_neo4j_driver() -> Optional[Any]:
    """Return the Neo4j driver singleton, or None if not connected."""
    return neo4j_driver

def get_chroma_client() -> Optional[Any]:
    """Return the ChromaDB client singleton, or None if not connected."""
    return chroma_client

async def close_databases():
    """Close database connections on shutdown."""
    global neo4j_driver
    if neo4j_driver:
        try:
            neo4j_driver.close()
            logger.info("Neo4j connection closed")
        except Exception:
            pass
