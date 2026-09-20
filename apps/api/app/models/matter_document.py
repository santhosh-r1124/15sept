"""Document exchange inside a matter (Phase 9, FRD 10): the advocate *requests* documents,
either party *uploads* files, and the advocate uploads the *final* deliverable.

File bytes live behind ``app.services.storage`` (local disk in dev); only metadata is here.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MatterDocumentRequestStatus(enum.StrEnum):
    OPEN = "OPEN"
    FULFILLED = "FULFILLED"


class MatterDocumentRequest(Base):
    """'Please send me X' - raised by the advocate, fulfilled when a file is attached to it."""

    __tablename__ = "matter_document_requests"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    matter_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("matters.id", ondelete="CASCADE"), nullable=False
    )
    requested_by_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[MatterDocumentRequestStatus] = mapped_column(
        SAEnum(
            MatterDocumentRequestStatus, name="matter_document_request_status", native_enum=True
        ),
        nullable=False,
        default=MatterDocumentRequestStatus.OPEN,
        server_default=MatterDocumentRequestStatus.OPEN.value,
    )
    created_at: Mapped[datetime] = mapped_column(
        server_default=text("clock_timestamp()"), nullable=False
    )

    __table_args__ = (Index("ix_matter_document_requests_matter_id", "matter_id"),)


class MatterFile(Base):
    __tablename__ = "matter_files"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    matter_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("matters.id", ondelete="CASCADE"), nullable=False
    )
    uploader_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    request_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("matter_document_requests.id", ondelete="SET NULL"),
        nullable=True,
    )
    # The client's name, kept for display and the download header only - never used as a path.
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    # Server-generated (see services/storage): a random name, safe as a path component.
    storage_key: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    # The advocate's finished deliverable, as opposed to a supporting document.
    is_final: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    created_at: Mapped[datetime] = mapped_column(
        server_default=text("clock_timestamp()"), nullable=False
    )

    __table_args__ = (Index("ix_matter_files_matter_id", "matter_id"),)
