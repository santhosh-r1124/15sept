"""Legal source document + chunk ORM models (Phase 3).

Metadata split matches the roadmap's field list: document-level fields
(title, law_name, jurisdiction, state, source_url, effective_date, version,
document_type) live on ``LegalDocument``; per-chunk fields (section, article,
page_number) live on ``LegalChunk``. ``document_id`` is just the FK.
"""

from __future__ import annotations

import enum
import uuid
from datetime import date, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import Date, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

# Fixed at migration time (the pgvector column dimension can't change without a
# new migration + re-embedding) — must match `Settings.embedding_dimensions`
# and migration 0004. Not read from Settings here: this is a schema fact, not
# runtime config.
EMBEDDING_DIM = 768


class DocumentType(enum.StrEnum):
    ACT = "ACT"
    RULES = "RULES"
    REGULATION = "REGULATION"
    NOTIFICATION = "NOTIFICATION"
    JUDGMENT = "JUDGMENT"
    OTHER = "OTHER"


class IngestionStatus(enum.StrEnum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class LegalDocument(TimestampMixin, Base):
    __tablename__ = "legal_documents"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    law_name: Mapped[str | None] = mapped_column(String(300))
    # "IN" for central/national law; an ISO-3166-2:IN state code for state law.
    jurisdiction: Mapped[str] = mapped_column(String(10), nullable=False, default="IN")
    state_code: Mapped[str | None] = mapped_column(String(2))
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    document_type: Mapped[DocumentType] = mapped_column(
        SAEnum(DocumentType, name="legal_document_type", native_enum=True), nullable=False
    )
    effective_date: Mapped[date | None] = mapped_column(Date)
    version: Mapped[str | None] = mapped_column(String(50))
    # sha256 of the raw fetched bytes — detects whether a source has changed
    # since it was last ingested, without storing the raw content itself.
    checksum: Mapped[str] = mapped_column(String(64), nullable=False, default="")

    ingestion_status: Mapped[IngestionStatus] = mapped_column(
        SAEnum(IngestionStatus, name="ingestion_status", native_enum=True),
        nullable=False,
        default=IngestionStatus.PENDING,
        server_default=IngestionStatus.PENDING.value,
    )
    ingestion_error: Mapped[str | None] = mapped_column(Text)
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    chunks: Mapped[list[LegalChunk]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="LegalChunk.chunk_index",
    )

    __table_args__ = (
        Index("ix_legal_documents_document_type", "document_type"),
        Index("ix_legal_documents_jurisdiction", "jurisdiction"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"LegalDocument(id={self.id!s}, title={self.title!r}, status={self.ingestion_status})"
        )


class LegalChunk(Base):
    __tablename__ = "legal_chunks"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("legal_documents.id", ondelete="CASCADE"), nullable=False
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    section: Mapped[str | None] = mapped_column(String(50))
    article: Mapped[str | None] = mapped_column(String(50))
    page_number: Mapped[int | None] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM), nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"), nullable=False)

    document: Mapped[LegalDocument] = relationship(back_populates="chunks")

    __table_args__ = (Index("ix_legal_chunks_document_id", "document_id"),)

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"LegalChunk(id={self.id!s}, document_id={self.document_id!s}, idx={self.chunk_index})"
        )
