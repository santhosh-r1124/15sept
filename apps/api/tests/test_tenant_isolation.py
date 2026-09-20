"""Tenant isolation for enterprise users (Phase 13). Needs Postgres (pgvector + full-text search).

The property under test: an organisation's private legal documents can be retrieved by its members
and by nobody else - not by another organisation, not by a plain consumer, not by an anonymous
visitor - through *either* ranking signal, and even if a ranker were to misbehave.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, select

from app.core.config import get_settings
from app.models.audit import AuditLog
from app.models.legal_document import DocumentType, LegalChunk, LegalDocument
from app.models.organization import Organization
from app.models.user import User, UserRole
from app.services import legal_classifier
from app.services.rag import retrieval as retrieval_module
from tests.helpers import Account, make_admin, register_advocate, register_consumer

ADMIN = "/api/v1/admin"
DIM = 768


def _vec(index: int) -> list[float]:
    vector = [0.0] * DIM
    vector[index] = 1.0
    return vector


async def _document(
    session: Any, title: str, content: str, embedding: list[float], org: uuid.UUID | None
) -> LegalChunk:
    document = LegalDocument(
        title=title,
        source_url=f"https://example.test/{uuid.uuid4().hex}",
        document_type=DocumentType.OTHER,
        checksum="x",
        organization_id=org,
    )
    session.add(document)
    await session.flush()
    chunk = LegalChunk(document_id=document.id, chunk_index=0, content=content, embedding=embedding)
    session.add(chunk)
    await session.commit()
    return chunk


class World:
    """Two organisations, each with a private document, plus one public document."""

    def __init__(self, session: Any) -> None:
        self.session = session
        self.acme = Organization(name=f"Acme {uuid.uuid4().hex[:6]}")
        self.zenith = Organization(name=f"Zenith {uuid.uuid4().hex[:6]}")


@pytest.fixture
async def world(db_txn_session: Any) -> World:
    w = World(db_txn_session)
    db_txn_session.add_all([w.acme, w.zenith])
    await db_txn_session.flush()
    w.public = await _document(
        db_txn_session,
        "Payment of Gratuity Act",
        "The gratuity statute applies to all.",
        _vec(1),
        None,
    )
    w.acme_doc = await _document(
        db_txn_session,
        "Acme HR policy",
        "Acme confidential gratuity policy for staff.",
        _vec(2),
        w.acme.id,
    )
    w.zenith_doc = await _document(
        db_txn_session,
        "Zenith HR policy",
        "Zenith secret gratuity policy for staff.",
        _vec(3),
        w.zenith.id,
    )
    return w


async def _search(
    world: World, org: uuid.UUID | None, *, query: str = "gratuity policy", vector: int = 3
) -> set[str]:
    async def fake_embed(text: str, *, settings: object) -> list[float]:
        return _vec(vector)

    retrieval_module.embed_query = fake_embed  # type: ignore[assignment]
    results = await retrieval_module.hybrid_search(
        query, db=world.session, settings=get_settings(), organization_id=org
    )
    return {r.document_title for r in results}


@pytest.fixture(autouse=True)
def _restore_embedder() -> Any:
    original = retrieval_module.embed_query
    yield
    retrieval_module.embed_query = original


# --- retrieval ---------------------------------------------------------------------------------


async def test_members_search_the_public_corpus_and_their_own_documents(world: World) -> None:
    # The query is closest to Zenith's chunk, so a leak would show up at the very top.
    assert await _search(world, world.acme.id) == {"Payment of Gratuity Act", "Acme HR policy"}


async def test_another_organisation_never_sees_them(world: World) -> None:
    assert await _search(world, world.zenith.id, vector=2) == {
        "Payment of Gratuity Act",
        "Zenith HR policy",
    }


async def test_someone_with_no_organisation_sees_the_public_corpus_only(world: World) -> None:
    assert await _search(world, None) == {"Payment of Gratuity Act"}


async def test_the_keyword_ranker_is_filtered_too(world: World) -> None:
    # A vector nothing matches, so only the keyword signal ("gratuity") can find anything.
    titles = await _search(world, world.acme.id, vector=100)

    assert titles == {"Payment of Gratuity Act", "Acme HR policy"}


async def test_the_vector_ranker_is_filtered_too(world: World) -> None:
    # A query with no keyword overlap, so only the vector signal can find anything.
    titles = await _search(world, None, query="xyzzy", vector=3)

    assert "Zenith HR policy" not in titles
    assert "Acme HR policy" not in titles


async def test_the_final_load_refilters_even_if_a_ranker_forgets_to(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Defence in depth: simulate a ranker that returns every chunk, filter or no filter."""
    every_chunk = [world.public.id, world.acme_doc.id, world.zenith_doc.id]

    async def leaky_vector(*_a: object, **_k: object) -> list[uuid.UUID]:
        return every_chunk

    async def leaky_keyword(*_a: object, **_k: object) -> list[uuid.UUID]:
        return every_chunk

    monkeypatch.setattr(retrieval_module, "_vector_ranked_ids", leaky_vector)
    monkeypatch.setattr(retrieval_module, "_keyword_ranked_ids", leaky_keyword)

    assert await _search(world, world.acme.id) == {"Payment of Gratuity Act", "Acme HR policy"}
    assert await _search(world, None) == {"Payment of Gratuity Act"}


