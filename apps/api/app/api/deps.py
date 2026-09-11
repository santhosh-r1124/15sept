"""Shared FastAPI dependencies."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.db.session import get_session
from app.services.redis import get_redis


async def db_session() -> AsyncIterator[AsyncSession]:
    async for session in get_session():
        yield session


def redis_client() -> Redis:
    return get_redis()


SettingsDep = Annotated[Settings, Depends(get_settings)]
DbSession = Annotated[AsyncSession, Depends(db_session)]
RedisDep = Annotated[Redis, Depends(redis_client)]
