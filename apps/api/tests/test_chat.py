"""Integration tests for the chat endpoints. Needs Postgres — see conftest.db_client.

The classifier, LLM and retrieval calls are monkeypatched
(app.services.legal_classifier.classify_query, app.services.llm.generate_grounded_answer,
app.services.rag.retrieval.hybrid_search) so these test persistence,
RBAC/ownership and routing logic without needing a real ANTHROPIC_API_KEY,
GEMINI_API_KEY, or network access. One test
(`test_send_message_without_api_key_returns_503`) deliberately does NOT patch
anything, to prove the real "not configured" path works end-to-end.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from app.core.legal_text import (
    ADVOCATE_RECOMMENDATION_MESSAGE,
    INSUFFICIENT_EVIDENCE_MESSAGE,
    OUT_OF_SCOPE_MESSAGE,
)
from app.services import legal_classifier
from app.services import llm as llm_module
from app.services.rag import retrieval as retrieval_module
from app.services.rag.retrieval import RetrievedChunk
from tests.conftest import unique_email

IT_LAW_CLASSIFICATION = legal_classifier.Classification(
    category="IT_LAW", jurisdiction_scope="CENTRAL", risk_level="LOW", is_out_of_scope=False
)
HIGH_RISK_CLASSIFICATION = legal_classifier.Classification(
    category="ADVOCATE_REQUIRED",
    jurisdiction_scope="COURT",
    risk_level="HIGH",
    is_out_of_scope=False,
)
OUT_OF_SCOPE_CLASSIFICATION = legal_classifier.Classification(
    category="OUT_OF_SCOPE", jurisdiction_scope="UNKNOWN", risk_level="LOW", is_out_of_scope=True
)
FAKE_CHUNK = RetrievedChunk(
    chunk_id=uuid.uuid4(),
    document_id=uuid.uuid4(),
    document_title="Test Act, 2000",
    source_url="https://example.test/act",
    section="1",
    article=None,
    content="Some legal text.",
)


def _patch_llm(
    monkeypatch: pytest.MonkeyPatch,
    *,
    classification: legal_classifier.Classification = IT_LAW_CLASSIFICATION,
    answer: str = "Here is some general information about that. [1]",
    retrieved: list[RetrievedChunk] | None = None,
    record_history: list[list[tuple[str, str]]] | None = None,
) -> None:
    resolved_retrieved = [FAKE_CHUNK] if retrieved is None else retrieved

    async def fake_classify(message: str, *, settings: object) -> legal_classifier.Classification:
        return classification

    async def fake_search(query: str, *, db: object, settings: object) -> list[RetrievedChunk]:
        return resolved_retrieved

    async def fake_generate(
        message: str,
        *,
        history: list[tuple[str, str]],
        context: list[RetrievedChunk],
        settings: object,
    ) -> str:
        if record_history is not None:
            record_history.append(history)
        return answer

    monkeypatch.setattr(legal_classifier, "classify_query", fake_classify)
    monkeypatch.setattr(retrieval_module, "hybrid_search", fake_search)
    monkeypatch.setattr(llm_module, "generate_grounded_answer", fake_generate)


async def _register(db_client: AsyncClient) -> dict[str, object]:
    resp = await db_client.post(
        "/api/v1/auth/register",
        json={"email": unique_email(), "password": "correct horse battery staple"},
    )
    assert resp.status_code == 201
    return resp.json()


async def test_send_message_without_api_key_returns_503(db_client: AsyncClient) -> None:
    # Deliberately unpatched — conftest never sets ANTHROPIC_API_KEY.
    resp = await db_client.post("/api/v1/chat/messages", json={"message": "What is an affidavit?"})
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "llm_not_configured"


async def test_anonymous_user_can_chat(
    db_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_llm(monkeypatch)
    resp = await db_client.post("/api/v1/chat/messages", json={"message": "What is an affidavit?"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["conversation_id"]
    assert body["user_message"]["role"] == "user"
    assert body["user_message"]["legal_category"] == "IT_LAW"
    expected_answer = "Here is some general information about that. [1]"
    assert body["assistant_message"]["role"] == "assistant"
    assert body["assistant_message"]["content"] == expected_answer
    assert body["assistant_message"]["sources"] == [
        {
            "document_id": str(FAKE_CHUNK.document_id),
            "document_title": FAKE_CHUNK.document_title,
            "section": FAKE_CHUNK.section,
            "article": FAKE_CHUNK.article,
            "source_url": FAKE_CHUNK.source_url,
        }
    ]
    assert body["disclaimer"]
    assert body["user_message"]["risk_level"] == "LOW"


async def test_high_risk_appends_advocate_recommendation(
    db_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_llm(monkeypatch, classification=HIGH_RISK_CLASSIFICATION, answer="Here's what applies.")
    resp = await db_client.post(
        "/api/v1/chat/messages", json={"message": "I got a legal notice from a vendor"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["user_message"]["risk_level"] == "HIGH"
    assert body["assistant_message"]["content"] == (
        f"Here's what applies.\n\n{ADVOCATE_RECOMMENDATION_MESSAGE}"
    )


async def test_high_risk_advocate_recommendation_also_applies_to_insufficient_evidence(
    db_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_llm(monkeypatch, classification=HIGH_RISK_CLASSIFICATION, retrieved=[])
    resp = await db_client.post(
        "/api/v1/chat/messages", json={"message": "I got a legal notice from a vendor"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["assistant_message"]["content"] == (
        f"{INSUFFICIENT_EVIDENCE_MESSAGE}\n\n{ADVOCATE_RECOMMENDATION_MESSAGE}"
    )


async def test_low_risk_does_not_append_advocate_recommendation(
    db_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_llm(monkeypatch, answer="Plain answer, no recommendation needed.")
    resp = await db_client.post("/api/v1/chat/messages", json={"message": "What is an affidavit?"})
    assert resp.status_code == 200
    content = resp.json()["assistant_message"]["content"]
    assert content == "Plain answer, no recommendation needed."
    assert ADVOCATE_RECOMMENDATION_MESSAGE not in content


async def test_insufficient_evidence_short_circuits_generation(
    db_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    generate_called = False

    async def fake_generate(*_args: object, **_kwargs: object) -> str:
        nonlocal generate_called
        generate_called = True
        return "should not be reached"

    _patch_llm(monkeypatch, retrieved=[])
    monkeypatch.setattr(llm_module, "generate_grounded_answer", fake_generate)

    resp = await db_client.post("/api/v1/chat/messages", json={"message": "What is an affidavit?"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["assistant_message"]["content"] == INSUFFICIENT_EVIDENCE_MESSAGE
    assert body["assistant_message"]["sources"] == []
    assert generate_called is False


async def test_retrieval_unavailable_falls_back_to_insufficient_evidence(
    db_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.core.errors import ServiceUnavailableError

    async def raising_search(query: str, *, db: object, settings: object) -> list[RetrievedChunk]:
        raise ServiceUnavailableError("no key", code="embeddings_not_configured")

    async def fake_classify(message: str, *, settings: object) -> legal_classifier.Classification:
        return IT_LAW_CLASSIFICATION

    monkeypatch.setattr(legal_classifier, "classify_query", fake_classify)
    monkeypatch.setattr(retrieval_module, "hybrid_search", raising_search)

    resp = await db_client.post("/api/v1/chat/messages", json={"message": "What is an affidavit?"})
    assert resp.status_code == 200
    assert resp.json()["assistant_message"]["content"] == INSUFFICIENT_EVIDENCE_MESSAGE


async def test_out_of_scope_short_circuits_generation(
    db_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    generate_called = False

    async def fake_generate(*_args: object, **_kwargs: object) -> str:
        nonlocal generate_called
        generate_called = True
        return "should not be reached"

    async def fake_classify(*_args: object, **_kwargs: object) -> legal_classifier.Classification:
        return OUT_OF_SCOPE_CLASSIFICATION

    monkeypatch.setattr(legal_classifier, "classify_query", fake_classify)
    monkeypatch.setattr(llm_module, "generate_grounded_answer", fake_generate)

    resp = await db_client.post("/api/v1/chat/messages", json={"message": "write me a poem"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["assistant_message"]["content"] == OUT_OF_SCOPE_MESSAGE
    assert body["assistant_message"]["sources"] is None
    assert body["user_message"]["is_out_of_scope"] is True
    assert generate_called is False


async def test_continuing_a_conversation_passes_history(
    db_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    history_calls: list[list[tuple[str, str]]] = []
    _patch_llm(monkeypatch, record_history=history_calls)

    first = await db_client.post("/api/v1/chat/messages", json={"message": "What is a contract?"})
    conversation_id = first.json()["conversation_id"]

    second = await db_client.post(
        "/api/v1/chat/messages",
        json={"conversation_id": conversation_id, "message": "And an agreement?"},
    )
    assert second.status_code == 200
    assert second.json()["conversation_id"] == conversation_id

    assert len(history_calls) == 2
    assert history_calls[0] == []  # first message: no prior history
    assert len(history_calls[1]) == 2  # second message: sees the first Q&A pair


async def test_logged_in_user_conversation_is_listed(
    db_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_llm(monkeypatch)
    tokens = await _register(db_client)
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    sent = await db_client.post(
        "/api/v1/chat/messages", json={"message": "What is an NDA?"}, headers=headers
    )
    conversation_id = sent.json()["conversation_id"]

    listing = await db_client.get("/api/v1/chat/conversations", headers=headers)
    assert listing.status_code == 200
    ids = [c["id"] for c in listing.json()]
    assert conversation_id in ids


async def test_anonymous_cannot_list_conversations(db_client: AsyncClient) -> None:
    resp = await db_client.get("/api/v1/chat/conversations")
    assert resp.status_code == 401


async def test_anonymous_conversation_is_readable_without_auth(
    db_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_llm(monkeypatch)
    sent = await db_client.post("/api/v1/chat/messages", json={"message": "What is bail?"})
    conversation_id = sent.json()["conversation_id"]

    resp = await db_client.get(f"/api/v1/chat/conversations/{conversation_id}")
    assert resp.status_code == 200
    assert len(resp.json()["messages"]) == 2


async def test_users_cannot_read_each_others_conversations(
    db_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_llm(monkeypatch)
    owner_tokens = await _register(db_client)
    owner_headers = {"Authorization": f"Bearer {owner_tokens['access_token']}"}
    sent = await db_client.post(
        "/api/v1/chat/messages", json={"message": "confidential question"}, headers=owner_headers
    )
    conversation_id = sent.json()["conversation_id"]

    other_tokens = await _register(db_client)
    other_headers = {"Authorization": f"Bearer {other_tokens['access_token']}"}

    read = await db_client.get(
        f"/api/v1/chat/conversations/{conversation_id}", headers=other_headers
    )
    assert read.status_code == 403

    reply = await db_client.post(
        "/api/v1/chat/messages",
        json={"conversation_id": conversation_id, "message": "trying to butt in"},
        headers=other_headers,
    )
    assert reply.status_code == 403


async def test_get_unknown_conversation_is_404(db_client: AsyncClient) -> None:
    resp = await db_client.get("/api/v1/chat/conversations/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404
