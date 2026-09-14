"""Semantic search over ingested legal chunks (pgvector cosine distance).

Plain vector search — the Phase 3 deliverable, kept as-is as an admin debug
tool (`GET /admin/legal-sources/search`) for sanity-checking what an
embedding actually retrieves. The chat pipeline uses hybrid (vector + Postgres
full-text) search instead, fused with Reciprocal Rank Fusion — see
`app.services.rag.retrieval.hybrid_search` (Phase 4) and
docs/adr/0007-hybrid-search-and-grounding.md for why the two are kept separate.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models.legal_document import LegalChunk, LegalDocument
from app.services.ingestion.embed import embed_query


@dataclass(frozen=True, slots=True)
class SearchResult:
    chunk: LegalChunk
    document: LegalDocument
    distance: float


async def semantic_search(
    query: str, *, db: AsyncSession, settings: Settings, top_k: int = 8
) -> list[SearchResult]:
    query_vector = await embed_query(query, settings=settings)

    distance = LegalChunk.embedding.cosine_distance(query_vector).label("distance")
    stmt = (
        select(LegalChunk, LegalDocument, distance)
        .join(LegalDocument, LegalChunk.document_id == LegalDocument.id)
        .order_by(distance)
        .limit(top_k)
    )
    rows = (await db.execute(stmt)).all()
    return [
        SearchResult(chunk=chunk, document=document, distance=float(dist))
        for chunk, document, dist in rows
    ]
