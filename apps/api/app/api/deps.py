"""Shared FastAPI dependencies."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Annotated

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import security
from app.core.config import Settings, get_settings
from app.core.errors import ForbiddenError, UnauthorizedError
from app.db.session import get_session
from app.models.user import User, UserRole
from app.services.redis import get_redis


async def db_session() -> AsyncIterator[AsyncSession]:
    async for session in get_session():
        yield session


def redis_client() -> Redis:
    return get_redis()


SettingsDep = Annotated[Settings, Depends(get_settings)]
DbSession = Annotated[AsyncSession, Depends(db_session)]
RedisDep = Annotated[Redis, Depends(redis_client)]

# ``auto_error=False`` so a missing header raises our own ``UnauthorizedError``
# (consistent error envelope) instead of Starlette's default 403.
_bearer_scheme = HTTPBearer(
    auto_error=False, description="Access token from /auth/login or /auth/register."
)
BearerCredentials = Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)]


async def get_current_user(
    settings: SettingsDep, db: DbSession, credentials: BearerCredentials
) -> User:
    if credentials is None:
        raise UnauthorizedError("Missing bearer token.")
    try:
        payload = security.decode_token(
            credentials.credentials, settings=settings, expected_type="access"
        )
    except jwt.PyJWTError as exc:
        raise UnauthorizedError("Invalid or expired access token.") from exc

    subject = payload.get("sub")
    if not isinstance(subject, str):
        raise UnauthorizedError("Malformed access token.")
    try:
        user_id = uuid.UUID(subject)
    except ValueError as exc:
        raise UnauthorizedError("Malformed access token.") from exc

    user = await db.get(User, user_id)
    if user is None or not user.is_active:
        raise UnauthorizedError("User not found or inactive.")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def get_current_user_optional(
    settings: SettingsDep, db: DbSession, credentials: BearerCredentials
) -> User | None:
    """Like :func:`get_current_user`, but returns ``None`` instead of raising.

    For endpoints usable both anonymously and while logged in (public-tier
    chat) — any bearer token present is still validated; a missing, malformed
    or invalid one just means "anonymous", not an error.
    """
    if credentials is None:
        return None
    try:
        payload = security.decode_token(
            credentials.credentials, settings=settings, expected_type="access"
        )
    except jwt.PyJWTError:
        return None

    subject = payload.get("sub")
    if not isinstance(subject, str):
        return None
    try:
        user_id = uuid.UUID(subject)
    except ValueError:
        return None

    user = await db.get(User, user_id)
    if user is None or not user.is_active:
        return None
    return user


OptionalUser = Annotated[User | None, Depends(get_current_user_optional)]


def require_roles(*roles: UserRole) -> Callable[[User], Awaitable[User]]:
    """Dependency factory: 403s unless the current user has one of ``roles``.

    Usage: ``current_admin: Annotated[User, Depends(require_roles(UserRole.ADMIN))]``
    """

    async def _dependency(user: CurrentUser) -> User:
        if user.role not in roles:
            raise ForbiddenError("You do not have permission to perform this action.")
        return user

    return _dependency
