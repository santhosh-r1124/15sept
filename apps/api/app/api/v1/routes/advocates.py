"""Advocate registration and self-service profile (Phase 1 slice).

Marketplace discovery/search is Phase 7; consultation booking is Phase 8. This
module only covers registering as an advocate and managing your own profile.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy import select

from app.api.deps import DbSession, SettingsDep, require_roles
from app.core import security
from app.core.errors import ConflictError, NotFoundError
from app.models.user import AdvocateProfile, EmailVerificationToken, User, UserRole
from app.schemas.advocate import (
    AdvocateProfileOut,
    AdvocateProfileUpdateRequest,
    AdvocateRegisterRequest,
)
from app.schemas.auth import TokenPair
from app.services.email import send_verification_email
from app.services.tokens import issue_token_pair

router = APIRouter()

# Only ADVOCATE-role accounts have (or may manage) an advocate profile.
AdvocateUser = Annotated[User, Depends(require_roles(UserRole.ADVOCATE))]


@router.post(
    "/register",
    response_model=TokenPair,
    status_code=status.HTTP_201_CREATED,
    summary="Register as an advocate",
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
