"""Public + authenticated legal chat (Phase 2).

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
from app.core.errors import ForbiddenError, NotFoundError
from app.core.legal_text import MANDATORY_DISCLAIMER, OUT_OF_SCOPE_MESSAGE
from app.models.chat import ChatMessage, Conversation, MessageRole
from app.models.user import User
from app.schemas.chat import (
    ChatMessageOut,
    ConversationDetail,
    ConversationSummary,
    SendMessageRequest,
    SendMessageResponse,
)
from app.services import llm as llm_service

router = APIRouter()

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

    classification = await llm_service.classify_query(payload.message, settings=settings)
    user_message.legal_category = classification.category
    user_message.jurisdiction_scope = classification.jurisdiction_scope
    user_message.is_out_of_scope = classification.is_out_of_scope

    if classification.is_out_of_scope:
        answer_text = OUT_OF_SCOPE_MESSAGE
    else:
        answer_text = await llm_service.generate_answer(
            payload.message, history=history, settings=settings
        )

    assistant_message = ChatMessage(
        conversation_id=conversation.id, role=MessageRole.ASSISTANT, content=answer_text
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
