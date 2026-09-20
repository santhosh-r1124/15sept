"""Admin: user management + advocate verification queue (Phase 1 slice).

The full Admin & Legal Ops dashboard (UI, reporting, RAG source management,
query review, etc.) is Phase 12. These endpoints exist now so RBAC and the
advocate verification workflow are real from Phase 1 — exercise them via
``/docs`` until Phase 12 ships a UI.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select

from app.api.deps import DbSession, SettingsDep, require_roles
from app.core.errors import ConflictError, NotFoundError
from app.models.user import AdvocateProfile, User, UserRole, VerificationStatus
from app.schemas.admin import PaginatedAdvocateProfiles, PaginatedUsers, UserActiveUpdateRequest
from app.schemas.advocate import AdvocateProfileOut, AdvocateRejectRequest, AdvocateVerifyRequest
from app.schemas.user import UserOut
from app.services.notifications import content as notice
from app.services.notifications import deliver_request_emails, notify

router = APIRouter()

AdminUser = Annotated[User, Depends(require_roles(UserRole.ADMIN, UserRole.LEGAL_ADMIN))]
Limit = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0)]


@router.get("/users", response_model=PaginatedUsers, summary="List users")
async def list_users(
    _admin: AdminUser,
    db: DbSession,
    role: UserRole | None = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    limit: Limit = 25,
    offset: Offset = 0,
) -> PaginatedUsers:
    stmt = select(User)
    count_stmt = select(func.count()).select_from(User)
    if role is not None:
        stmt = stmt.where(User.role == role)
        count_stmt = count_stmt.where(User.role == role)
    if q:
        # Substring match on email / name; escape LIKE wildcards so "100%" means 100%.
        escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped}%"
        match = or_(
            User.email.ilike(pattern, escape="\\"), User.display_name.ilike(pattern, escape="\\")
        )
        stmt = stmt.where(match)
        count_stmt = count_stmt.where(match)

    total = (await db.execute(count_stmt)).scalar_one()
    rows = (
        (await db.execute(stmt.order_by(User.created_at.desc()).limit(limit).offset(offset)))
        .scalars()
        .all()
    )
    return PaginatedUsers(
        items=[UserOut.model_validate(u) for u in rows], total=total, limit=limit, offset=offset
    )


@router.patch("/users/{user_id}", response_model=UserOut, summary="Activate or suspend a user")
async def set_user_active(
    user_id: uuid.UUID, payload: UserActiveUpdateRequest, admin: AdminUser, db: DbSession
) -> UserOut:
    user = await db.get(User, user_id)
    if user is None:
        raise NotFoundError("User not found.")
    if user.id == admin.id and not payload.is_active:
        # An admin suspending themselves would lock the last person who can undo it out.
        raise ConflictError("You can't suspend your own account.", code="cannot_suspend_self")
    user.is_active = payload.is_active
    await db.commit()
    await db.refresh(user)
    return UserOut.model_validate(user)


@router.get(
    "/advocates/pending",
    response_model=PaginatedAdvocateProfiles,
    summary="List advocates awaiting verification",
)
async def list_pending_advocates(
    _admin: AdminUser, db: DbSession, limit: Limit = 25, offset: Offset = 0
) -> PaginatedAdvocateProfiles:
    statuses = (VerificationStatus.PENDING, VerificationStatus.IN_REVIEW)
    stmt = select(AdvocateProfile).where(AdvocateProfile.verification_status.in_(statuses))
    count_stmt = (
        select(func.count())
        .select_from(AdvocateProfile)
        .where(AdvocateProfile.verification_status.in_(statuses))
    )

    total = (await db.execute(count_stmt)).scalar_one()
    rows = (
        (
            await db.execute(
                stmt.order_by(AdvocateProfile.created_at.asc()).limit(limit).offset(offset)
            )
        )
        .scalars()
        .all()
    )
    return PaginatedAdvocateProfiles(
        items=[AdvocateProfileOut.model_validate(p) for p in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/advocates/{profile_id}/verify",
    response_model=AdvocateProfileOut,
    summary="Approve an advocate",
)
async def verify_advocate(
    profile_id: uuid.UUID,
    payload: AdvocateVerifyRequest,
    _admin: AdminUser,
    db: DbSession,
    settings: SettingsDep,
) -> AdvocateProfileOut:
    profile = await db.get(AdvocateProfile, profile_id)
    if profile is None:
        raise NotFoundError("Advocate profile not found.")
    profile.verification_status = VerificationStatus.VERIFIED
    profile.verification_note = payload.note
    advocate = await db.get(User, profile.user_id)
    if advocate is not None:
        await notify(db, settings, advocate, notice.advocate_verified())
    await db.commit()
    await deliver_request_emails(db)
    await db.refresh(profile)
    return AdvocateProfileOut.model_validate(profile)


@router.post(
    "/advocates/{profile_id}/reject",
    response_model=AdvocateProfileOut,
    summary="Reject an advocate",
)
async def reject_advocate(
    profile_id: uuid.UUID,
    payload: AdvocateRejectRequest,
    _admin: AdminUser,
    db: DbSession,
    settings: SettingsDep,
) -> AdvocateProfileOut:
    profile = await db.get(AdvocateProfile, profile_id)
    if profile is None:
        raise NotFoundError("Advocate profile not found.")
    profile.verification_status = VerificationStatus.REJECTED
    profile.verification_note = payload.note
    advocate = await db.get(User, profile.user_id)
    if advocate is not None:
        await notify(db, settings, advocate, notice.advocate_rejected(note=payload.note))
    await db.commit()
    await deliver_request_emails(db)
    await db.refresh(profile)
    return AdvocateProfileOut.model_validate(profile)
