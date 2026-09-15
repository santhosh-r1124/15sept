"""Integration tests for /api/v1/documents/*. Needs Postgres — see
conftest.db_client. Draft generation is monkeypatched
(app.services.document_assistant.generation.generate_draft) so these test
persistence, RBAC/ownership and validation without needing a real
ANTHROPIC_API_KEY or network access. One test
(`test_create_without_api_key_returns_503`) deliberately does NOT patch it,
to prove the real "not configured" path works end-to-end.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.models.document_request import AssistantDocumentType
from app.services.document_assistant import generation as generation_module
from tests.conftest import unique_email

VALID_AFFIDAVIT_ANSWERS = {
    "purpose": "Name change",
    "full_name": "Jane Doe",
    "address": "123 Main St, Pune",
    "state_code": "mh",
    "facts_to_declare": "I have changed my name from X to Y.",
}


def _patch_generation(
    monkeypatch: pytest.MonkeyPatch, *, draft: str = "DRAFT AFFIDAVIT\n\n..."
) -> None:
    async def fake_generate(
        document_type: AssistantDocumentType, *, answers: dict[str, str], settings: object
    ) -> str:
        return draft

    monkeypatch.setattr(generation_module, "generate_draft", fake_generate)


async def _register(db_client: AsyncClient) -> dict[str, object]:
    resp = await db_client.post(
        "/api/v1/auth/register",
        json={"email": unique_email(), "password": "correct horse battery staple"},
    )
    assert resp.status_code == 201
    return resp.json()


async def test_list_document_types_is_public(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/documents/types")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == len(AssistantDocumentType)
    affidavit = next(t for t in body if t["document_type"] == "AFFIDAVIT")
    keys = {q["key"] for q in affidavit["questions"]}
    assert "full_name" in keys
    assert "state_code" in keys


async def test_create_without_api_key_returns_503(db_client: AsyncClient) -> None:
    # Deliberately unpatched — conftest never sets ANTHROPIC_API_KEY.
    resp = await db_client.post(
        "/api/v1/documents",
        json={"document_type": "AFFIDAVIT", "answers": VALID_AFFIDAVIT_ANSWERS},
    )
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "llm_not_configured"


async def test_create_rejects_missing_required_answers(
    db_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_generation(monkeypatch)
    resp = await db_client.post(
        "/api/v1/documents", json={"document_type": "AFFIDAVIT", "answers": {}}
    )
    assert resp.status_code == 422
    fields = {d["field"] for d in resp.json()["error"]["details"]}
    assert "answers.full_name" in fields
    assert "answers.purpose" in fields


async def test_anonymous_user_can_create_a_draft(
    db_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_generation(monkeypatch)
    resp = await db_client.post(
        "/api/v1/documents",
        json={"document_type": "AFFIDAVIT", "answers": VALID_AFFIDAVIT_ANSWERS},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["document"]["document_type"] == "AFFIDAVIT"
    assert body["document"]["draft_text"] == "DRAFT AFFIDAVIT\n\n..."
    assert body["document"]["state_code"] == "MH"  # normalized to uppercase
    assert body["disclaimer"]


async def test_get_document_request_readable_without_auth_when_anonymous(
    db_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_generation(monkeypatch)
    created = await db_client.post(
        "/api/v1/documents",
        json={"document_type": "AFFIDAVIT", "answers": VALID_AFFIDAVIT_ANSWERS},
    )
    document_id = created.json()["document"]["id"]

    resp = await db_client.get(f"/api/v1/documents/{document_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == document_id


async def test_get_unknown_document_request_is_404(db_client: AsyncClient) -> None:
    resp = await db_client.get("/api/v1/documents/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404


async def test_logged_in_user_document_request_is_listed_and_owned(
    db_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_generation(monkeypatch)
    tokens = await _register(db_client)
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    created = await db_client.post(
        "/api/v1/documents",
        json={"document_type": "AFFIDAVIT", "answers": VALID_AFFIDAVIT_ANSWERS},
        headers=headers,
    )
    document_id = created.json()["document"]["id"]

    listing = await db_client.get("/api/v1/documents", headers=headers)
    assert listing.status_code == 200
    ids = [d["id"] for d in listing.json()]
    assert document_id in ids


async def test_anonymous_cannot_list_document_requests(db_client: AsyncClient) -> None:
    resp = await db_client.get("/api/v1/documents")
    assert resp.status_code == 401


async def test_other_users_cannot_read_an_owned_document_request(
    db_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_generation(monkeypatch)
    owner_tokens = await _register(db_client)
    owner_headers = {"Authorization": f"Bearer {owner_tokens['access_token']}"}
    created = await db_client.post(
        "/api/v1/documents",
        json={"document_type": "AFFIDAVIT", "answers": VALID_AFFIDAVIT_ANSWERS},
        headers=owner_headers,
    )
    document_id = created.json()["document"]["id"]

    other_tokens = await _register(db_client)
    other_headers = {"Authorization": f"Bearer {other_tokens['access_token']}"}

    resp = await db_client.get(f"/api/v1/documents/{document_id}", headers=other_headers)
    assert resp.status_code == 403
