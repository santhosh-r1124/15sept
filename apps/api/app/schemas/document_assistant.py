"""Document Assistant request/response schemas (Phase 6)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.document_request import AssistantDocumentType


class QuestionOut(BaseModel):
    key: str
    label: str
    required: bool
    help_text: str | None


class DocumentTypeInfoOut(BaseModel):
    document_type: AssistantDocumentType
    questions: list[QuestionOut]


class CreateDocumentRequestPayload(BaseModel):
    document_type: AssistantDocumentType
    # Free-text answers keyed by Question.key; validated server-side against
    # that document_type's required questions (app.services.document_assistant
    # .questions.missing_required_answers), not by Pydantic field presence,
    # since the required set differs per document_type.
    answers: dict[str, str] = Field(default_factory=dict)


class DocumentRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_type: AssistantDocumentType
    state_code: str | None
    answers: dict[str, str]
    draft_text: str
    created_at: datetime


class CreateDocumentResponse(BaseModel):
    document: DocumentRequestOut
    disclaimer: str
