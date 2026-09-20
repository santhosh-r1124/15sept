"""Typed application configuration, loaded from the environment.

All runtime configuration flows through :func:`get_settings`. Nothing else in the
codebase should read ``os.environ`` directly.
"""

from __future__ import annotations

import enum
import json
from decimal import Decimal
from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Environment(enum.StrEnum):
    """Deployment environment. Drives logging, docs exposure and error verbosity."""

    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"

    @property
    def is_production(self) -> bool:
        return self is Environment.PRODUCTION

    @property
    def is_local(self) -> bool:
        return self is Environment.DEVELOPMENT


class Settings(BaseSettings):
    """Application settings.

    Field names map to UPPER_SNAKE_CASE environment variables (case-insensitive).
    Local development reads ``apps/api/.env``; in Docker/CI the process
    environment is populated from the repo-root ``.env`` / CI secrets.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ---- Runtime -----------------------------------------------------------
    app_env: Environment = Environment.DEVELOPMENT
    app_name: str = "legal-platform-api"
    version: str = "0.1.0"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    log_format: Literal["console", "json"] = "console"

    # ---- Database --------------------------------------------------------
    database_url: str = Field(
        default="postgresql+asyncpg://legal:legal_dev_password@localhost:5432/legal_platform",
        description="Async SQLAlchemy URL (asyncpg driver) used by the app.",
    )
    database_url_sync: str | None = Field(
        default=None,
        description="Sync SQLAlchemy URL (psycopg driver) used by Alembic. "
        "Derived from database_url when unset.",
    )
    database_echo: bool = False
    db_pool_size: int = 5
    db_max_overflow: int = 10
    db_pool_timeout_seconds: int = 30

    # ---- Redis ---------------------------------------------------------
    redis_url: str = "redis://localhost:6379/0"

    # ---- Security ----------------------------------------------------
    api_secret_key: str = "change-me-dev-only"
    jwt_secret: str = "change-me-dev-only"
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 30
    refresh_token_ttl_days: int = 14
    email_verification_ttl_hours: int = 24
    password_reset_ttl_hours: int = 1

    # ---- CORS ------------------------------------------------------
    # ``NoDecode`` stops pydantic-settings from JSON-parsing the env value; the
    # validator below accepts a comma-separated string or a JSON array.
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3000"]
    )

    # ---- LLM / RAG (Phase 2+) ----------------------------------------
    anthropic_api_key: str | None = None
    llm_model: str = "claude-sonnet-5"
    llm_max_tokens: int = 1024
    llm_classifier_max_tokens: int = 300
    # How many prior messages (user + assistant) to include as context.
    chat_history_length: int = 10

    # ---- Embeddings / knowledge base (Phase 3+) ------------------------
    # Google AI Studio key — free tier, no billing account required. Chosen
    # over paid embedding providers (Voyage/OpenAI) to keep the platform
    # runnable at zero cost; swap providers later by re-embedding.
    gemini_api_key: str | None = None
    embedding_model: str = "gemini-embedding-001"
    # gemini-embedding-001 supports Matryoshka truncation down from 3072;
    # 768 is Google's recommended efficiency/quality tradeoff point. Changing
    # this requires a new migration (the pgvector column dimension is fixed).
    embedding_dimensions: int = 768
    ingestion_max_source_bytes: int = 25 * 1024 * 1024
    ingestion_chunk_max_chars: int = 1500
    ingestion_chunk_overlap_chars: int = 200

    # ---- Payments (Phase 8+) ----------------------------------------------
    # "mock" always succeeds and is refused in production (app/services/payments).
    # The real gateway is chosen in Phase 10.
    payment_provider: str = "mock"
    # The platform's cut of each consultation/document fee. The FRD leaves the commission model
    # open ("subject to the applicable professional and regulatory framework", section 16), so
    # this defaults to 0 and needs the project owner's decision before launch.
    platform_fee_percent: Decimal = Decimal("0")

    # ---- Uploads (Phase 9+) ------------------------------------------------
    upload_dir: str = "./uploads"
    upload_max_bytes: int = 10 * 1024 * 1024

    # ---- Frontend (Phase 1+) ------------------------------------------
    # Base URL used to build links inside emails (verify-email, reset-password).
    frontend_base_url: str = "http://localhost:3000"
    # Where advocates land (notification emails to an advocate link into the portal).
    portal_base_url: str = "http://localhost:3001"

    # ---- Email (Phase 11) ----------------------------------------------------
    # "console" logs the email instead of sending it (free, needs no account). "smtp" sends via
    # any SMTP server - a free Gmail/Outlook app-password account works for low volume, or a
    # provider's free tier. No paid service is required or assumed.
    email_backend: Literal["console", "smtp"] = "console"
    email_from: str = "Legal Advisor <no-reply@localhost>"
    smtp_host: str = "localhost"
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    # STARTTLS on the submission port (587). Set false only for a local relay on a trusted network.
    smtp_starttls: bool = True
    smtp_timeout_seconds: int = 10

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_cors_origins(cls, value: object) -> object:
        """Accept a comma-separated string or a JSON array as well as a list."""
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return []
            if stripped.startswith("["):
                return json.loads(stripped)
            return [item.strip() for item in stripped.split(",") if item.strip()]
        return value

    @property
    def sqlalchemy_url_async(self) -> str:
        return self.database_url

    @property
    def sqlalchemy_url_sync(self) -> str:
        """Sync URL for Alembic. Falls back to swapping the async driver."""
        if self.database_url_sync:
            return self.database_url_sync
        return (
            self.database_url.replace("+asyncpg", "+psycopg")
            .replace("postgresql+asyncpg", "postgresql+psycopg")
            .replace("postgres://", "postgresql+psycopg://")
        )

    @property
    def docs_enabled(self) -> bool:
        """Expose interactive API docs everywhere except production."""
        return self.app_env is not Environment.PRODUCTION


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings singleton."""
    return Settings()
