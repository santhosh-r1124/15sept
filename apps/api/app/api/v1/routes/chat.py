"""Public + authenticated legal chat (Phase 2) with grounded retrieval (Phase 4).

Anyone can chat (Tier 1 / public, per the FRD) — ``conversation_id`` is enough
to continue a thread anonymously. Logging in additionally ties the
conversation to the account (so it survives across devices) and unlocks
``GET /chat/conversations`` (a list of *your* threads).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentUser, DbSession, OptionalUser, SettingsDep
from app.core.errors import ForbiddenError, NotFoundError, ServiceUnavailableError
from app.core.legal_text import (
    ADVOCATE_RECOMMENDATION_MESSAGE,
    INSUFFICIENT_EVIDENCE_MESSAGE,
    MANDATORY_DISCLAIMER,
    OUT_OF_SCOPE_MESSAGE,
)
from app.core.logging import get_logger
from app.models.chat import ChatMessage, Conversation, MessageRole
from app.models.user import User
from app.schemas.chat import (
    ChatMessageOut,
    ConversationDetail,
    ConversationSummary,
    SendMessageRequest,
    SendMessageResponse,
)
from app.services import legal_classifier, risk_engine
from app.services import llm as llm_service
from app.services.rag import retrieval as retrieval_service
from app.services.rag.retrieval import RetrievedChunk

router = APIRouter()
logger = get_logger("app.chat")

_TITLE_MAX_LEN = 60


def _derive_title(message: str) -> str:
    flat = " ".join(message.split())
    return flat if len(flat) <= _TITLE_MAX_LEN else flat[: _TITLE_MAX_LEN - 1].rstrip() + "…"


def _assert_readable(conversation: Conversation, user: User | None) -> None:
    """A conversation with an owner is only visible to that owner."""
    if conversation.user_id is not None and (user is None or conversation.user_id != user.id):
        raise ForbiddenError("This conversation belongs to another account.")


async def _load_conversation(db: DbSession, conversation_id: uuid.UUID) -> Conversation:
    conversation = await db.get(
        Conversation, conversation_id, options=[selectinload(Conversation.messages)]
    )
    if conversation is None:
        raise NotFoundError("Conversation not found.")
    return conversation


async def _retrieve(message: str, *, db: DbSession, settings: SettingsDep) -> list[RetrievedChunk]:
    """Retrieval is a soft dependency: if embeddings aren't configured (or the
    provider errors), that's not a reason to 500 the whole chat request — it's
    indistinguishable, from the user's side, from "no matching sources were
    found", so it degrades to the same INSUFFICIENT_EVIDENCE_MESSAGE path
    rather than guessing an ungrounded answer or surfacing a raw 503.
    """
    try:
        return await retrieval_service.hybrid_search(message, db=db, settings=settings)
    except ServiceUnavailableError as exc:
        logger.info("retrieval_unavailable", code=exc.code)
        return []


def _source_dict(chunk: RetrievedChunk) -> dict[str, object]:
    return {
        "document_id": str(chunk.document_id),
        "document_title": chunk.document_title,
        "section": chunk.section,
        "article": chunk.article,
        "source_url": chunk.source_url,
    }


@router.post("/messages", response_model=SendMessageResponse, summary="Send a chat message")
async def send_message(
    payload: SendMessageRequest, user: OptionalUser, db: DbSession, settings: SettingsDep
) -> SendMessageResponse:
    if payload.conversation_id is not None:
        conversation = await _load_conversation(db, payload.conversation_id)
        _assert_readable(conversation, user)
        history_source = conversation.messages
    else:
        conversation = Conversation(
            user_id=user.id if user else None, title=_derive_title(payload.message)
        )
        db.add(conversation)
        await db.flush()
        history_source = []

    history = [(m.role.value, m.content) for m in history_source[-settings.chat_history_length :]]

    user_message = ChatMessage(
        conversation_id=conversation.id, role=MessageRole.USER, content=payload.message
    )
    db.add(user_message)

    classification = await legal_classifier.classify_query(payload.message, settings=settings)
    user_message.legal_category = classification.category
    user_message.jurisdiction_scope = classification.jurisdiction_scope
    user_message.is_out_of_scope = classification.is_out_of_scope
    user_message.risk_level = classification.risk_level

    sources: list[dict[str, object]] | None = None
    if classification.is_out_of_scope:
        answer_text = OUT_OF_SCOPE_MESSAGE
    else:
        retrieved = await _retrieve(payload.message, db=db, settings=settings)
        if not retrieved:
            answer_text = INSUFFICIENT_EVIDENCE_MESSAGE
            sources = []
        else:
            answer_text = await llm_service.generate_grounded_answer(
                payload.message, history=history, context=retrieved, settings=settings
            )
            sources = [_source_dict(chunk) for chunk in retrieved]

        if risk_engine.requires_advocate_recommendation(classification.risk_level):
            answer_text = f"{answer_text}\n\n{ADVOCATE_RECOMMENDATION_MESSAGE}"

    assistant_message = ChatMessage(
        conversation_id=conversation.id,
        role=MessageRole.ASSISTANT,
        content=answer_text,
        sources=sources,
    )
    db.add(assistant_message)

    await db.commit()
    await db.refresh(user_message)
    await db.refresh(assistant_message)

    return SendMessageResponse(
        conversation_id=conversation.id,
        user_message=ChatMessageOut.model_validate(user_message),
        assistant_message=ChatMessageOut.model_validate(assistant_message),
        disclaimer=MANDATORY_DISCLAIMER,
    )


@router.get(
    "/conversations", response_model=list[ConversationSummary], summary="List your conversations"
)
async def list_conversations(user: CurrentUser, db: DbSession) -> list[ConversationSummary]:
    rows = (
        (
            await db.execute(
                select(Conversation)
                .where(Conversation.user_id == user.id)
                .order_by(Conversation.updated_at.desc())
                .limit(50)
            )
        )
        .scalars()
        .all()
    )
    return [ConversationSummary.model_validate(c) for c in rows]


@router.get(
    "/conversations/{conversation_id}",
    response_model=ConversationDetail,
    summary="Get a conversation's messages",
)
async def get_conversation(
    conversation_id: uuid.UUID, user: OptionalUser, db: DbSession
) -> ConversationDetail:
    conversation = await _load_conversation(db, conversation_id)
    _assert_readable(conversation, user)
    return ConversationDetail(
        id=conversation.id,
        title=conversation.title,
        messages=[ChatMessageOut.model_validate(m) for m in conversation.messages],
    )
