"""Integration tests for app.services.ingestion.pipeline. Needs Postgres —
see conftest.db_txn_session. fetch/extract/clean/chunk/embed are monkeypatched
at their point of use inside `pipeline` (those stages have their own pure-unit
tests); this exercises persistence, status transitions and error recording.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.models.legal_document import DocumentType, IngestionStatus, LegalChunk
from app.services.ingestion import pipeline as pipeline_module
from app.services.ingestion.chunk import Chunk
from app.services.ingestion.fetch import FetchedDocument

DEFAULT_CHUNKS = [
    Chunk(content="Section 1 body.", section="1", article=None, page_number=1),
    Chunk(content="Section 2 body.", section="2", article=None, page_number=1),
]
FAKE_VECTOR = [0.01] * 768


def _patch_pipeline(
    monkeypatch: pytest.MonkeyPatch,
    *,
    chunks: list[Chunk] | None = None,
    fail_with: Exception | None = None,
) -> None:
    resolved_chunks = DEFAULT_CHUNKS if chunks is None else chunks

    async def fake_fetch(url: str, *, settings: object) -> FetchedDocument:
        if fail_with is not None:
            raise fail_with
        return FetchedDocument(
            url=url, content_type="text/html", raw_bytes=b"<p>x</p>", checksum="abc123"
        )

    def fake_extract(document: object) -> str:
        return "irrelevant — chunk_document is also patched"

    def fake_clean(raw_text: str) -> str:
        return raw_text

    def fake_chunk(cleaned_text: str, *, max_chars: int, overlap_chars: int) -> list[Chunk]:
        return resolved_chunks

    async def fake_embed(texts: list[str], *, settings: object) -> list[list[float]]:
        return [FAKE_VECTOR for _ in texts]

    monkeypatch.setattr(pipeline_module, "fetch_document", fake_fetch)
    monkeypatch.setattr(pipeline_module, "extract_text", fake_extract)
    monkeypatch.setattr(pipeline_module, "clean_document_text", fake_clean)
    monkeypatch.setattr(pipeline_module, "chunk_document", fake_chunk)
    monkeypatch.setattr(pipeline_module, "embed_texts", fake_embed)


async def test_ingest_source_creates_document_and_chunks(
    db_txn_session: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_pipeline(monkeypatch)

    document = await pipeline_module.ingest_source(
        db=db_txn_session,  # type: ignore[arg-type]
        settings=get_settings(),
        title="Test Act, 2000",
        source_url="https://example.test/act",
        document_type=DocumentType.ACT,
        law_name="Test Act",
    )

    assert document.ingestion_status == IngestionStatus.COMPLETED
    assert document.chunk_count == 2
    assert document.checksum == "abc123"
    assert document.ingestion_error is None

    rows = (
        (
            await db_txn_session.execute(  # type: ignore[attr-defined]
                select(LegalChunk).where(LegalChunk.document_id == document.id)
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 2
    assert {c.section for c in rows} == {"1", "2"}
    assert all(len(c.embedding) == 768 for c in rows)


async def test_ingest_source_records_failure_instead_of_raising(
    db_txn_session: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_pipeline(monkeypatch, fail_with=ValueError("network unreachable"))

    document = await pipeline_module.ingest_source(
        db=db_txn_session,  # type: ignore[arg-type]
        settings=get_settings(),
        title="Broken Source",
        source_url="https://example.test/broken",
        document_type=DocumentType.OTHER,
    )

    assert document.ingestion_status == IngestionStatus.FAILED
    assert document.chunk_count == 0
    assert "network unreachable" in (document.ingestion_error or "")


async def test_ingest_source_fails_when_no_chunks_extracted(
    db_txn_session: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_pipeline(monkeypatch, chunks=[])

    document = await pipeline_module.ingest_source(
        db=db_txn_session,  # type: ignore[arg-type]
        settings=get_settings(),
        title="Empty Source",
        source_url="https://example.test/empty",
        document_type=DocumentType.OTHER,
    )

    assert document.ingestion_status == IngestionStatus.FAILED
    assert "No extractable text" in (document.ingestion_error or "")


async def test_reingest_source_replaces_chunks(
    db_txn_session: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_pipeline(
        monkeypatch, chunks=[Chunk(content="v1", section=None, article=None, page_number=1)]
    )
    document = await pipeline_module.ingest_source(
        db=db_txn_session,  # type: ignore[arg-type]
        settings=get_settings(),
        title="Doc",
        source_url="https://example.test/doc",
        document_type=DocumentType.ACT,
    )
    assert document.chunk_count == 1

    _patch_pipeline(
        monkeypatch,
        chunks=[
            Chunk(content="v2a", section=None, article=None, page_number=1),
            Chunk(content="v2b", section=None, article=None, page_number=1),
        ],
    )
    document = await pipeline_module.reingest_source(
        db=db_txn_session,
        settings=get_settings(),
        document=document,  # type: ignore[arg-type]
    )

    assert document.chunk_count == 2
    rows = (
        (
            await db_txn_session.execute(  # type: ignore[attr-defined]
                select(LegalChunk).where(LegalChunk.document_id == document.id)
            )
        )
        .scalars()
        .all()
    )
    assert {c.content for c in rows} == {"v2a", "v2b"}
