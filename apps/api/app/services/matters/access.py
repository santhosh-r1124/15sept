"""Who is the caller, relative to a matter? Shared by every matter-scoped route.

Non-participants get a 404 rather than a 403 — a matter's existence isn't something to leak.
Admins may read any matter but never act on one (``readable_by`` allows them, ``require_actor``
doesn't).
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import NotFoundError
from app.models.matter import Matter
from app.models.user import AdvocateProfile, User, UserRole
from app.services.matters.lifecycle import Actor

ADMIN_ROLES = (UserRole.ADMIN, UserRole.LEGAL_ADMIN)

MATTER_LOAD_OPTIONS = (
    selectinload(Matter.consumer),
    selectinload(Matter.advocate_profile).selectinload(AdvocateProfile.user),
)


async def load_matter(db: AsyncSession, matter_id: uuid.UUID) -> Matter:
    matter = await db.scalar(
        select(Matter)
        .options(*MATTER_LOAD_OPTIONS)
        .where(Matter.id == matter_id)
        .execution_options(populate_existing=True)
    )
    if matter is None:
        raise NotFoundError("Matter not found.")
    return matter


def actor_for(user: User, matter: Matter) -> Actor | None:
    if matter.consumer_id == user.id:
        return Actor.CONSUMER
    if matter.advocate_profile.user_id == user.id:
        return Actor.ADVOCATE
    return None


def readable_by(user: User, matter: Matter) -> Actor | None:
    """The caller's role on this matter, or ``None`` for an admin (allowed to read);
    everyone else must be a participant."""
    actor = actor_for(user, matter)
    if actor is None and user.role not in ADMIN_ROLES:
        raise NotFoundError("Matter not found.")
    return actor


def require_actor(user: User, matter: Matter) -> Actor:
    actor = actor_for(user, matter)
    if actor is None:
        raise NotFoundError("Matter not found.")
    return actor
