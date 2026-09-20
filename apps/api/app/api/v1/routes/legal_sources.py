"""Admin: ingest, list, search, re-index and remove legal knowledge-base sources.

Runs ingestion synchronously and returns the result (COMPLETED or FAILED with
``ingestion_error`` set) — fine at Phase 3 scale. A background job queue for
large/bulk sources is a Phase 11/13 concern, not needed yet.

The full admin RAG-source management UI (upload, approve, version, track
failures) is Phase 12; these endpoints are the data layer it will drive, and
are usable now via ``/docs``.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select

from app.api.deps import DbSession, SettingsDep, require_roles
from app.core.errors import NotFoundError
from app.models.legal_document import DocumentType, IngestionStatus, LegalDocument
from app.models.organization import Organization
from app.models.user import User, UserRole
from app.schemas.legal_source import (
    IngestSourceRequest,
    LegalDocumentOut,
    PaginatedLegalDocuments,
    SearchResponse,
    SearchResultOut,
)
from app.services import audit
from app.services.ingestion.pipeline import ingest_source, reingest_source
from app.services.ingestion.search import semantic_search

router = APIRouter()

AdminUser = Annotated[User, Depends(require_roles(UserRole.ADMIN, UserRole.LEGAL_ADMIN))]
Limit = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0)]


async def _get_document(db: DbSession, document_id: uuid.UUID) -> LegalDocument:
    document = await db.get(LegalDocument, document_id)
    if document is None:
        raise NotFoundError("Legal source document not found.")
    return document


@router.post("", response_model=LegalDocumentOut, summary="Ingest a new legal source")
async def create_source(
    payload: IngestSourceRequest,
    admin: AdminUser,
    db: DbSession,
    settings: SettingsDep,
    request: Request,
) -> LegalDocumentOut:
    if payload.organization_id is not None and (
        await db.get(Organization, payload.organization_id) is None
    ):
        raise NotFoundError("Organization not found.")
    document = await ingest_source(
        db=db,
        settings=settings,
        title=payload.title,
        source_url=payload.source_url,
        document_type=payload.document_type,
        law_name=payload.law_name,
        jurisdiction=payload.jurisdiction,
        state_code=payload.state_code,
        effective_date=payload.effective_date,
        version=payload.version,
        organization_id=payload.organization_id,
    )
    audit.record(
        db,
        actor=admin,
        action="source.create",
        target_type="legal_document",
        target_id=document.id,
        detail={"title": document.title},
        request=request,
    )
    await db.commit()
    return LegalDocumentOut.model_validate(document)


@router.get("", response_model=PaginatedLegalDocuments, summary="List legal source documents")
async def list_sources(
    _admin: AdminUser,
    db: DbSession,
    document_type: DocumentType | None = None,
    status: IngestionStatus | None = None,
    limit: Limit = 25,
    offset: Offset = 0,
) -> PaginatedLegalDocuments:
    stmt = select(LegalDocument)
    count_stmt = select(func.count()).select_from(LegalDocument)
    if document_type is not None:
        stmt = stmt.where(LegalDocument.document_type == document_type)
        count_stmt = count_stmt.where(LegalDocument.document_type == document_type)
    if status is not None:
        stmt = stmt.where(LegalDocument.ingestion_status == status)
        count_stmt = count_stmt.where(LegalDocument.ingestion_status == status)

    total = (await db.execute(count_stmt)).scalar_one()
    rows = (
        (
            await db.execute(
                stmt.order_by(LegalDocument.created_at.desc()).limit(limit).offset(offset)
            )
        )
        .scalars()
        .all()
    )
    return PaginatedLegalDocuments(
        items=[LegalDocumentOut.model_validate(d) for d in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/search", response_model=SearchResponse, summary="Semantic search over ingested chunks"
)
async def search_sources(
    _admin: AdminUser,
    db: DbSession,
    settings: SettingsDep,
    q: Annotated[str, Query(min_length=1, max_length=500)],
    top_k: Annotated[int, Query(ge=1, le=50)] = 8,
) -> SearchResponse:
    results = await semantic_search(q, db=db, settings=settings, top_k=top_k)
    return SearchResponse(
        query=q,
        results=[
            SearchResultOut(
                chunk_id=r.chunk.id,
                document_id=r.document.id,
                document_title=r.document.title,
                section=r.chunk.section,
                article=r.chunk.article,
                page_number=r.chunk.page_number,
                content=r.chunk.content,
                distance=r.distance,
            )
            for r in results
        ],
    )


@router.get("/{document_id}", response_model=LegalDocumentOut, summary="Get a source document")
async def get_source(document_id: uuid.UUID, _admin: AdminUser, db: DbSession) -> LegalDocumentOut:
    document = await _get_document(db, document_id)
    return LegalDocumentOut.model_validate(document)


@router.post(
    "/{document_id}/reindex",
    response_model=LegalDocumentOut,
    summary="Re-fetch and re-chunk a source",
)
async def reindex_source(
    document_id: uuid.UUID,
    admin: AdminUser,
    db: DbSession,
    settings: SettingsDep,
    request: Request,
) -> LegalDocumentOut:
    document = await _get_document(db, document_id)
    document = await reingest_source(db=db, settings=settings, document=document)
    audit.record(
        db,
        actor=admin,
        action="source.reindex",
        target_type="legal_document",
        target_id=document.id,
        request=request,
    )
    await db.commit()
    return LegalDocumentOut.model_validate(document)


@router.delete("/{document_id}", status_code=204, summary="Remove an obsolete source")
async def delete_source(
    document_id: uuid.UUID, admin: AdminUser, db: DbSession, request: Request
) -> None:
    document = await _get_document(db, document_id)
    audit.record(
        db,
        actor=admin,
        action="source.delete",
        target_type="legal_document",
        target_id=document.id,
        detail={"title": document.title},
        request=request,
    )
    await db.delete(document)
    await db.commit()
