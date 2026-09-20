"""Consultation call sessions (voice / video).

Only *metadata* is stored - who opened the room, when both people were connected, when it ended.
No media is recorded or stored anywhere (it flows browser to browser). The rows answer "did the
consultation take place, and for how long?", which the advocate needs before closing the matter
and legal ops needs when a client and advocate disagree.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MatterCall(Base):
    __tablename__ = "matter_calls"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    matter_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("matters.id", ondelete="CASCADE"), nullable=False
    )
    opened_by: Mapped[str] = mapped_column(String(10), nullable=False)  # CONSUMER | ADVOCATE
    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("clock_timestamp()"), nullable=False
    )
    # Set the first time both participants are in the room; stays null if the other never came.
    connected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # hangup | disconnect | time_limit | superseded
    ended_reason: Mapped[str | None] = mapped_column(String(20))

    __table_args__ = (Index("ix_matter_calls_matter", "matter_id", "opened_at"),)
