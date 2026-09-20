"""FastAPI application factory.

Run locally:  uv run uvicorn app.main:app --reload --port 8000
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.api.v1.routes import health
from app.core.config import Settings, get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging, get_logger
from app.db.session import dispose_engine
from app.middleware.request_context import RequestContextMiddleware
from app.services.email import configure_email_sender
from app.services.redis import close_redis

logger = get_logger("app.main")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings
    configure_email_sender(settings)
    logger.info(
        "api_starting",
        environment=settings.app_env.value,
        version=settings.version,
    )
    try:
        yield
    finally:
        await dispose_engine()
        await close_redis()
        logger.info("api_stopped")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings)

    app = FastAPI(
        title="Legal Platform API",
        version=settings.version,
        description=(
            "Core backend for the Indian Legal Advisor Bot & Advocate Connect "
            "platform. Phase 0 skeleton."
        ),
        lifespan=lifespan,
        docs_url="/docs" if settings.docs_enabled else None,
        redoc_url="/redoc" if settings.docs_enabled else None,
        openapi_url="/openapi.json" if settings.docs_enabled else None,
    )
    app.state.settings = settings

    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )

    register_exception_handlers(app)

    app.include_router(health.router, tags=["health"])
    app.include_router(api_router, prefix="/api/v1")

    @app.get("/", include_in_schema=False)
    async def root() -> dict[str, str]:
        return {
            "service": settings.app_name,
            "version": settings.version,
            "docs": "/docs" if settings.docs_enabled else "disabled",
            "health": "/health",
        }

    return app


app = create_app()
