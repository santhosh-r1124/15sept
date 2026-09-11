"""Shared pytest fixtures.

Config is forced to safe defaults before the app is imported so tests never
touch a developer's real ``.env``. ``pytest-asyncio`` runs in ``auto`` mode
(see pyproject), so ``async def test_*`` needs no marker.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator

import pytest

os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("LOG_FORMAT", "console")
os.environ.setdefault("LOG_LEVEL", "WARNING")
os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://legal:legal@localhost:5432/legal_platform_test"
)
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/1")
os.environ.setdefault("CORS_ORIGINS", "http://localhost:3000,http://localhost:3001")


@pytest.fixture
def app() -> Iterator[object]:
    from app.core.config import get_settings
    from app.main import create_app

    get_settings.cache_clear()
    yield create_app()
    get_settings.cache_clear()


@pytest.fixture
async def client(app: object) -> AsyncIterator[object]:
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=app)  # type: ignore[arg-type]
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac
