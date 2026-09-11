"""Legal source ingestion + search schemas (Phase 3)."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.legal_document import DocumentType, IngestionStatus


class IngestSourceRequest(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    source_url: str = Field(min_length=1, max_length=2000)
    document_type: DocumentType
    law_name: str | None = Field(default=None, max_length=300)
    jurisdiction: str = Field(default="IN", min_length=2, max_length=10)
    state_code: str | None = Field(default=None, min_length=2, max_length=2)
    effective_date: date | None = None
    version: str | None = Field(default=None, max_length=50)

    @field_validator("state_code")
    @classmethod
    def _upper_state(cls, value: str | None) -> str | None:
        return value.upper() if value else value


class LegalDocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    law_name: str | None
    jurisdiction: str
    state_code: str | None
    source_url: str
    document_type: DocumentType
    effective_date: date | None
    version: str | None
    ingestion_status: IngestionStatus
    ingestion_error: str | None
    chunk_count: int
    created_at: datetime
    updated_at: datetime


class PaginatedLegalDocuments(BaseModel):
    items: list[LegalDocumentOut]
    total: int
    limit: int
    offset: int


class SearchResultOut(BaseModel):
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_title: str
    section: str | None
    article: str | None
    page_number: int | None
    content: str
    distance: float


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResultOut]
