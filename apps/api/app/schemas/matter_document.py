"""Matter document-exchange schemas (Phase 9)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.models.matter_document import MatterDocumentRequestStatus


class CreateDocumentRequestRequest(BaseModel):
    description: str = Field(min_length=1, max_length=1000)


class DocumentRequestOut(BaseModel):
    id: uuid.UUID
    matter_id: uuid.UUID
    description: str
    status: MatterDocumentRequestStatus
    created_at: datetime


class MatterFileOut(BaseModel):
    id: uuid.UUID
    matter_id: uuid.UUID
    request_id: uuid.UUID | None
    file_name: str
    content_type: str
    size_bytes: int
    is_final: bool
    uploader_role: Literal["CONSUMER", "ADVOCATE"]
    created_at: datetime


class MatterDocumentsOut(BaseModel):
    requests: list[DocumentRequestOut]
    files: list[MatterFileOut]
