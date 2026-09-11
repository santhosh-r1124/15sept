"""Authentication flows: register, login, refresh, logout, verify email, password reset.

Admins and legal-admins log in through the same `/login` — there is no separate
admin endpoint. RBAC (``role``) is what differentiates access, not the login
path. Bootstrap the first admin with ``uv run python -m app.scripts.create_admin``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import jwt
from fastapi import APIRouter, status
from sqlalchemy import select, update

from app.api.deps import DbSession, SettingsDep
from app.core import security
from app.core.errors import ConflictError, NotFoundError, UnauthorizedError, ValidationAppError
from app.core.logging import get_logger
from app.models.user import EmailVerificationToken, PasswordResetToken, RefreshToken, User, UserRole
from app.schemas.auth import (
    ForgotPasswordRequest,
    LoginRequest,
    LogoutRequest,
    MessageResponse,
    RefreshRequest,
    RegisterRequest,
    ResendVerificationRequest,
    ResetPasswordRequest,
    TokenPair,
    VerifyEmailRequest,
)
from app.services.email import send_password_reset_email, send_verification_email
from app.services.tokens import issue_token_pair

logger = get_logger("app.auth")

router = APIRouter()


@router.post(
    "/register",
    response_model=TokenPair,
    status_code=status.HTTP_201_CREATED,
    summary="Register a consumer account",
)
async def register(payload: RegisterRequest, db: DbSession, settings: SettingsDep) -> TokenPair:
    email = payload.email.lower()
    existing = await db.scalar(select(User).where(User.email == email))
    if existing is not None:
        raise ConflictError("An account with this email already exists.", code="email_taken")

    user = User(
        email=email,
        hashed_password=security.hash_password(payload.password),
        role=UserRole.CONSUMER,
        display_name=payload.display_name,
        state_code=payload.state_code,
        preferred_language=payload.preferred_language,
    )
    db.add(user)
    await db.flush()  # populate user.id before referencing it below

    raw_token, token_hash = security.generate_one_time_token()
    db.add(
        EmailVerificationToken(
            user_id=user.id,
            token_hash=token_hash,
            expires_at=datetime.now(UTC) + timedelta(hours=settings.email_verification_ttl_hours),
        )
    )
    await send_verification_email(to=user.email, token=raw_token, settings=settings)

    logger.info("user_registered", user_id=str(user.id), role=user.role.value)
    return await issue_token_pair(user=user, db=db, settings=settings)


@router.post("/login", response_model=TokenPair, summary="Log in")
async def login(payload: LoginRequest, db: DbSession, settings: SettingsDep) -> TokenPair:
    user = await db.scalar(select(User).where(User.email == payload.email.lower()))
    if user is None or not security.verify_password(payload.password, user.hashed_password):
        raise UnauthorizedError("Incorrect email or password.", code="invalid_credentials")
    if not user.is_active:
        raise UnauthorizedError("This account has been deactivated.", code="account_inactive")

    logger.info("user_logged_in", user_id=str(user.id))
    return await issue_token_pair(user=user, db=db, settings=settings)


@router.post("/refresh", response_model=TokenPair, summary="Rotate the access/refresh token pair")
async def refresh(payload: RefreshRequest, db: DbSession, settings: SettingsDep) -> TokenPair:
    try:
        decoded = security.decode_token(
            payload.refresh_token, settings=settings, expected_type="refresh"
        )
    except jwt.PyJWTError as exc:
        raise UnauthorizedError("Invalid or expired refresh token.") from exc

    jti = decoded.get("jti")
    subject = decoded.get("sub")
    if not isinstance(jti, str) or not isinstance(subject, str):
        raise UnauthorizedError("Malformed refresh token.")

    record = await db.scalar(
        select(RefreshToken).where(RefreshToken.jti_hash == security.hash_token(jti))
    )
    if record is None or record.revoked_at is not None or record.expires_at < datetime.now(UTC):
        raise UnauthorizedError("Refresh token has been revoked or expired.")

    try:
        user_id = uuid.UUID(subject)
    except ValueError as exc:
        raise UnauthorizedError("Malformed refresh token.") from exc

    user = await db.get(User, user_id)
    if user is None or not user.is_active:
        raise UnauthorizedError("User not found or inactive.")

    record.revoked_at = datetime.now(UTC)  # single-use: rotate on every refresh
    return await issue_token_pair(user=user, db=db, settings=settings)


@router.post("/logout", response_model=MessageResponse, summary="Revoke a refresh token")
async def logout(payload: LogoutRequest, db: DbSession, settings: SettingsDep) -> MessageResponse:
    try:
        decoded = security.decode_token(
            payload.refresh_token, settings=settings, expected_type="refresh"
        )
    except jwt.PyJWTError:
        # Already invalid/expired — logout is idempotent either way.
        return MessageResponse(message="Logged out.")

    jti = decoded.get("jti")
    if isinstance(jti, str):
        record = await db.scalar(
            select(RefreshToken).where(RefreshToken.jti_hash == security.hash_token(jti))
        )
        if record is not None and record.revoked_at is None:
            record.revoked_at = datetime.now(UTC)
            await db.commit()
    return MessageResponse(message="Logged out.")


@router.post("/verify-email", response_model=MessageResponse, summary="Verify an email address")
async def verify_email(payload: VerifyEmailRequest, db: DbSession) -> MessageResponse:
    token_hash = security.hash_token(payload.token)
    record = await db.scalar(
        select(EmailVerificationToken).where(EmailVerificationToken.token_hash == token_hash)
    )
    if record is None or record.used_at is not None or record.expires_at < datetime.now(UTC):
        raise ValidationAppError(
            "This verification link is invalid or has expired.", code="invalid_token"
        )

    user = await db.get(User, record.user_id)
    if user is None:
        raise NotFoundError("User not found.")

    user.email_verified = True
    record.used_at = datetime.now(UTC)
    await db.commit()
    return MessageResponse(message="Email verified.")


@router.post(
    "/resend-verification", response_model=MessageResponse, summary="Resend the verification email"
)
async def resend_verification(
    payload: ResendVerificationRequest, db: DbSession, settings: SettingsDep
) -> MessageResponse:
    user = await db.scalar(select(User).where(User.email == payload.email.lower()))
    # Same response either way — don't leak whether the email exists or is verified.
    if user is not None and not user.email_verified:
        raw_token, token_hash = security.generate_one_time_token()
        db.add(
            EmailVerificationToken(
                user_id=user.id,
                token_hash=token_hash,
                expires_at=datetime.now(UTC)
                + timedelta(hours=settings.email_verification_ttl_hours),
            )
        )
        await db.commit()
        await send_verification_email(to=user.email, token=raw_token, settings=settings)
    return MessageResponse(
        message="If that email exists and is unverified, a new link has been sent."
    )


@router.post(
    "/forgot-password", response_model=MessageResponse, summary="Request a password reset link"
)
async def forgot_password(
    payload: ForgotPasswordRequest, db: DbSession, settings: SettingsDep
) -> MessageResponse:
    user = await db.scalar(select(User).where(User.email == payload.email.lower()))
    if user is not None:
        raw_token, token_hash = security.generate_one_time_token()
        db.add(
            PasswordResetToken(
                user_id=user.id,
                token_hash=token_hash,
                expires_at=datetime.now(UTC) + timedelta(hours=settings.password_reset_ttl_hours),
            )
        )
        await db.commit()
        await send_password_reset_email(to=user.email, token=raw_token, settings=settings)
    return MessageResponse(message="If that email exists, a reset link has been sent.")


@router.post(
    "/reset-password", response_model=MessageResponse, summary="Reset password using a reset token"
)
async def reset_password(payload: ResetPasswordRequest, db: DbSession) -> MessageResponse:
    token_hash = security.hash_token(payload.token)
    record = await db.scalar(
        select(PasswordResetToken).where(PasswordResetToken.token_hash == token_hash)
    )
    if record is None or record.used_at is not None or record.expires_at < datetime.now(UTC):
        raise ValidationAppError("This reset link is invalid or has expired.", code="invalid_token")

    user = await db.get(User, record.user_id)
    if user is None:
        raise NotFoundError("User not found.")

    user.hashed_password = security.hash_password(payload.new_password)
    record.used_at = datetime.now(UTC)

    # A password reset ends every existing session.
    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )
    await db.commit()
    return MessageResponse(message="Password has been reset. Please log in again.")
