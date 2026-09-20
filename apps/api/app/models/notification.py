"""In-app notifications, doubling as the email outbox (Phase 11).

A ``Notification`` is written in the *same transaction* as the thing it announces, so it exists
if and only if the action committed - a rolled-back cancel never produces a "your matter was
cancelled" ghost. Its optional email is an outbox row: ``email_status`` says whether it still has
to be sent, and delivery (``services/notifications``) happens after commit and can be retried.

``kind`` and ``email_status`` are plain strings validated in code (``NotificationKind`` /
``EmailStatus``), not Postgres enums: new event types are added often and shouldn't need a
migration.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class NotificationKind(enum.StrEnum):
    MATTER_REQUESTED = "MATTER_REQUESTED"
    MATTER_ACCEPTED = "MATTER_ACCEPTED"
    MATTER_REJECTED = "MATTER_REJECTED"
    MATTER_CANCELLED = "MATTER_CANCELLED"
    MATTER_PAID = "MATTER_PAID"
    MATTER_SCHEDULED = "MATTER_SCHEDULED"
    MATTER_CLOSED = "MATTER_CLOSED"
    MESSAGE_RECEIVED = "MESSAGE_RECEIVED"
    CALL_WAITING = "CALL_WAITING"
    DOCUMENT_REQUESTED = "DOCUMENT_REQUESTED"
    DOCUMENT_UPLOADED = "DOCUMENT_UPLOADED"
    REFUND_ISSUED = "REFUND_ISSUED"
    ADVOCATE_VERIFIED = "ADVOCATE_VERIFIED"
    ADVOCATE_REJECTED = "ADVOCATE_REJECTED"


class EmailStatus(enum.StrEnum):
    PENDING = "PENDING"  # still to be sent (or being retried)
    SENT = "SENT"
    FAILED = "FAILED"  # gave up after MAX_EMAIL_ATTEMPTS
    SKIPPED = "SKIPPED"  # no email for this event, or the user opted out


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    # Relative path inside the recipient's app (e.g. "/matters/<id>").
    link: Mapped[str | None] = mapped_column(String(300))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("clock_timestamp()"), nullable=False
    )

    # ---- email outbox -------------------------------------------------------------------
    email_status: Mapped[str] = mapped_column(
        String(10), nullable=False, default=EmailStatus.SKIPPED.value
    )
    email_subject: Mapped[str | None] = mapped_column(String(200))
    email_body: Mapped[str | None] = mapped_column(Text)
    email_attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    emailed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        # The bell: newest first for one user, and a cheap "how many unread".
        Index("ix_notifications_user_created", "user_id", "created_at"),
        Index(
            "ix_notifications_unread",
            "user_id",
            postgresql_where=text("read_at IS NULL"),
        ),
        # The outbox scan only ever looks at what is still pending.
        Index(
            "ix_notifications_email_pending",
            "created_at",
            postgresql_where=text("email_status = 'PENDING'"),
        ),
    )
