"""ORM models.

Import every model module here so that ``Base.metadata`` is complete for
Alembic autogenerate (see ``migrations/env.py``).
"""

from __future__ import annotations

from app.db.base import Base
from app.models.chat import ChatMessage, Conversation, MessageRole
from app.models.document_request import AssistantDocumentType, DocumentRequest
from app.models.legal_document import DocumentType, IngestionStatus, LegalChunk, LegalDocument
from app.models.user import (
    AdvocateProfile,
    EmailVerificationToken,
    PasswordResetToken,
    RefreshToken,
    User,
    UserRole,
    VerificationStatus,
)

__all__ = [
    "AdvocateProfile",
    "AssistantDocumentType",
    "Base",
    "ChatMessage",
    "Conversation",
    "DocumentRequest",
    "DocumentType",
    "EmailVerificationToken",
    "IngestionStatus",
    "LegalChunk",
    "LegalDocument",
    "MessageRole",
    "PasswordResetToken",
    "RefreshToken",
    "User",
    "UserRole",
    "VerificationStatus",
]
