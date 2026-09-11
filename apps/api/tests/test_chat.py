"""Integration tests for the chat endpoints. Needs Postgres — see conftest.db_client.

The LLM calls themselves are monkeypatched (app.services.llm.classify_query /
generate_answer) so these test persistence, RBAC/ownership and routing logic
without needing a real ANTHROPIC_API_KEY or network access. One test
(`test_send_message_without_api_key_returns_503`) deliberately does NOT patch
anything, to prove the real "not configured" path works end-to-end.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.core.legal_text import OUT_OF_SCOPE_MESSAGE
from app.services import llm as llm_module
from tests.conftest import unique_email

IT_LAW_CLASSIFICATION = llm_module.Classification(
    category="IT_LAW", jurisdiction_scope="CENTRAL", is_out_of_scope=False
)
OUT_OF_SCOPE_CLASSIFICATION = llm_module.Classification(
    category="OUT_OF_SCOPE", jurisdiction_scope="UNKNOWN", is_out_of_scope=True
)


def _patch_llm(
    monkeypatch: pytest.MonkeyPatch,
    *,
    classification: llm_module.Classification = IT_LAW_CLASSIFICATION,
    answer: str = "Here is some general information about that.",
    record_history: list[list[tuple[str, str]]] | None = None,
) -> None:
    async def fake_classify(message: str, *, settings: object) -> llm_module.Classification:
        return classification

    async def fake_generate(
        message: str, *, history: list[tuple[str, str]], settings: object
    ) -> str:
        if record_history is not None:
            record_history.append(history)
        return answer

    monkeypatch.setattr(llm_module, "classify_query", fake_classify)
    monkeypatch.setattr(llm_module, "generate_answer", fake_generate)


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
    assert body["assistant_message"]["role"] == "assistant"
    assert body["assistant_message"]["content"] == "Here is some general information about that."
    assert body["disclaimer"]


async def test_out_of_scope_short_circuits_generation(
    db_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    generate_called = False

    async def fake_generate(*_args: object, **_kwargs: object) -> str:
        nonlocal generate_called
        generate_called = True
        return "should not be reached"

    async def fake_classify(*_args: object, **_kwargs: object) -> llm_module.Classification:
        return OUT_OF_SCOPE_CLASSIFICATION

    monkeypatch.setattr(llm_module, "classify_query", fake_classify)
    monkeypatch.setattr(llm_module, "generate_answer", fake_generate)

    resp = await db_client.post("/api/v1/chat/messages", json={"message": "write me a poem"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["assistant_message"]["content"] == OUT_OF_SCOPE_MESSAGE
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
