"""User, advocate profile and auth-token ORM models (Phase 1)."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric, String, Text, func, text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


# Mirrors packages/shared/src/roles.ts (ROLES) — keep in sync.
class UserRole(enum.StrEnum):
    CONSUMER = "CONSUMER"
    ADVOCATE = "ADVOCATE"
    ADMIN = "ADMIN"
    LEGAL_ADMIN = "LEGAL_ADMIN"
    ENTERPRISE_USER = "ENTERPRISE_USER"


# Mirrors packages/shared/src/roles.ts (VERIFICATION_STATUSES) — keep in sync.
class VerificationStatus(enum.StrEnum):
    PENDING = "PENDING"
    IN_REVIEW = "IN_REVIEW"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        SAEnum(UserRole, name="user_role", native_enum=True),
        nullable=False,
        default=UserRole.CONSUMER,
        server_default=UserRole.CONSUMER.value,
    )
    display_name: Mapped[str | None] = mapped_column(String(150))
    state_code: Mapped[str | None] = mapped_column(String(2))
    preferred_language: Mapped[str | None] = mapped_column(String(50))
    email_verified: Mapped[bool] = mapped_column(
        default=False, server_default=text("false"), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(
        default=True, server_default=text("true"), nullable=False
    )
    # The tenant an ENTERPRISE_USER belongs to (Phase 13); None for everyone else.
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="SET NULL")
    )
    # Set when the person exercised their right to erasure; the row is then anonymised.
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Opt-out for *notification* emails (Phase 11). Account emails (verify / reset) always send.
    email_notifications: Mapped[bool] = mapped_column(
        default=True, server_default=text("true"), nullable=False
    )

    advocate_profile: Mapped[AdvocateProfile | None] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"User(id={self.id!s}, email={self.email!r}, role={self.role})"


class AdvocateProfile(TimestampMixin, Base):
    """Advocate-specific fields, one-to-one with a ``User(role=ADVOCATE)``."""

    __tablename__ = "advocate_profiles"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    practice_areas: Mapped[list[str]] = mapped_column(
        ARRAY(String), default=list, server_default="{}"
    )
    state_code: Mapped[str] = mapped_column(String(2), nullable=False)
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    languages: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, server_default="{}")
    consultation_fee: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    bio: Mapped[str | None] = mapped_column(Text)
    experience_years: Mapped[int | None] = mapped_column(Integer)
    verification_status: Mapped[VerificationStatus] = mapped_column(
        SAEnum(VerificationStatus, name="verification_status", native_enum=True),
        nullable=False,
        default=VerificationStatus.PENDING,
        server_default=VerificationStatus.PENDING.value,
    )
    verification_note: Mapped[str | None] = mapped_column(Text)
    # Simple weekly-slot availability, e.g. {"mon": ["10:00-13:00"], ...}. Refined in Phase 8.
    availability: Mapped[dict[str, object] | None] = mapped_column(JSONB)

    user: Mapped[User] = relationship(back_populates="advocate_profile")

    def __repr__(self) -> str:  # pragma: no cover
        return f"AdvocateProfile(user_id={self.user_id!s}, status={self.verification_status})"


class EmailVerificationToken(Base):
    __tablename__ = "email_verification_tokens"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    __table_args__ = (Index("ix_email_verification_tokens_user_id", "user_id"),)


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    __table_args__ = (Index("ix_password_reset_tokens_user_id", "user_id"),)


class RefreshToken(Base):
    """DB-backed record of an issued refresh token, keyed by its JWT ``jti``.

    Lets us revoke on logout and detect/rotate on reuse — a bare JWT can't be
    invalidated before it expires.
    """

    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    jti_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    __table_args__ = (Index("ix_refresh_tokens_user_id", "user_id"),)
