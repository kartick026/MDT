"""
Neo4j Dependency Graph Service
Manages service dependencies and traversal
"""
import logging
from typing import List, Dict, Any, Optional
from core.database import get_neo4j_driver
from core.config import settings

logger = logging.getLogger(__name__)


class DependencyGraph:
    """
    Manages service dependency graph in Neo4j
    Provides traversal and impact analysis queries
    """

    def __init__(self):
        self.driver = get_neo4j_driver()

    async def init_schema(self):
        """Initialize Neo4j schema for MDT"""
        if not self.driver:
            logger.warning("Neo4j not connected, skipping schema init")
            return

        async with self.driver.session() as session:
            # Create constraints and indexes
            await session.run("""
                CREATE CONSTRAINT service_name IF NOT EXISTS
                FOR (s:Service) REQUIRE s.name IS UNIQUE
            """)

            await session.run("""
                CREATE CONSTRAINT file_path IF NOT EXISTS
                FOR (f:File) REQUIRE f.path IS UNIQUE
            """)

            logger.info("Neo4j schema initialized")

    async def add_service(self, name: str, metadata: Dict[str, Any]):
        """Add a service node to the graph"""
        if not self.driver:
            return

        async with self.driver.session() as session:
            await session.run("""
                MERGE (s:Service {name: $name})
                SET s += $metadata
            """, name=name, metadata=metadata)

    async def add_dependency(
        self,
        from_service: str,
        to_service: str,
        dependency_type: str = "http"
    ):
        """Add a dependency relationship between services"""
        if not self.driver:
            return

        async with self.driver.session() as session:
            await session.run("""
                MATCH (from:Service {name: $from})
                MATCH (to:Service {name: $to})
                MERGE (from)-[d:DEPENDS_ON {
                    type: $dep_type,
                    created_at: datetime()
                }]->(to)
            """, from_=from_service, to=to_service, dep_type=dependency_type)

    async def get_affected_services(self, file_path: str) -> List[str]:
        """
        Get all services that might be affected by changes to a file
        Uses backward traversal from the changed file
        """
        if not self.driver:
            # Fallback: return all known services
            return ["user-service", "order-service", "payment-service", "notification-service"]

        async with self.driver.session() as session:
            result = await session.run("""
                MATCH (f:File {path: $path})
                OPTIONAL MATCH (f)<-[:DEFINES_FILE]-(s:Service)
                OPTIONAL MATCH (s)-[:DEPENDS_ON*1..3]->(affected:Service)
                RETURN DISTINCT affected.name AS service_name
            """, path=file_path)

            records = await result.data()
            return [r["service_name"] for r in records if r.get("service_name")]

    async def get_dependency_chain(
        self,
        service_name: str,
        depth: int = 3
    ) -> List[Dict[str, Any]]:
        """Get the dependency chain for a service"""
        if not self.driver:
            return []

        async with self.driver.session() as session:
            result = await session.run("""
                MATCH path = (s:Service {name: $name})-[:DEPENDS_ON*1..%d]->(other:Service)
                RETURN path
            """ % depth, name=service_name)

            records = await result.data()
            return [self._path_to_dict(r["path"]) for r in records]

    async def add_file(self, path: str, service: str, metadata: Dict[str, Any]):
        """Add a file node and link to its service"""
        if not self.driver:
            return

        async with self.driver.session() as session:
            await session.run("""
                MATCH (s:Service {name: $service})
                MERGE (f:File {path: $path})
                SET f += $metadata
                MERGE (s)-[:DEFINES_FILE]->(f)
            """, service=service, path=path, metadata=metadata)

    def _path_to_dict(self, path) -> Dict[str, Any]:
        """Convert a Neo4j path to dictionary format"""
        # Simplified path conversion
        return {"nodes": [n.element_id for n in path.nodes]}