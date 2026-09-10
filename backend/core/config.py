"""Configuration settings for MDT Backend"""
from pydantic_settings import BaseSettings, SettingsConfigDict

from pydantic import field_validator, model_validator
from typing import List, Union
import logging
import os

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """Application settings"""

    # Application
    APP_NAME: str = "Microservice Drift Tracker"
    VERSION: str = "1.0.0"
    ENVIRONMENT: str = "development"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "text"  # "text" or "json"
    ALLOWED_ORIGINS: Union[List[str], str] = ["http://localhost:5173", "http://localhost:3000"]

    # Authentication & JWT
    AUTH_REQUIRED: bool = True
    JWT_SECRET_KEY: str = "mdt-production-super-secret-jwt-key-minimum-32-chars!"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 24 hours
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str = "admin123"
    ALLOW_SELF_SIGNUP: bool = True
    ENABLE_DEFAULT_VIEWER: bool = True
    AUDITOR_USERNAME: str = "auditor"
    AUDITOR_PASSWORD: str = "auditor123"

    # Neo4j
    NEO4J_URI: str = "bolt://localhost:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = "password"

    # ChromaDB
    CHROMADB_MODE: str = "local"  # "local" (PersistentClient) or "server" (HttpClient)
    CHROMADB_HOST: str = "localhost"
    CHROMADB_PORT: int = 8000

    # GitHub Webhook Security
    GITHUB_WEBHOOK_SECRET: str = "secret"
    WEBHOOK_SIGNATURE_REQUIRED: bool = True
    RATE_LIMIT_WEBHOOK_PER_MINUTE: int = 30
    MAX_WEBHOOK_PAYLOAD_BYTES: int = 25 * 1024 * 1024  # 25 MB payload limit

    # GitHub Access Tokens
    GITHUB_TOKEN: str = ""  # PAT fallback
    GITHUB_APP_ID: str = ""
    GITHUB_APP_PRIVATE_KEY: str = ""

    # AI/LLM
    OPENAI_API_KEY: str = ""
    LLM_MODEL: str = "gemini-3.8-flash"
    LLM_BASE_URL: str = "https://generativelanguage.googleapis.com/v1beta/openai/"
    EMBEDDING_MODEL: str = "gemini-embedding-001"

    # Microservice URLs
    USER_SERVICE_URL: str = "http://user-service:8001"
    ORDER_SERVICE_URL: str = "http://order-service:8002"
    PAYMENT_SERVICE_URL: str = "http://payment-service:8003"
    NOTIFICATION_SERVICE_URL: str = "http://notification-service:8004"

    # Risk thresholds
    RISK_LOW: int = 25
    RISK_MEDIUM: int = 50
    RISK_HIGH: int = 75

    # Architectural-smell thresholds. Set these per environment instead of
    # baking demo-sized limits into detector queries.
    SMELL_BOTTLENECK_INBOUND_THRESHOLD: int = 3
    SMELL_BOTTLENECK_TOTAL_DEGREE_THRESHOLD: int = 5
    SMELL_HIGH_COUPLING_THRESHOLD: int = 3
    SMELL_DEPENDENCY_GROWTH_THRESHOLD: int = 3
    SMELL_API_CHURN_THRESHOLD: int = 3

    @field_validator("OPENAI_API_KEY")
    @classmethod
    def validate_api_key(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            logger.warning("OPENAI_API_KEY is empty. LLM analysis will use deterministic fallback.")
        elif any(placeholder in cleaned.lower() for placeholder in ("your_", "sk-proj-your", "placeholder")):
            logger.warning("OPENAI_API_KEY appears to be a placeholder: %s...", cleaned[:10])
        return cleaned

    @field_validator("ALLOWED_ORIGINS")
    @classmethod
    def parse_allowed_origins(cls, v: Union[List[str], str]) -> List[str]:
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    @model_validator(mode="after")
    def reject_demo_secrets_in_production(self):
        """Prevent documented development credentials reaching production or staging."""
        env_clean = self.ENVIRONMENT.lower().strip()
        if env_clean in {"production", "prod", "staging", "stg", "uat"}:
            insecure = {
                "JWT_SECRET_KEY": "mdt-production-super-secret-jwt-key-minimum-32-chars!",
                "ADMIN_PASSWORD": "admin123",
                "GITHUB_WEBHOOK_SECRET": "secret",
                "NEO4J_PASSWORD": "password",
            }
            if self.ENABLE_DEFAULT_VIEWER:
                insecure["AUDITOR_PASSWORD"] = "auditor123"

            unsafe_fields = [field for field, value in insecure.items() if getattr(self, field) == value]
            if unsafe_fields:
                raise ValueError(
                    f"[{env_clean.upper()}] Deployment configuration must replace development defaults: "
                    + ", ".join(unsafe_fields)
                )
        return self

    model_config = SettingsConfigDict(
        env_file=(
            os.path.join(os.path.dirname(__file__), "..", ".env"),
            "backend/.env",
            ".env",
        ),
        extra="ignore"
    )


settings = Settings()
