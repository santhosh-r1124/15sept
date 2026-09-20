"""Matter (a booked advocate engagement) + its message thread (Phase 8, FRD §9-10).

A ``Matter`` is what the FRD's advocate dashboard calls a "request" once accepted: one
consumer engaging one verified advocate for either a timed consultation or a document
service. It moves through the lifecycle in ``app.services.matters.lifecycle``.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric, String, Text, text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.models.user import AdvocateProfile, User


class MatterServiceType(enum.StrEnum):
    """Mirrors packages/shared/src/matter.ts (MATTER_SERVICE_TYPES) — keep in sync (FRD §9)."""

    CONSULTATION = "CONSULTATION"
    DOCUMENT_DRAFT = "DOCUMENT_DRAFT"
    DOCUMENT_REVIEW = "DOCUMENT_REVIEW"
    DOCUMENT_MODIFICATION = "DOCUMENT_MODIFICATION"
    AFFIDAVIT_ASSISTANCE = "AFFIDAVIT_ASSISTANCE"
    AGREEMENT_REVIEW = "AGREEMENT_REVIEW"


class MatterStatus(enum.StrEnum):
    """Mirrors packages/shared/src/matter.ts (MATTER_STATUSES) — keep in sync."""

    REQUESTED = "REQUESTED"
    ACCEPTED = "ACCEPTED"
    PAID = "PAID"
    SCHEDULED = "SCHEDULED"
    CLOSED = "CLOSED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


class Matter(TimestampMixin, Base):
    __tablename__ = "matters"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    consumer_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    advocate_profile_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("advocate_profiles.id", ondelete="CASCADE"), nullable=False
    )
    service_type: Mapped[MatterServiceType] = mapped_column(
        SAEnum(MatterServiceType, name="matter_service_type", native_enum=True), nullable=False
    )
    # 15 / 30 / 60 — only set for CONSULTATION (FRD §9).
    consultation_minutes: Mapped[int | None] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    requirement: Mapped[str] = mapped_column(Text, nullable=False)
    preferred_language: Mapped[str | None] = mapped_column(String(50))
    status: Mapped[MatterStatus] = mapped_column(
        SAEnum(MatterStatus, name="matter_status", native_enum=True),
        nullable=False,
        default=MatterStatus.REQUESTED,
        server_default=MatterStatus.REQUESTED.value,
    )
    # Prefilled for consultations from the advocate's fee (see services.matters.pricing);
    # the advocate confirms or sets it when accepting.
    quoted_fee: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    # Advocate's note on accept/reject, or who cancelled and why.
    decision_note: Mapped[str | None] = mapped_column(Text)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Opaque reference from the payment provider (Phase 10 moves the full record to `payments`).
    payment_reference: Mapped[str | None] = mapped_column(String(100))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    consumer: Mapped[User] = relationship(foreign_keys=[consumer_id])
    advocate_profile: Mapped[AdvocateProfile] = relationship(foreign_keys=[advocate_profile_id])
    messages: Mapped[list[MatterMessage]] = relationship(
        back_populates="matter", cascade="all, delete-orphan", order_by="MatterMessage.created_at"
    )

    __table_args__ = (
        Index("ix_matters_consumer_id", "consumer_id"),
        Index("ix_matters_advocate_profile_id", "advocate_profile_id"),
        Index("ix_matters_status", "status"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"Matter(id={self.id!s}, status={self.status}, type={self.service_type})"


class MatterMessage(Base):
    __tablename__ = "matter_messages"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    matter_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("matters.id", ondelete="CASCADE"), nullable=False
    )
    sender_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    # clock_timestamp(), not now(): now() is frozen at transaction start, which would give
    # messages written in one transaction identical timestamps and an unstable thread order.
    created_at: Mapped[datetime] = mapped_column(
        server_default=text("clock_timestamp()"), nullable=False
    )

    matter: Mapped[Matter] = relationship(back_populates="messages")

    __table_args__ = (Index("ix_matter_messages_matter_id", "matter_id"),)
