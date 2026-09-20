"""Conversation + chat message ORM models (Phase 2)."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text, func, text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class MessageRole(enum.StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


class Conversation(TimestampMixin, Base):
    """A chat thread. ``user_id`` is null for anonymous (public-tier) chats."""

    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    # Derived from the first message; None until the first message lands.
    title: Mapped[str | None] = mapped_column(String(200))

    messages: Mapped[list[ChatMessage]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="ChatMessage.created_at",
    )

    __table_args__ = (Index("ix_conversations_user_id", "user_id"),)

    def __repr__(self) -> str:  # pragma: no cover
        return f"Conversation(id={self.id!s}, user_id={self.user_id!s})"


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[MessageRole] = mapped_column(
        # values_callable: persist the enum *values* ("user"/"assistant", which is what the
        # Postgres enum in migration 0003 and the API contract use), not SQLAlchemy's default
        # of member *names* ("USER"/"ASSISTANT"), which Postgres rejects.
        SAEnum(
            MessageRole,
            name="message_role",
            native_enum=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)

    # Set on the user's message only — the outcome of
    # app.services.legal_classifier.classify_query.
    legal_category: Mapped[str | None] = mapped_column(String(30))
    jurisdiction_scope: Mapped[str | None] = mapped_column(String(30))
    is_out_of_scope: Mapped[bool | None] = mapped_column(Boolean)
    # LOW/MEDIUM/HIGH/CRITICAL (Phase 5) — indexed for the Phase 12 admin
    # "high-risk query review" queue (docs/roadmap.md).
    risk_level: Mapped[str | None] = mapped_column(String(10))

    # Set on the assistant's message only (Phase 4) — the legal_chunks that
    # grounded the answer, as [{document_id, document_title, section, article,
    # source_url}]. Null for out-of-scope replies; an empty list means
    # retrieval ran but found nothing (the "insufficient evidence" case).
    sources: Mapped[list[dict[str, object]] | None] = mapped_column(JSONB)

    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    # Legal-ops review of HIGH/CRITICAL queries (Phase 12). Only ever set on the user's message.
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    review_note: Mapped[str | None] = mapped_column(Text)

    conversation: Mapped[Conversation] = relationship(back_populates="messages")

    __table_args__ = (
        Index("ix_chat_messages_conversation_id", "conversation_id"),
        Index("ix_chat_messages_risk_level", "risk_level"),
        # The review queue: unreviewed high-risk queries, oldest first.
        Index(
            "ix_chat_messages_review_queue",
            "created_at",
            postgresql_where=text("risk_level IN ('HIGH', 'CRITICAL') AND reviewed_at IS NULL"),
        ),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"ChatMessage(id={self.id!s}, role={self.role}, conv={self.conversation_id!s})"
