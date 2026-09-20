"""Organisations - the tenant boundary for enterprise users (Phase 13).

An organisation groups ``ENTERPRISE_USER`` accounts and owns *private* legal documents: text an
organisation ingested for its own assistant (internal policies, contracts) that must be searchable
by its members and by nobody else. Public documents have ``organization_id`` NULL and are visible to
everyone. The isolation rule is enforced where it matters - inside retrieval - not in the UI.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    name: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("clock_timestamp()"), nullable=False
    )
