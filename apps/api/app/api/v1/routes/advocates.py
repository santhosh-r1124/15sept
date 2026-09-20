"""Advocate registration, self-service profile (Phase 1), and public
marketplace discovery (Phase 7).

Consultation booking is Phase 8 — search/profile here is read-only, there is
no "contact" or "book" action yet.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.api.deps import DbSession, SettingsDep, require_roles
from app.core import security
from app.core.errors import ConflictError, NotFoundError
from app.models.user import (
    AdvocateProfile,
    EmailVerificationToken,
    User,
    UserRole,
    VerificationStatus,
)
from app.schemas.advocate import (
    AdvocateDirectoryEntry,
    AdvocateProfileOut,
    AdvocateProfileUpdateRequest,
    AdvocateRegisterRequest,
    PaginatedAdvocateDirectory,
)
from app.schemas.auth import TokenPair
from app.services.email import send_verification_email
from app.services.rate_limit import rate_limit
from app.services.tokens import issue_token_pair

router = APIRouter()

# Only ADVOCATE-role accounts have (or may manage) an advocate profile.
AdvocateUser = Annotated[User, Depends(require_roles(UserRole.ADVOCATE))]
Limit = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0)]


def _directory_entry(profile: AdvocateProfile) -> AdvocateDirectoryEntry:
    return AdvocateDirectoryEntry(
        id=profile.id,
        display_name=profile.user.display_name,
        practice_areas=profile.practice_areas,
        state_code=profile.state_code,
        city=profile.city,
        languages=profile.languages,
        consultation_fee=profile.consultation_fee,
        bio=profile.bio,
        experience_years=profile.experience_years,
        availability=profile.availability,
    )


@router.post(
    "/register",
    response_model=TokenPair,
    status_code=status.HTTP_201_CREATED,
    summary="Register as an advocate",
    dependencies=[rate_limit("register", limit=5, window_seconds=3600)],
)
async def register_advocate(
    payload: AdvocateRegisterRequest, db: DbSession, settings: SettingsDep
) -> TokenPair:
    email = payload.email.lower()
    existing = await db.scalar(select(User).where(User.email == email))
    if existing is not None:
        raise ConflictError("An account with this email already exists.", code="email_taken")

    user = User(
        email=email,
        hashed_password=security.hash_password(payload.password),
        role=UserRole.ADVOCATE,
        display_name=payload.display_name,
        state_code=payload.state_code,
    )
    db.add(user)
    await db.flush()  # populate user.id for the profile + verification token below

    db.add(
        AdvocateProfile(
            user_id=user.id,
            practice_areas=payload.practice_areas,
            state_code=payload.state_code,
            city=payload.city,
            languages=payload.languages,
            consultation_fee=payload.consultation_fee,
            bio=payload.bio,
            experience_years=payload.experience_years,
        )
    )

    raw_token, token_hash = security.generate_one_time_token()
    db.add(
        EmailVerificationToken(
            user_id=user.id,
            token_hash=token_hash,
            expires_at=datetime.now(UTC) + timedelta(hours=settings.email_verification_ttl_hours),
        )
    )
    await send_verification_email(to=user.email, token=raw_token, settings=settings)

    return await issue_token_pair(user=user, db=db, settings=settings)


@router.get("/me", response_model=AdvocateProfileOut, summary="Get your advocate profile")
async def read_my_profile(user: AdvocateUser, db: DbSession) -> AdvocateProfileOut:
    profile = await db.scalar(select(AdvocateProfile).where(AdvocateProfile.user_id == user.id))
    if profile is None:
        raise NotFoundError("Advocate profile not found.")
    return AdvocateProfileOut.model_validate(profile)


@router.patch("/me", response_model=AdvocateProfileOut, summary="Update your advocate profile")
async def update_my_profile(
    payload: AdvocateProfileUpdateRequest, user: AdvocateUser, db: DbSession
) -> AdvocateProfileOut:
    profile = await db.scalar(select(AdvocateProfile).where(AdvocateProfile.user_id == user.id))
    if profile is None:
        raise NotFoundError("Advocate profile not found.")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(profile, field, value)
    await db.commit()
    await db.refresh(profile)
    return AdvocateProfileOut.model_validate(profile)


@router.get("", response_model=PaginatedAdvocateDirectory, summary="Search verified advocates")
async def search_advocates(
    db: DbSession,
    practice_area: str | None = None,
    state_code: str | None = None,
    city: str | None = None,
    language: str | None = None,
    min_experience_years: Annotated[int | None, Query(ge=0)] = None,
    max_consultation_fee: Annotated[Decimal | None, Query(ge=0)] = None,
    limit: Limit = 25,
    offset: Offset = 0,
) -> PaginatedAdvocateDirectory:
    """Public directory — only ever returns VERIFIED advocates (roadmap
    Phase 7). "Consultation type" and ratings/reviews filters from FRD §8
    aren't included: neither exists as real data yet (both are Phase 8
    concepts, once consultations exist to declare a type or leave a review).
    """
    conditions = [AdvocateProfile.verification_status == VerificationStatus.VERIFIED]
    if practice_area:
        # ARRAY.any(scalar) -> "scalar = ANY(array_column)"; mypy's stubs only
        # model the relationship-comparator overload of .any() (a boolean
        # criterion), not pgvector/ARRAY's scalar-value one — correct at
        # runtime, not statically typeable with the installed stubs.
        conditions.append(AdvocateProfile.practice_areas.any(practice_area))  # type: ignore[arg-type]
    if state_code:
        conditions.append(AdvocateProfile.state_code == state_code.upper())
    if city:
        conditions.append(AdvocateProfile.city.ilike(f"%{city}%"))
    if language:
        conditions.append(AdvocateProfile.languages.any(language))  # type: ignore[arg-type]
    if min_experience_years is not None:
        conditions.append(AdvocateProfile.experience_years >= min_experience_years)
    if max_consultation_fee is not None:
        conditions.append(AdvocateProfile.consultation_fee <= max_consultation_fee)

    count_stmt = select(func.count()).select_from(AdvocateProfile).where(*conditions)
    total = (await db.execute(count_stmt)).scalar_one()

    stmt = (
        select(AdvocateProfile)
        .options(selectinload(AdvocateProfile.user))
        .where(*conditions)
        .order_by(
            AdvocateProfile.experience_years.desc().nulls_last(),
            AdvocateProfile.created_at.desc(),
        )
        .limit(limit)
        .offset(offset)
    )
    rows = (await db.execute(stmt)).scalars().all()
    return PaginatedAdvocateDirectory(
        items=[_directory_entry(p) for p in rows], total=total, limit=limit, offset=offset
    )


@router.get(
    "/{profile_id}", response_model=AdvocateDirectoryEntry, summary="Get a verified advocate"
)
async def get_advocate(profile_id: uuid.UUID, db: DbSession) -> AdvocateDirectoryEntry:
    profile = await db.scalar(
        select(AdvocateProfile)
        .options(selectinload(AdvocateProfile.user))
        .where(
            AdvocateProfile.id == profile_id,
            AdvocateProfile.verification_status == VerificationStatus.VERIFIED,
        )
    )
    if profile is None:
        # Same 404 whether the id doesn't exist or exists but isn't verified —
        # an unverified advocate's profile isn't public, not even its existence.
        raise NotFoundError("Advocate not found.")
    return _directory_entry(profile)
