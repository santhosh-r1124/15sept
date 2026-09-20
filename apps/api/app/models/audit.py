"""Audit log (Phase 13): who did what to what, and when.

Append-only *by construction*: a database trigger (migration 0014) rejects every UPDATE, DELETE
and TRUNCATE, so neither a bug nor a compromised application account can quietly rewrite
history. A row is written in the same transaction as the action it records - it exists if and
only if the action committed.

There is deliberately no foreign key on ``actor_id``: the log must outlive the account (an
erased user's id stays as a pseudonymous reference). ``detail`` holds small, non-sensitive facts
(an amount, a status, a count) - never message text, document contents or personal data.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Index, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("clock_timestamp()"), nullable=False
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True))
    actor_role: Mapped[str | None] = mapped_column(String(20))
    # Dotted verb: "user.suspend", "refund.issue", "review.list" ...
    action: Mapped[str] = mapped_column(String(60), nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(30))
    target_id: Mapped[str | None] = mapped_column(String(64))
    detail: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    ip: Mapped[str | None] = mapped_column(String(45))
    request_id: Mapped[str | None] = mapped_column(String(64))

    __table_args__ = (
        Index("ix_audit_logs_occurred_at", "occurred_at"),
        Index("ix_audit_logs_actor", "actor_id", "occurred_at"),
        Index("ix_audit_logs_target", "target_type", "target_id"),
    )