async def test_the_organisation_argument_cannot_be_forgotten(world: World) -> None:
    with pytest.raises(TypeError):
        await retrieval_module.hybrid_search(  # type: ignore[call-arg]
            "gratuity", db=world.session, settings=get_settings()
        )


# --- chat searches as the asking user's organisation -------------------------------------------


async def _enterprise_member(
    client: AsyncClient, session: Any, org_id: uuid.UUID
) -> tuple[Account, Account]:
    admin = await make_admin(session)
    member = await register_consumer(client)
    resp = await client.put(
        f"{ADMIN}/users/{member.user_id}/organization",
        json={"organization_id": str(org_id)},
        headers=admin.headers,
    )
    assert resp.status_code == 200, resp.text
    return admin, member


async def test_chat_passes_the_askers_organisation_to_retrieval(
    db_client: AsyncClient, db_txn_session: Any, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    _admin, member = await _enterprise_member(db_client, db_txn_session, world.acme.id)
    plain = await register_consumer(db_client)
    seen: list[uuid.UUID | None] = []

    async def spy(query: str, *, db: object, settings: object, organization_id: Any) -> list[Any]:
        seen.append(organization_id)
        return []

    async def classify(message: str, *, settings: object) -> Any:
        return legal_classifier.Classification("EMPLOYMENT_LAW", "CENTRAL", "LOW", False)

    monkeypatch.setattr(retrieval_module, "hybrid_search", spy)
    monkeypatch.setattr(legal_classifier, "classify_query", classify)
    ask = {"message": "What is our gratuity policy?"}

    await db_client.post("/api/v1/chat/messages", json=ask)  # anonymous
    await db_client.post("/api/v1/chat/messages", json=ask, headers=plain.headers)
    await db_client.post("/api/v1/chat/messages", json=ask, headers=member.headers)

    assert seen == [None, None, world.acme.id]


# --- managing organisations --------------------------------------------------------------------


async def test_only_admins_manage_organisations(
    db_client: AsyncClient, db_txn_session: Any
) -> None:
    consumer = await register_consumer(db_client)
    for method, url in (("POST", f"{ADMIN}/organizations"), ("GET", f"{ADMIN}/organizations")):
        resp = await db_client.request(
            method, url, json={"name": "X Corp"}, headers=consumer.headers
        )
        assert resp.status_code == 403
    assert (await db_client.get(f"{ADMIN}/organizations")).status_code == 401


async def test_creating_an_organisation_is_audited_and_names_are_unique(
    db_client: AsyncClient, db_txn_session: Any
) -> None:
    admin = await make_admin(db_txn_session)

    created = await db_client.post(
        f"{ADMIN}/organizations", json={"name": "  Globex   Ltd "}, headers=admin.headers
    )
    duplicate = await db_client.post(
        f"{ADMIN}/organizations", json={"name": "globex ltd"}, headers=admin.headers
    )

    assert created.status_code == 201
    assert created.json()["name"] == "Globex Ltd"  # whitespace normalised
    assert (created.json()["member_count"], created.json()["document_count"]) == (0, 0)
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "organization_exists"
    entry = await db_txn_session.scalar(select(AuditLog).where(AuditLog.action == "org.create"))
    assert entry.target_id == created.json()["id"]


async def test_the_list_shows_members_and_private_documents(
    db_client: AsyncClient, db_txn_session: Any, world: World
) -> None:
    admin, _member = await _enterprise_member(db_client, db_txn_session, world.acme.id)

    listing = (await db_client.get(f"{ADMIN}/organizations", headers=admin.headers)).json()

    by_id = {o["id"]: o for o in listing}
    assert by_id[str(world.acme.id)]["member_count"] == 1
    assert by_id[str(world.acme.id)]["document_count"] == 1
    assert by_id[str(world.zenith.id)]["member_count"] == 0
    assert by_id[str(world.zenith.id)]["document_count"] == 1


async def test_joining_makes_a_consumer_an_enterprise_user_and_leaving_reverses_it(
    db_client: AsyncClient, db_txn_session: Any, world: World
) -> None:
    admin, member = await _enterprise_member(db_client, db_txn_session, world.acme.id)

    me = (await db_client.get("/api/v1/users/me", headers=member.headers)).json()
    assert (me["role"], me["organization_id"]) == ("ENTERPRISE_USER", str(world.acme.id))

    left = await db_client.put(
        f"{ADMIN}/users/{member.user_id}/organization",
        json={"organization_id": None},
        headers=admin.headers,
    )
    assert left.status_code == 200
    assert (left.json()["role"], left.json()["organization_id"]) == ("CONSUMER", None)
    entries = (
        (
            await db_txn_session.execute(
                select(AuditLog).where(AuditLog.action == "user.organization.set")
            )
        )
        .scalars()
        .all()
    )
    assert len(entries) == 2


async def test_only_ordinary_accounts_can_join_an_organisation(
    db_client: AsyncClient, db_txn_session: Any, world: World
) -> None:
    admin = await make_admin(db_txn_session)
    advocate = await register_advocate(db_client, db_txn_session)
    other_admin = await make_admin(db_txn_session, UserRole.LEGAL_ADMIN)
    body = {"organization_id": str(world.acme.id)}

    for target in (advocate.user_id, other_admin.user_id):
        resp = await db_client.put(
            f"{ADMIN}/users/{target}/organization", json=body, headers=admin.headers
        )
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "not_assignable"
    plain = await register_consumer(db_client)
    missing_user = await db_client.put(
        f"{ADMIN}/users/{uuid.uuid4()}/organization", json=body, headers=admin.headers
    )
    unknown_org = await db_client.put(
        f"{ADMIN}/users/{plain.user_id}/organization",
        json={"organization_id": str(uuid.uuid4())},
        headers=admin.headers,
    )
    assert missing_user.status_code == 404
    assert unknown_org.status_code == 404


async def test_ingesting_into_an_unknown_organisation_is_refused_before_any_fetching(
    db_client: AsyncClient, db_txn_session: Any
) -> None:
    admin = await make_admin(db_txn_session)

    resp = await db_client.post(
        f"{ADMIN}/legal-sources",
        json={
            "title": "Internal memo",
            "source_url": "https://example.test/memo.pdf",
            "document_type": "OTHER",
            "organization_id": str(uuid.uuid4()),
        },
        headers=admin.headers,
    )

    assert resp.status_code == 404


async def test_the_source_list_shows_which_documents_are_private(
    db_client: AsyncClient, db_txn_session: Any, world: World
) -> None:
    admin = await make_admin(db_txn_session)

    items = (
        await db_client.get(f"{ADMIN}/legal-sources", params={"limit": 100}, headers=admin.headers)
    ).json()["items"]

    owners = {i["title"]: i["organization_id"] for i in items}
    assert owners["Acme HR policy"] == str(world.acme.id)
    assert owners["Payment of Gratuity Act"] is None


async def test_deleting_an_organisation_removes_its_private_documents_and_frees_its_members(
    db_client: AsyncClient, db_txn_session: Any, world: World
) -> None:
    _admin, member = await _enterprise_member(db_client, db_txn_session, world.acme.id)

    await db_txn_session.execute(delete(Organization).where(Organization.id == world.acme.id))
    await db_txn_session.commit()

    titles = set(
        (
            await db_txn_session.execute(
                select(LegalDocument.title).where(
                    LegalDocument.title.in_(["Acme HR policy", "Zenith HR policy"])
                )
            )
        ).scalars()
    )
    assert titles == {"Zenith HR policy"}  # Acme's private document went with it
    user = await db_txn_session.scalar(select(User).where(User.id == uuid.UUID(member.user_id)))
    await db_txn_session.refresh(user)
    assert user.organization_id is None
