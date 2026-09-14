"""Chat request/response schemas (Phase 2)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class SendMessageRequest(BaseModel):
    conversation_id: uuid.UUID | None = None
    message: str = Field(min_length=1, max_length=4000)


class SourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    document_id: uuid.UUID
    document_title: str
    section: str | None
    article: str | None
    source_url: str


class ChatMessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    role: Literal["user", "assistant"]
    content: str
    legal_category: str | None
    jurisdiction_scope: str | None
    is_out_of_scope: bool | None
    # Assistant messages only: the legal_chunks that grounded the answer.
    # Null for out-of-scope replies; [] means retrieval ran but found nothing.
    sources: list[SourceOut] | None = None
    created_at: datetime


class SendMessageResponse(BaseModel):
    conversation_id: uuid.UUID
    user_message: ChatMessageOut
    assistant_message: ChatMessageOut
    disclaimer: str


class ConversationSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str | None
    created_at: datetime
    updated_at: datetime


class ConversationDetail(BaseModel):
    id: uuid.UUID
    title: str | None
    messages: list[ChatMessageOut]
