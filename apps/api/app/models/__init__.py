"""ORM models.

Import every model module here so that ``Base.metadata`` is complete for
Alembic autogenerate (see ``migrations/env.py``).
"""

from __future__ import annotations

from app.db.base import Base
from app.models.call import MatterCall
from app.models.chat import ChatMessage, Conversation, MessageRole
from app.models.document_request import AssistantDocumentType, DocumentRequest
from app.models.legal_document import DocumentType, IngestionStatus, LegalChunk, LegalDocument
from app.models.matter import Matter, MatterMessage, MatterServiceType, MatterStatus
from app.models.matter_document import (
    MatterDocumentRequest,
    MatterDocumentRequestStatus,
    MatterFile,
)
from app.models.notification import EmailStatus, Notification, NotificationKind
from app.models.payment import Invoice, Payment, PaymentStatus, Refund
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
    "EmailStatus",
    "EmailVerificationToken",
    "IngestionStatus",
    "Invoice",
    "LegalChunk",
    "LegalDocument",
    "Matter",
    "MatterCall",
    "MatterDocumentRequest",
    "MatterDocumentRequestStatus",
    "MatterFile",
    "MatterMessage",
    "MatterServiceType",
    "MatterStatus",
    "MessageRole",
    "Notification",
    "NotificationKind",
    "PasswordResetToken",
    "Payment",
    "PaymentStatus",
    "RefreshToken",
    "Refund",
    "User",
    "UserRole",
    "VerificationStatus",
]
