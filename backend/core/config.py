"""Configuration settings for MDT Backend"""
from pydantic_settings import BaseSettings
from typing import List
import os


class Settings(BaseSettings):
    """Application settings"""

    # Application
    APP_NAME: str = "Microservice Drift Tracker"
    VERSION: str = "1.0.0"
    DEBUG: bool = True
    ALLOWED_ORIGINS: List[str] = ["http://localhost:5173", "http://localhost:3000"]

    # Neo4j
    NEO4J_URI: str = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    NEO4J_USER: str = os.getenv("NEO4J_USER", "neo4j")
    NEO4J_PASSWORD: str = os.getenv("NEO4J_PASSWORD", "password")

    # ChromaDB
    CHROMADB_HOST: str = os.getenv("CHROMADB_HOST", "localhost")
    CHROMADB_PORT: int = 8000

    # GitHub
    GITHUB_WEBHOOK_SECRET: str = os.getenv("GITHUB_WEBHOOK_SECRET", "secret")
    GITHUB_TOKEN: str = os.getenv("GITHUB_TOKEN", "")  # PAT fallback
    GITHUB_APP_ID: str = os.getenv("GITHUB_APP_ID", "")
    GITHUB_APP_PRIVATE_KEY: str = os.getenv("GITHUB_APP_PRIVATE_KEY", "")

    # AI/LLM
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "gpt-4o-mini")
    LLM_BASE_URL: str = os.getenv("LLM_BASE_URL", "")   # leave blank for OpenAI; set to Gemini endpoint for Google
    EMBEDDING_MODEL: str = "text-embedding-ada-002"

    # Microservice URLs
    USER_SERVICE_URL: str = "http://user-service:8001"
    ORDER_SERVICE_URL: str = "http://order-service:8002"
    PAYMENT_SERVICE_URL: str = "http://payment-service:8003"
    NOTIFICATION_SERVICE_URL: str = "http://notification-service:8004"

    # Risk thresholds
    RISK_LOW: int = 25
    RISK_MEDIUM: int = 50
    RISK_HIGH: int = 75

    # Architectural-smell thresholds.  Set these per environment instead of
    # baking demo-sized limits into detector queries.
    SMELL_BOTTLENECK_INBOUND_THRESHOLD: int = 3
    SMELL_BOTTLENECK_TOTAL_DEGREE_THRESHOLD: int = 5
    SMELL_HIGH_COUPLING_THRESHOLD: int = 3
    SMELL_DEPENDENCY_GROWTH_THRESHOLD: int = 3
    SMELL_API_CHURN_THRESHOLD: int = 3

    class Config:
        env_file = ".env"


settings = Settings()
