"""Legal Document Assistant (Phase 6, FRD §7).

Public-tier like chat (works anonymously or logged in) — the questionnaire
itself is static per ``document_type`` (``GET /documents/types``) so the
frontend can render the whole form without a backend round trip per
question; ``POST /documents`` validates the answers, generates the draft in
one Claude call, and persists the result. See
``app.services.document_assistant`` and
docs/adr/0009-document-assistant-scope.md for why this isn't RAG-grounded.
"""

from __future__ import annotations

import dataclasses
import uuid

from fastapi import APIRouter
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession, OptionalUser, SettingsDep
from app.core.errors import ForbiddenError, NotFoundError, ValidationAppError
from app.core.legal_text import MANDATORY_DISCLAIMER
from app.models.document_request import AssistantDocumentType, DocumentRequest
from app.models.user import User
from app.schemas.document_assistant import (
    CreateDocumentRequestPayload,
    CreateDocumentResponse,
    DocumentRequestOut,
    DocumentTypeInfoOut,
    QuestionOut,
)
from app.services.document_assistant import generation
from app.services.document_assistant.questions import missing_required_answers, questions_for
from app.services.rate_limit import rate_limit

router = APIRouter()


def _assert_readable(document: DocumentRequest, user: User | None) -> None:
    """A request with an owner is only visible to that owner — same rule as
    chat conversations."""
    if document.user_id is not None and (user is None or document.user_id != user.id):
        raise ForbiddenError("This document request belongs to another account.")


@router.get(
    "/types", response_model=list[DocumentTypeInfoOut], summary="List document types + questions"
)
async def list_document_types() -> list[DocumentTypeInfoOut]:
    return [
        DocumentTypeInfoOut(
            document_type=document_type,
            questions=[QuestionOut(**dataclasses.asdict(q)) for q in questions_for(document_type)],
        )
        for document_type in AssistantDocumentType
    ]


@router.post(
    "",
    response_model=CreateDocumentResponse,
    summary="Generate a document draft",
    dependencies=[rate_limit("document-draft", limit=10, window_seconds=3600)],
)
async def create_document_request(
    payload: CreateDocumentRequestPayload, user: OptionalUser, db: DbSession, settings: SettingsDep
) -> CreateDocumentResponse:
    missing = missing_required_answers(payload.document_type, payload.answers)
    if missing:
        raise ValidationAppError(
            "Some required questions are unanswered.",
            details=[
                {"field": f"answers.{key}", "message": "This field is required."} for key in missing
            ],
        )

    draft_text = await generation.generate_draft(
        payload.document_type, answers=payload.answers, settings=settings
    )

    state_code = (payload.answers.get("state_code") or "").strip().upper() or None
    document = DocumentRequest(
        user_id=user.id if user else None,
        document_type=payload.document_type,
        state_code=state_code,
        answers=payload.answers,
        draft_text=draft_text,
    )
    db.add(document)
    await db.commit()
    await db.refresh(document)

    return CreateDocumentResponse(
        document=DocumentRequestOut.model_validate(document), disclaimer=MANDATORY_DISCLAIMER
    )


@router.get("", response_model=list[DocumentRequestOut], summary="List your document requests")
async def list_document_requests(user: CurrentUser, db: DbSession) -> list[DocumentRequestOut]:
    rows = (
        (
            await db.execute(
                select(DocumentRequest)
                .where(DocumentRequest.user_id == user.id)
                .order_by(DocumentRequest.created_at.desc())
                .limit(50)
            )
        )
        .scalars()
        .all()
    )
    return [DocumentRequestOut.model_validate(d) for d in rows]


@router.get("/{document_id}", response_model=DocumentRequestOut, summary="Get a document request")
async def get_document_request(
    document_id: uuid.UUID, user: OptionalUser, db: DbSession
) -> DocumentRequestOut:
    document = await db.get(DocumentRequest, document_id)
    if document is None:
        raise NotFoundError("Document request not found.")
    _assert_readable(document, user)
    return DocumentRequestOut.model_validate(document)
