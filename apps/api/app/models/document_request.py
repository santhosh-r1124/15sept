"""Legal Document Assistant ORM model (Phase 6, FRD §7).

A ``DocumentRequest`` is a completed draft, not a work-in-progress
questionnaire: the questionnaire itself is stateless on the backend (the
static per-type question set in ``app.services.document_assistant.questions``
drives a client-side form), so there is nothing to persist until the user has
answered every required question and a draft has actually been generated. A
failed generation (LLM not configured, transport error) is therefore never
written here — it 503s the request instead, the same way
``app.services.llm`` does for chat — so no ``status``/``error`` columns exist;
every row in this table is a successfully generated draft.
"""

from __future__ import annotations

import enum
import uuid

from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class AssistantDocumentType(enum.StrEnum):
    """Mirrors packages/shared/src/legal.ts (DOCUMENT_TYPES) — keep in sync.

    Distinct from ``app.models.legal_document.DocumentType`` (Phase 3), which
    classifies *ingested source* documents (Acts, judgments, ...); this
    classifies what the *user* is asking the assistant to draft.
    """

    RENTAL_AGREEMENT = "RENTAL_AGREEMENT"
    EMPLOYMENT_AGREEMENT = "EMPLOYMENT_AGREEMENT"
    NDA = "NDA"
    AFFIDAVIT = "AFFIDAVIT"
    DECLARATION = "DECLARATION"
    BUSINESS_AGREEMENT = "BUSINESS_AGREEMENT"
    PARTNERSHIP_DOCUMENT = "PARTNERSHIP_DOCUMENT"
    AUTHORIZATION_LETTER = "AUTHORIZATION_LETTER"
    SERVICE_AGREEMENT = "SERVICE_AGREEMENT"
    LEGAL_NOTICE = "LEGAL_NOTICE"
    OTHER = "OTHER"


class DocumentRequest(TimestampMixin, Base):
    """A generated document draft. ``user_id`` is null for anonymous
    (public-tier) requests, same convention as ``Conversation`` (Phase 2).
    """

    __tablename__ = "document_requests"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    document_type: Mapped[AssistantDocumentType] = mapped_column(
        SAEnum(AssistantDocumentType, name="assistant_document_type", native_enum=True),
        nullable=False,
    )
    # ISO-3166-2:IN state code — jurisdiction hint (FRD §12), optional since
    # some document types (e.g. an NDA between two companies) may not have a
    # single obvious state.
    state_code: Mapped[str | None] = mapped_column(String(2))
    # The user's answers to app.services.document_assistant.questions
    # QUESTION_SETS[document_type], keyed by Question.key.
    answers: Mapped[dict[str, str]] = mapped_column(JSONB, nullable=False)
    draft_text: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (Index("ix_document_requests_user_id", "user_id"),)

    def __repr__(self) -> str:  # pragma: no cover
        return f"DocumentRequest(id={self.id!s}, document_type={self.document_type})"
