"""End-to-end ingestion: fetch -> extract -> clean -> chunk -> embed -> persist.

Failures at any stage (network, extraction, embeddings not configured, etc.)
are caught and recorded on the ``LegalDocument`` row (``ingestion_status`` /
``ingestion_error``) rather than raised — one bad source shouldn't 500 the
request, and admins need to *see* why a source failed (roadmap Phase 12:
"Track ingestion failures").
"""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.logging import get_logger
from app.models.legal_document import DocumentType, IngestionStatus, LegalChunk, LegalDocument
from app.services.ingestion.chunk import chunk_document
from app.services.ingestion.clean import clean_document_text
from app.services.ingestion.embed import embed_texts
from app.services.ingestion.extract import extract_text
from app.services.ingestion.fetch import fetch_document

logger = get_logger("app.ingestion")


async def ingest_source(
    *,
    db: AsyncSession,
    settings: Settings,
    title: str,
    source_url: str,
    document_type: DocumentType,
    law_name: str | None = None,
    jurisdiction: str = "IN",
    state_code: str | None = None,
    effective_date: date | None = None,
    version: str | None = None,
    organization_id: uuid.UUID | None = None,
) -> LegalDocument:
    document = LegalDocument(
        title=title,
        law_name=law_name,
        jurisdiction=jurisdiction,
        state_code=state_code,
        source_url=source_url,
        document_type=document_type,
        effective_date=effective_date,
        version=version,
        organization_id=organization_id,
        checksum="",
        ingestion_status=IngestionStatus.PROCESSING,
    )
    db.add(document)
    await db.flush()  # populate document.id for the chunks written below
    await _run_pipeline(document, db=db, settings=settings)
    return document


async def reingest_source(
    *, db: AsyncSession, settings: Settings, document: LegalDocument
) -> LegalDocument:
    """Re-fetch and re-process an existing source, replacing its chunks
    (roadmap Phase 12: "Re-index documents")."""
    await db.execute(delete(LegalChunk).where(LegalChunk.document_id == document.id))
    document.chunk_count = 0
    document.ingestion_status = IngestionStatus.PROCESSING
    document.ingestion_error = None
    await _run_pipeline(document, db=db, settings=settings)
    return document


async def _run_pipeline(document: LegalDocument, *, db: AsyncSession, settings: Settings) -> None:
    try:
        fetched = await fetch_document(document.source_url, settings=settings)
        document.checksum = fetched.checksum

        raw_text = extract_text(fetched)
        cleaned_text = clean_document_text(raw_text)
        chunks = chunk_document(
            cleaned_text,
            max_chars=settings.ingestion_chunk_max_chars,
            overlap_chars=settings.ingestion_chunk_overlap_chars,
        )
        if not chunks:
            raise ValueError("No extractable text content found at this source.")

        vectors = await embed_texts([c.content for c in chunks], settings=settings)

        for index, (chunk, vector) in enumerate(zip(chunks, vectors, strict=True)):
            db.add(
                LegalChunk(
                    document_id=document.id,
                    chunk_index=index,
                    section=chunk.section,
                    article=chunk.article,
                    page_number=chunk.page_number,
                    content=chunk.content,
                    embedding=vector,
                )
            )

        document.chunk_count = len(chunks)
        document.ingestion_status = IngestionStatus.COMPLETED
        document.ingestion_error = None
        logger.info("ingestion_completed", source_url=document.source_url, chunks=len(chunks))
    except Exception as exc:  # recorded on the row below, not re-raised
        logger.warning("ingestion_failed", source_url=document.source_url, error=str(exc))
        document.ingestion_status = IngestionStatus.FAILED
        document.ingestion_error = str(exc)[:2000]

    await db.commit()
    await db.refresh(document)
