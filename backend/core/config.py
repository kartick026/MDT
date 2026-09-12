"""Configuration settings for MDT Backend"""
from pydantic_settings import BaseSettings, SettingsConfigDict

from pydantic import Field, field_validator, model_validator
from typing import List, Union
import logging
import os
import secrets

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
    JWT_SECRET_KEY: str = Field(
        default="",
        description="JWT symmetric signing key (minimum 32 characters in production)"
    )
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
    GITHUB_WEBHOOK_SECRET: str = Field(
        default="",
        description="GitHub webhook HMAC signature secret"
    )
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
        """Prevent documented development credentials reaching production or staging,
        and generate high-entropy ephemeral secrets in development when unset."""
        env_clean = self.ENVIRONMENT.lower().strip()
        is_prod = env_clean in {"production", "prod", "staging", "stg", "uat"}

        known_insecure_jwt = {
            "mdt-production-super-secret-jwt-key-minimum-32-chars!",
            "change-this-to-a-secure-random-string-in-production-min-32-chars",
            "secret",
            "changeme",
            "password",
            "your_secret_key_here",
        }
        known_insecure_webhook = {
            "secret",
            "your_webhook_secret_here",
            "your-32-character-webhook-secret",
            "changeme",
        }

        # 1. JWT_SECRET_KEY validation & safe dev fallback
        current_jwt = self.JWT_SECRET_KEY.strip() if self.JWT_SECRET_KEY else ""
        if not current_jwt or current_jwt in known_insecure_jwt:
            if is_prod:
                raise ValueError(
                    f"[{env_clean.upper()}] Deployment configuration must set a secure JWT_SECRET_KEY (min 32 characters). "
                    f"Insecure default or empty key is strictly rejected."
                )
            self.JWT_SECRET_KEY = secrets.token_urlsafe(32)
            logger.warning("JWT_SECRET_KEY not set or using insecure default. Generated ephemeral development key.")
        elif is_prod and len(current_jwt) < 32:
            raise ValueError(
                f"[{env_clean.upper()}] JWT_SECRET_KEY must be at least 32 characters long in production (got {len(current_jwt)})."
            )
        else:
            self.JWT_SECRET_KEY = current_jwt

        # 2. GITHUB_WEBHOOK_SECRET validation & safe dev fallback
        current_webhook = self.GITHUB_WEBHOOK_SECRET.strip() if self.GITHUB_WEBHOOK_SECRET else ""
        if not current_webhook or current_webhook in known_insecure_webhook:
            if is_prod:
                raise ValueError(
                    f"[{env_clean.upper()}] Deployment configuration must set a secure GITHUB_WEBHOOK_SECRET. "
                    f"Insecure default or empty secret is strictly rejected."
                )
            self.GITHUB_WEBHOOK_SECRET = secrets.token_hex(20)
            logger.warning("GITHUB_WEBHOOK_SECRET not set or using insecure default. Generated ephemeral development secret.")
        else:
            self.GITHUB_WEBHOOK_SECRET = current_webhook

        # 3. Prevent development passwords in production
        if is_prod:
            insecure = {
                "ADMIN_PASSWORD": "admin123",
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
