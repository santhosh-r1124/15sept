"""Payments ledger, refunds and invoices (Phase 10).

One ``Payment`` per matter (enforced by a unique constraint - it is also what stops a double
charge under concurrency). Refunds are separate rows so the history is auditable, and the
running total lives on the payment. An ``Invoice`` is issued at payment time and is immutable;
refunds are shown alongside it, not by editing it.

Money is ``Numeric(10, 2)`` / ``Decimal`` everywhere - never float.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String, Text, text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class PaymentStatus(enum.StrEnum):
    SUCCEEDED = "SUCCEEDED"
    PARTIALLY_REFUNDED = "PARTIALLY_REFUNDED"
    REFUNDED = "REFUNDED"


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    matter_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("matters.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    payer_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    refunded_amount: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False, default=Decimal("0.00"), server_default=text("0")
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="INR")
    status: Mapped[PaymentStatus] = mapped_column(
        SAEnum(PaymentStatus, name="payment_status", native_enum=True),
        nullable=False,
        default=PaymentStatus.SUCCEEDED,
        server_default=PaymentStatus.SUCCEEDED.value,
    )
    # Which PaymentProvider took the money ("mock" until a real gateway is chosen) and its
    # opaque reference for it - what a refund is issued against.
    provider: Mapped[str] = mapped_column(String(30), nullable=False)
    provider_reference: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        server_default=text("clock_timestamp()"), nullable=False
    )

    refunds: Mapped[list[Refund]] = relationship(
        back_populates="payment", order_by="Refund.created_at"
    )

    __table_args__ = (Index("ix_payments_payer_id", "payer_id"),)


class Refund(Base):
    __tablename__ = "refunds"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    payment_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("payments.id", ondelete="CASCADE"), nullable=False
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    provider_reference: Mapped[str] = mapped_column(String(100), nullable=False)
    # Who triggered it: the admin's user id for a manual refund, or the cancelling party for an
    # automatic one (see services/payments/ledger.py).
    initiated_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        server_default=text("clock_timestamp()"), nullable=False
    )

    payment: Mapped[Payment] = relationship(back_populates="refunds")

    __table_args__ = (Index("ix_refunds_payment_id", "payment_id"),)


class Invoice(Base):
    __tablename__ = "invoices"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    # "INV-2026-000042", from the invoice_number_seq Postgres sequence: unique and gap-tolerant
    # (a rolled-back transaction can skip a number, which is normal for sequences).
    invoice_number: Mapped[str] = mapped_column(String(30), nullable=False, unique=True)
    payment_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("payments.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    matter_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("matters.id", ondelete="CASCADE"), nullable=False
    )
    consumer_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    advocate_profile_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("advocate_profiles.id", ondelete="CASCADE"), nullable=False
    )
    # Snapshotted at issue time: an invoice must not change if the matter/profile later does.
    description: Mapped[str] = mapped_column(String(300), nullable=False)
    client_name: Mapped[str] = mapped_column(String(150), nullable=False)
    advocate_name: Mapped[str] = mapped_column(String(150), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="INR")
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("clock_timestamp()"), nullable=False
    )

    payment: Mapped[Payment] = relationship()

    __table_args__ = (
        Index("ix_invoices_consumer_id", "consumer_id"),
        Index("ix_invoices_advocate_profile_id", "advocate_profile_id"),
    )
