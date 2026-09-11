"""Integration tests for /api/v1/admin/legal-sources/*. Needs Postgres.

fetch/extract/clean/chunk/embed are monkeypatched on `pipeline`/`search` (see
test_ingestion_pipeline.py for pipeline-level coverage) so these focus on
RBAC, HTTP wiring and — for the ranking test — a real pgvector round trip.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.core import security
from app.core.config import get_settings
from app.models.user import User, UserRole
from app.services.ingestion import pipeline as pipeline_module
from app.services.ingestion import search as search_module
from app.services.ingestion.chunk import Chunk
from app.services.ingestion.fetch import FetchedDocument
from tests.conftest import unique_email

DEFAULT_CHUNKS = [
    Chunk(content="Section 1 body.", section="1", article=None, page_number=1),
    Chunk(content="Section 2 body.", section="2", article=None, page_number=1),
]
FAKE_VECTOR = [0.01] * 768


def _patch_pipeline(monkeypatch: pytest.MonkeyPatch, *, chunks: list[Chunk] | None = None) -> None:
    resolved_chunks = DEFAULT_CHUNKS if chunks is None else chunks

    async def fake_fetch(url: str, *, settings: object) -> FetchedDocument:
        return FetchedDocument(
            url=url, content_type="text/html", raw_bytes=b"<p>x</p>", checksum="abc123"
        )

    def fake_extract(document: object) -> str:
        return "irrelevant"

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


async def _admin_headers(db_txn_session: object) -> dict[str, str]:
    user = User(
        email=unique_email("admin"),
        hashed_password=security.hash_password("irrelevant-not-logged-in-with"),
        role=UserRole.ADMIN,
        email_verified=True,
    )
    db_txn_session.add(user)  # type: ignore[attr-defined]
    await db_txn_session.flush()  # type: ignore[attr-defined]
    token = security.create_access_token(
        user_id=user.id, role=UserRole.ADMIN.value, settings=get_settings()
    )
    return {"Authorization": f"Bearer {token}"}


async def _ingest(
    db_client: AsyncClient, headers: dict[str, str], **overrides: object
) -> dict[str, object]:
    payload = {
        "title": "Test Act, 2000",
        "source_url": "https://example.test/act",
        "document_type": "ACT",
        **overrides,
    }
    resp = await db_client.post("/api/v1/admin/legal-sources", json=payload, headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


async def test_ingest_requires_authentication(db_client: AsyncClient) -> None:
    resp = await db_client.post(
        "/api/v1/admin/legal-sources",
        json={"title": "X", "source_url": "https://example.test/x", "document_type": "ACT"},
    )
    assert resp.status_code == 401


async def test_non_admin_cannot_ingest(db_client: AsyncClient) -> None:
    consumer = await db_client.post(
        "/api/v1/auth/register",
        json={"email": unique_email("consumer"), "password": "correct horse battery staple"},
    )
    headers = {"Authorization": f"Bearer {consumer.json()['access_token']}"}
    resp = await db_client.post(
        "/api/v1/admin/legal-sources",
        json={"title": "X", "source_url": "https://example.test/x", "document_type": "ACT"},
        headers=headers,
    )
    assert resp.status_code == 403


async def test_admin_can_ingest_and_list(
    db_client: AsyncClient, db_txn_session: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_pipeline(monkeypatch)
    headers = await _admin_headers(db_txn_session)

    created = await _ingest(db_client, headers, law_name="Information Technology Act")
    assert created["ingestion_status"] == "COMPLETED"
    assert created["chunk_count"] == 2

    listing = await db_client.get("/api/v1/admin/legal-sources", headers=headers)
    assert listing.status_code == 200
    ids = [d["id"] for d in listing.json()["items"]]
    assert created["id"] in ids


async def test_ingestion_failure_is_recorded_not_500(
    db_client: AsyncClient, db_txn_session: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def failing_fetch(url: str, *, settings: object) -> FetchedDocument:
        raise ValueError("network unreachable")

    monkeypatch.setattr(pipeline_module, "fetch_document", failing_fetch)
    headers = await _admin_headers(db_txn_session)

    resp = await db_client.post(
        "/api/v1/admin/legal-sources",
        json={
            "title": "Broken",
            "source_url": "https://example.test/broken",
            "document_type": "OTHER",
        },
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ingestion_status"] == "FAILED"
    assert "network unreachable" in body["ingestion_error"]


async def test_get_and_delete_source(
    db_client: AsyncClient, db_txn_session: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_pipeline(monkeypatch)
    headers = await _admin_headers(db_txn_session)
    created = await _ingest(db_client, headers)
    document_id = created["id"]

    fetched = await db_client.get(f"/api/v1/admin/legal-sources/{document_id}", headers=headers)
    assert fetched.status_code == 200

    deleted = await db_client.delete(f"/api/v1/admin/legal-sources/{document_id}", headers=headers)
    assert deleted.status_code == 204

    gone = await db_client.get(f"/api/v1/admin/legal-sources/{document_id}", headers=headers)
    assert gone.status_code == 404


async def test_reindex_replaces_chunks(
    db_client: AsyncClient, db_txn_session: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_pipeline(
        monkeypatch, chunks=[Chunk(content="v1", section=None, article=None, page_number=1)]
    )
    headers = await _admin_headers(db_txn_session)
    created = await _ingest(db_client, headers)
    assert created["chunk_count"] == 1

    _patch_pipeline(
        monkeypatch,
        chunks=[
            Chunk(content="v2a", section=None, article=None, page_number=1),
            Chunk(content="v2b", section=None, article=None, page_number=1),
        ],
    )
    reindexed = await db_client.post(
        f"/api/v1/admin/legal-sources/{created['id']}/reindex", headers=headers
    )
    assert reindexed.status_code == 200
    assert reindexed.json()["chunk_count"] == 2


async def test_search_orders_by_closest_vector(
    db_client: AsyncClient, db_txn_session: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Two clearly-distinct 768-dim vectors so cosine distance unambiguously
    # favours one — a real pgvector round trip, not just "did it 200".
    vector_a = [1.0] + [0.0] * 767
    vector_b = [0.0] * 767 + [1.0]

    _patch_pipeline(monkeypatch)

    async def two_vectors(texts: list[str], *, settings: object) -> list[list[float]]:
        return [vector_a, vector_b]

    monkeypatch.setattr(pipeline_module, "embed_texts", two_vectors)

    headers = await _admin_headers(db_txn_session)
    await _ingest(db_client, headers)  # chunk[0]="Section 1 body." -> vector_a

    async def query_matches_a(query: str, *, settings: object) -> list[float]:
        return vector_a

    monkeypatch.setattr(search_module, "embed_query", query_matches_a)

    resp = await db_client.get(
        "/api/v1/admin/legal-sources/search", params={"q": "anything"}, headers=headers
    )
    assert resp.status_code == 200
    results = resp.json()["results"]
    assert len(results) == 2
    assert results[0]["section"] == "1"
    assert results[0]["distance"] < results[1]["distance"]
