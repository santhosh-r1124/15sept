"""Issue an access/refresh token pair and persist the refresh token record."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import security
from app.core.config import Settings
from app.models.user import RefreshToken, User
from app.schemas.auth import TokenPair


async def issue_token_pair(*, user: User, db: AsyncSession, settings: Settings) -> TokenPair:
    """Create + persist a fresh access/refresh token pair for ``user``.

    Commits ``db`` — any pending changes from the caller (e.g. a newly created
    ``User`` row) are persisted together with the refresh token record in one
    transaction.
    """
    access_token = security.create_access_token(
        user_id=user.id, role=user.role.value, settings=settings
    )
    issued = security.create_refresh_token(user_id=user.id, role=user.role.value, settings=settings)
    db.add(
        RefreshToken(
            user_id=user.id,
            jti_hash=security.hash_token(issued.jti),
            expires_at=issued.expires_at,
        )
    )
    await db.commit()
    return TokenPair(
        access_token=access_token,
        refresh_token=issued.token,
        expires_in=settings.access_token_ttl_minutes * 60,
    )
