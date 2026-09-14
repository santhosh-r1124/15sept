"""Hybrid search over `legal_chunks`: pgvector cosine similarity + Postgres
full-text search, fused with Reciprocal Rank Fusion (RRF) — Phase 4.

Why RRF instead of a dedicated reranker model: the user asked for free
alternatives only (no paid services) for the rest of this project. RRF is a
simple, well-established rank-fusion technique (Cormack, Clarke & Buettcher,
2009) — it needs no extra model, no extra API call, and no training, and it's
what Postgres/pgvector "hybrid search" reference implementations (e.g.
Supabase's) use for exactly this reason. See docs/adr/0007-hybrid-search-and-grounding.md
for the full writeup, including why a hard cosine-distance threshold was
rejected as a guardrail (uncalibratable without a real corpus — see below).

This is deliberately separate from `app.services.ingestion.search.semantic_search`
(Phase 3's admin debug tool, plain vector search) rather than replacing it —
that endpoint exists to let an admin sanity-check what an embedding actually
retrieves, and hybrid+RRF re-ordering would muddy that signal.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models.legal_document import LegalChunk, LegalDocument
from app.services.ingestion.embed import embed_query

# The original RRF paper found result quality insensitive to k in a wide
# range around 60 — no corpus-specific tuning needed, unlike a raw distance
# cutoff would require.
_RRF_K = 60
# How many candidates each individual ranker (vector, keyword) contributes to
# the fusion pool, before RRF picks the final top_k.
_CANDIDATE_POOL = 20


@dataclass(frozen=True, slots=True)
class RetrievedChunk:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_title: str
    source_url: str
    section: str | None
    article: str | None
    content: str


def reciprocal_rank_fusion[T](ranked_lists: Sequence[Sequence[T]], *, k: int = _RRF_K) -> list[T]:
    """Combine several ranked ID lists into one, by summing ``1/(k+rank)``
    across lists. An ID that appears near the top of *either* list, or
    moderately high in *both*, outranks one that only ever appears near the
    top of a single list — that's the whole point of fusing two different
    retrieval signals instead of picking one.
    """
    scores: dict[T, float] = {}
    for ranked in ranked_lists:
        for rank, item in enumerate(ranked, start=1):
            scores[item] = scores.get(item, 0.0) + 1.0 / (k + rank)
    return sorted(scores, key=lambda item: scores[item], reverse=True)


async def _vector_ranked_ids(
    query_vector: list[float], *, db: AsyncSession, limit: int
) -> list[uuid.UUID]:
    distance = LegalChunk.embedding.cosine_distance(query_vector)
    stmt = select(LegalChunk.id).order_by(distance).limit(limit)
    return list((await db.execute(stmt)).scalars().all())


async def _keyword_ranked_ids(query: str, *, db: AsyncSession, limit: int) -> list[uuid.UUID]:
    # plainto_tsquery treats the input as plain text tokens (not tsquery
    # syntax), so arbitrary user input can't raise a syntax error here; an
    # all-stopword/empty query safely produces an empty tsquery that matches
    # nothing rather than erroring.
    tsquery = func.plainto_tsquery("english", query)
    stmt = (
        select(LegalChunk.id)
        .where(LegalChunk.content_tsv.op("@@")(tsquery))
        .order_by(func.ts_rank(LegalChunk.content_tsv, tsquery).desc())
        .limit(limit)
    )
    return list((await db.execute(stmt)).scalars().all())


async def hybrid_search(
    query: str, *, db: AsyncSession, settings: Settings, top_k: int = 6
) -> list[RetrievedChunk]:
    query_vector = await embed_query(query, settings=settings)
    vector_ids = await _vector_ranked_ids(query_vector, db=db, limit=_CANDIDATE_POOL)
    keyword_ids = await _keyword_ranked_ids(query, db=db, limit=_CANDIDATE_POOL)

    fused_ids = reciprocal_rank_fusion([vector_ids, keyword_ids])[:top_k]
    if not fused_ids:
        return []

    stmt = (
        select(LegalChunk, LegalDocument)
        .join(LegalDocument, LegalChunk.document_id == LegalDocument.id)
        .where(LegalChunk.id.in_(fused_ids))
    )
    rows = (await db.execute(stmt)).all()
    by_id = {chunk.id: (chunk, document) for chunk, document in rows}

    results: list[RetrievedChunk] = []
    for chunk_id in fused_ids:
        pair = by_id.get(chunk_id)
        if pair is None:  # pragma: no cover - defensive, shouldn't happen
            continue
        chunk, document = pair
        results.append(
            RetrievedChunk(
                chunk_id=chunk.id,
                document_id=document.id,
                document_title=document.title,
                source_url=document.source_url,
                section=chunk.section,
                article=chunk.article,
                content=chunk.content,
            )
        )
    return results
