"""Database initialization for Neo4j and ChromaDB"""
import logging
from typing import Optional
from neo4j import GraphDatabase
import chromadb

from core.config import settings

logger = logging.getLogger(__name__)

neo4j_driver: Optional[GraphDatabase.driver] = None
chroma_client: Optional[chromadb.Client] = None


async def init_databases():
    """Initialize database connections"""
    global neo4j_driver, chroma_client

    try:
        # Init Neo4j
        neo4j_driver = GraphDatabase.driver(
            settings.NEO4J_URI,
            auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD)
        )
        logger.info("Neo4j connected successfully")
    except Exception as e:
        logger.warning(f"Neo4j connection failed: {e}")

    try:
        # Init ChromaDB
        chroma_client = chromadb.Client()
        logger.info("ChromaDB connected successfully")
    except Exception as e:
        logger.warning(f"ChromaDB connection failed: {e}")


def get_neo4j_driver():
    """Get Neo4j driver instance"""
    return neo4j_driver


def get_chroma_client():
    """Get ChromaDB client instance"""
    return chroma_client


async def close_databases():
    """Close database connections"""
    global neo4j_driver
    if neo4j_driver:
        neo4j_driver.close()
        logger.info("Neo4j connection closed")