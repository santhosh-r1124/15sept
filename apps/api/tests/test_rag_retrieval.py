"""Tests for app.services.rag.retrieval.

`reciprocal_rank_fusion` is pure logic (no DB) — the fusion math is the part
most worth getting right and easiest to get subtly wrong, so it's tested in
isolation with plain lists. `hybrid_search` needs a real Postgres (pgvector +
the generated `content_tsv` column both have to actually work), so that part
is one integration test — see conftest.db_txn_session.
"""

from __future__ import annotations

import pytest

from app.core.config import get_settings
from app.models.legal_document import DocumentType, LegalChunk, LegalDocument
from app.services.rag import retrieval as retrieval_module
from app.services.rag.retrieval import reciprocal_rank_fusion

# ---------------------------------------------------------------------------
# reciprocal_rank_fusion — pure logic, no DB
# ---------------------------------------------------------------------------


def test_rrf_ranks_item_present_in_both_lists_above_single_list_items() -> None:
    # "b" is #2 in one list and #1 in the other — it should outrank "a" and
    # "c", which each only appear once.
    vector_ranked = ["a", "b", "c"]
    keyword_ranked = ["b", "d", "e"]

    fused = reciprocal_rank_fusion([vector_ranked, keyword_ranked])

    assert fused[0] == "b"
    assert set(fused) == {"a", "b", "c", "d", "e"}


def test_rrf_preserves_order_for_a_single_list() -> None:
    assert reciprocal_rank_fusion([["x", "y", "z"]]) == ["x", "y", "z"]


def test_rrf_handles_empty_lists() -> None:
    assert reciprocal_rank_fusion([]) == []
    assert reciprocal_rank_fusion([[], []]) == []


def test_rrf_can_let_a_dual_signal_item_outrank_a_single_signal_top_rank() -> None:
    # This is the actual point of fusing two signals rather than picking one:
    # "49" is the *worst* vector match (rank 50 of 50) but the *only* keyword
    # match, while "0" is the best vector match but has no keyword support at
    # all. Appearing in both ranked lists lets "49" outscore "0".
    long_list = [str(i) for i in range(50)]  # "0" = vector rank 1 ... "49" = vector rank 50
    fused = reciprocal_rank_fusion([long_list, ["49"]])
    assert fused[0] == "49"


# ---------------------------------------------------------------------------
# hybrid_search — needs Postgres (pgvector + generated tsvector column)
# ---------------------------------------------------------------------------


async def test_hybrid_search_fuses_vector_and_keyword_signals(
    db_txn_session: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    document = LegalDocument(
        title="Digital Personal Data Protection Act, 2023",
        source_url="https://example.test/dpdpa",
        document_type=DocumentType.ACT,
        checksum="abc",
    )
    db_txn_session.add(document)  # type: ignore[attr-defined]
    await db_txn_session.commit()  # type: ignore[attr-defined]

    # relevant: matches the query both semantically (vector) and lexically
    # ("data fiduciary" appears verbatim).
    relevant_vector = [1.0] + [0.0] * 767
    relevant = LegalChunk(
        document_id=document.id,
        chunk_index=0,
        content="A data fiduciary must obtain consent before processing personal data.",
        embedding=relevant_vector,
    )
    # unrelated on both axes.
    unrelated = LegalChunk(
        document_id=document.id,
        chunk_index=1,
        content="Filing fees for a company incorporation form are prescribed separately.",
        embedding=[0.0] * 767 + [1.0],
    )
    db_txn_session.add_all([relevant, unrelated])  # type: ignore[attr-defined]
    await db_txn_session.commit()  # type: ignore[attr-defined]

    async def fake_embed_query(query: str, *, settings: object) -> list[float]:
        return relevant_vector

    monkeypatch.setattr(retrieval_module, "embed_query", fake_embed_query)

    results = await retrieval_module.hybrid_search(
        "data fiduciary consent",
        db=db_txn_session,
        settings=get_settings(),  # type: ignore[arg-type]
        organization_id=None,
    )

    assert len(results) == 2
    assert results[0].chunk_id == relevant.id
    assert results[0].document_title == document.title


async def test_hybrid_search_returns_empty_list_when_no_chunks_exist(
    db_txn_session: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_embed_query(query: str, *, settings: object) -> list[float]:
        return [0.0] * 768

    monkeypatch.setattr(retrieval_module, "embed_query", fake_embed_query)

    results = await retrieval_module.hybrid_search(
        "anything",
        db=db_txn_session,
        settings=get_settings(),  # type: ignore[arg-type]
        organization_id=None,
    )
    assert results == []
