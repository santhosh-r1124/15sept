"""Integration tests for the admin & legal-ops endpoints (Phase 12). Needs Postgres.

The test database can hold committed rows from other tests, so these assert on ids and on
before/after differences rather than on absolute counts.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.chat import ChatMessage, Conversation, MessageRole
from app.models.user import UserRole
from tests.helpers import (
    Account,
    advance_matter,
    book_matter,
    make_admin,
    register_advocate,
    register_consumer,
)

ADMIN = "/api/v1/admin"
T0 = datetime(2026, 1, 1, 12, 0)  # chat_messages.created_at is a naive timestamp


async def _chat(
    session: Any,
    *,
    question: str,
    risk: str | None,
    at: datetime,
    answer: str | None = "Here is some general information.",
    sources: list[dict[str, object]] | None = None,
    owner: str | None = None,
    reviewed: bool = False,
) -> ChatMessage:
    conversation = Conversation(user_id=uuid.UUID(owner) if owner else None, title=question[:60])
    session.add(conversation)
    await session.flush()
    asked = ChatMessage(
        conversation_id=conversation.id,
        role=MessageRole.USER,
        content=question,
        legal_category="CRIMINAL_LAW",
        jurisdiction_scope="STATE",
        is_out_of_scope=False,
        risk_level=risk,
        created_at=at,
    )
    session.add(asked)
    if answer is not None:
        session.add(
            ChatMessage(
                conversation_id=conversation.id,
                role=MessageRole.ASSISTANT,
                content=answer,
                sources=sources,
                created_at=at + timedelta(seconds=1),
            )
        )
    if reviewed:
        asked.reviewed_at = at + timedelta(minutes=5)
        asked.review_note = "Already handled"
    await session.commit()
    return asked


async def _overview(client: AsyncClient, admin: Account) -> dict[str, Any]:
    resp = await client.get(f"{ADMIN}/overview", headers=admin.headers)
    assert resp.status_code == 200, resp.text
    return dict(resp.json())


# --- access control ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path", ["/overview", "/matters", "/advocates", "/reviews", "/users", "/advocates/pending"]
)
async def test_admin_endpoints_reject_everyone_else(
    db_client: AsyncClient, db_txn_session: Any, path: str
) -> None:
    consumer = await register_consumer(db_client)
    advocate = await register_advocate(db_client, db_txn_session)

    assert (await db_client.get(f"{ADMIN}{path}")).status_code == 401
    assert (await db_client.get(f"{ADMIN}{path}", headers=consumer.headers)).status_code == 403
    assert (await db_client.get(f"{ADMIN}{path}", headers=advocate.headers)).status_code == 403


async def test_legal_admins_have_access_too(db_client: AsyncClient, db_txn_session: Any) -> None:
    legal_admin = await make_admin(db_txn_session, UserRole.LEGAL_ADMIN)

    for path in ("/overview", "/matters", "/advocates", "/reviews"):
        resp = await db_client.get(f"{ADMIN}{path}", headers=legal_admin.headers)
        assert resp.status_code == 200, path


# --- overview ---------------------------------------------------------------------------------


async def test_overview_is_zero_filled_and_tracks_changes(
    db_client: AsyncClient, db_txn_session: Any
) -> None:
    admin = await make_admin(db_txn_session)
    before = await _overview(db_client, admin)
    # Every breakdown lists every key, so the dashboard never has to guess.
    assert set(before["users_by_role"]) == {r.value for r in UserRole}
    assert {"PENDING", "IN_REVIEW", "VERIFIED", "REJECTED"} == set(before["advocates_by_status"])
    assert "PAID" in before["matters_by_status"]
    assert {"PENDING", "PROCESSING", "COMPLETED", "FAILED"} == set(before["sources_by_status"])

    consumer = await register_consumer(db_client)
    verified = await register_advocate(db_client, db_txn_session)
    await register_advocate(db_client, db_txn_session, verified=False)
    matter = await book_matter(db_client, consumer, verified)
    await advance_matter(db_client, matter, consumer, verified, "PAID")
    await _chat(db_txn_session, question="I was arrested", risk="CRITICAL", at=T0)
    await _chat(db_txn_session, question="Sued for money", risk="HIGH", at=T0)
    await _chat(db_txn_session, question="Tenant rules?", risk="LOW", at=T0)

    after = await _overview(db_client, admin)

    def grew(section: str, key: str) -> int:
        return int(after[section][key]) - int(before[section][key])

    assert grew("users_by_role", "CONSUMER") == 1
    assert grew("users_by_role", "ADVOCATE") == 2
    assert grew("advocates_by_status", "VERIFIED") == 1
    assert grew("advocates_by_status", "PENDING") == 1
    assert grew("matters_by_status", "PAID") == 1
    assert after["advocates_pending"] - before["advocates_pending"] == 1
    assert after["reviews_pending"] - before["reviews_pending"] == 2  # LOW isn't reviewable
    assert after["payments"]["count"] - before["payments"]["count"] == 1
    assert float(after["payments"]["gross"]) - float(before["payments"]["gross"]) == 1200.0
    assert float(after["payments"]["refunded"]) == float(before["payments"]["refunded"])


# --- matters ----------------------------------------------------------------------------------


async def test_matters_list_shows_who_and_filters_by_status(
    db_client: AsyncClient, db_txn_session: Any
) -> None:
    admin = await make_admin(db_txn_session)
    consumer = await register_consumer(db_client, display_name="Asha Verma")
    advocate = await register_advocate(db_client, db_txn_session)
    paid = await advance_matter(
        db_client,
        await book_matter(db_client, consumer, advocate, title="Paid one"),
        consumer,
        advocate,
        "PAID",
    )
    requested = await book_matter(db_client, consumer, advocate, title="Still requested")

    resp = await db_client.get(
        f"{ADMIN}/matters", params={"status": "PAID", "limit": 100}, headers=admin.headers
    )

    assert resp.status_code == 200
    by_id = {m["id"]: m for m in resp.json()["items"]}
    assert paid["id"] in by_id
    assert requested["id"] not in by_id
    row = by_id[paid["id"]]
    assert row["title"] == "Paid one"
    assert row["consumer_name"] == "Asha Verma"
    assert row["advocate_name"] == "Adv. Kavya Rao"
    assert row["quoted_fee"] == "1200.00"


# --- advocates --------------------------------------------------------------------------------


async def test_advocate_list_includes_identity_and_filters_by_status(
    db_client: AsyncClient, db_txn_session: Any
) -> None:
    admin = await make_admin(db_txn_session)
    pending = await register_advocate(db_client, db_txn_session, verified=False)
    verified = await register_advocate(db_client, db_txn_session)

    resp = await db_client.get(
        f"{ADMIN}/advocates", params={"status": "PENDING", "limit": 100}, headers=admin.headers
    )

    assert resp.status_code == 200
    by_id = {a["id"]: a for a in resp.json()["items"]}
    assert pending.profile_id in by_id
    assert verified.profile_id not in by_id
    row = by_id[pending.profile_id]
    assert row["display_name"] == "Adv. Kavya Rao"
    assert "@" in row["email"]  # who to verify - the public/own views leave this out
    assert row["verification_status"] == "PENDING"
    assert row["state_code"] == "KA"


# --- users ------------------------------------------------------------------------------------


async def test_user_search_matches_email_and_name_and_treats_wildcards_literally(
    db_client: AsyncClient, db_txn_session: Any
) -> None:
    admin = await make_admin(db_txn_session)
    target = await register_consumer(db_client, display_name="Zebulon Quixote")
    email = str((await db_client.get("/api/v1/users/me", headers=target.headers)).json()["email"])

    by_name = await db_client.get(f"{ADMIN}/users", params={"q": "zebulon"}, headers=admin.headers)
    by_email = await db_client.get(
        f"{ADMIN}/users", params={"q": email.split("@")[0]}, headers=admin.headers
    )
    wildcard = await db_client.get(f"{ADMIN}/users", params={"q": "%"}, headers=admin.headers)
    underscore = await db_client.get(f"{ADMIN}/users", params={"q": "_"}, headers=admin.headers)

    assert [u["id"] for u in by_name.json()["items"]] == [target.user_id]
    assert target.user_id in [u["id"] for u in by_email.json()["items"]]
    # "%" and "_" are LIKE wildcards; escaped, they only match a literal "%" / "_".
    assert target.user_id not in [u["id"] for u in wildcard.json()["items"]]
    assert wildcard.json()["total"] == 0
    assert all("_" in (u["email"] + (u["display_name"] or "")) for u in underscore.json()["items"])


async def test_an_admin_cannot_suspend_themselves(
    db_client: AsyncClient, db_txn_session: Any
) -> None:
    admin = await make_admin(db_txn_session)

    resp = await db_client.patch(
        f"{ADMIN}/users/{admin.user_id}", json={"is_active": False}, headers=admin.headers
    )

    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "cannot_suspend_self"
    assert (await db_client.get(f"{ADMIN}/overview", headers=admin.headers)).status_code == 200


async def test_suspending_someone_locks_them_out_and_reactivating_lets_them_back(
    db_client: AsyncClient, db_txn_session: Any
) -> None:
    admin = await make_admin(db_txn_session)
    consumer = await register_consumer(db_client)
    url = f"{ADMIN}/users/{consumer.user_id}"

    suspended = await db_client.patch(url, json={"is_active": False}, headers=admin.headers)
    assert suspended.status_code == 200
    assert suspended.json()["is_active"] is False
    assert (await db_client.get("/api/v1/users/me", headers=consumer.headers)).status_code == 401

    restored = await db_client.patch(url, json={"is_active": True}, headers=admin.headers)
    assert restored.status_code == 200
    assert (await db_client.get("/api/v1/users/me", headers=consumer.headers)).status_code == 200


# --- high-risk query review -------------------------------------------------------------------


async def test_review_queue_lists_worst_first_and_only_high_risk_unreviewed(
    db_client: AsyncClient, db_txn_session: Any
) -> None:
    admin = await make_admin(db_txn_session)
    high_old = await _chat(db_txn_session, question="Served with a summons", risk="HIGH", at=T0)
    critical = await _chat(
        db_txn_session,
        question="Police want to arrest me tonight",
        risk="CRITICAL",
        at=T0 + timedelta(hours=1),  # newer, but worse
        sources=[{"document_title": "BNSS"}, {"document_title": "CrPC"}],
    )
    medium = await _chat(db_txn_session, question="Notice period?", risk="MEDIUM", at=T0)
    done = await _chat(db_txn_session, question="Old one", risk="HIGH", at=T0, reviewed=True)

    resp = await db_client.get(f"{ADMIN}/reviews", params={"limit": 100}, headers=admin.headers)

    assert resp.status_code == 200
    ids = [i["id"] for i in resp.json()["items"]]
    ours = [i for i in ids if i in {str(high_old.id), str(critical.id)}]
    assert ours == [str(critical.id), str(high_old.id)]  # CRITICAL before HIGH
    assert str(medium.id) not in ids
    assert str(done.id) not in ids

    item = next(i for i in resp.json()["items"] if i["id"] == str(critical.id))
    assert item["question"] == "Police want to arrest me tonight"
    assert item["answer"] == "Here is some general information."
    assert item["answer_source_count"] == 2
    assert item["risk_level"] == "CRITICAL"
    assert item["legal_category"] == "CRIMINAL_LAW"
    assert item["reviewed_at"] is None


async def test_review_items_never_reveal_who_asked(
    db_client: AsyncClient, db_txn_session: Any
) -> None:
    admin = await make_admin(db_txn_session)
    consumer = await register_consumer(db_client)
    mine = await _chat(
        db_txn_session,
        question="Registered user question",
        risk="HIGH",
        at=T0,
        owner=consumer.user_id,
    )
    anon = await _chat(db_txn_session, question="Anonymous question", risk="HIGH", at=T0)

    resp = await db_client.get(f"{ADMIN}/reviews", params={"limit": 100}, headers=admin.headers)

    by_id = {i["id"]: i for i in resp.json()["items"]}
    assert by_id[str(mine.id)]["registered"] is True
    assert by_id[str(anon.id)]["registered"] is False
    for item in by_id.values():
        assert not {"user_id", "email", "display_name", "owner_id"} & set(item)
    assert consumer.user_id not in resp.text


async def test_review_filters(db_client: AsyncClient, db_txn_session: Any) -> None:
    admin = await make_admin(db_txn_session)
    high = await _chat(db_txn_session, question="High one", risk="HIGH", at=T0)
    critical = await _chat(db_txn_session, question="Critical one", risk="CRITICAL", at=T0)
    done = await _chat(db_txn_session, question="Done one", risk="CRITICAL", at=T0, reviewed=True)

    def ids(resp: Any) -> set[str]:
        return {i["id"] for i in resp.json()["items"]}

    only_high = await db_client.get(
        f"{ADMIN}/reviews", params={"risk_level": "HIGH", "limit": 100}, headers=admin.headers
    )
    reviewed = await db_client.get(
        f"{ADMIN}/reviews", params={"status": "reviewed", "limit": 100}, headers=admin.headers
    )
    everything = await db_client.get(
        f"{ADMIN}/reviews", params={"status": "all", "limit": 100}, headers=admin.headers
    )

    assert str(high.id) in ids(only_high)
    assert str(critical.id) not in ids(only_high)
    assert str(done.id) in ids(reviewed)
    assert str(high.id) not in ids(reviewed)
    assert {str(high.id), str(critical.id), str(done.id)} <= ids(everything)
    bad = await db_client.get(
        f"{ADMIN}/reviews", params={"risk_level": "LOW"}, headers=admin.headers
    )
    assert bad.status_code == 422


async def test_marking_a_query_reviewed_removes_it_from_the_queue(
    db_client: AsyncClient, db_txn_session: Any
) -> None:
    admin = await make_admin(db_txn_session)
    other_admin = await make_admin(db_txn_session, UserRole.LEGAL_ADMIN)
    asked = await _chat(db_txn_session, question="Served with a summons", risk="HIGH", at=T0)
    url = f"{ADMIN}/reviews/{asked.id}/review"

    first = await db_client.post(
        url, json={"note": "Referred to an advocate"}, headers=admin.headers
    )

    assert first.status_code == 200, first.text
    assert first.json()["reviewed_at"] is not None
    assert first.json()["review_note"] == "Referred to an advocate"
    queue = await db_client.get(f"{ADMIN}/reviews", params={"limit": 100}, headers=admin.headers)
    assert str(asked.id) not in {i["id"] for i in queue.json()["items"]}

    # A second reviewer can amend the note, but the original reviewer and time stand.
    second = await db_client.post(
        url, json={"note": "Advocate confirmed"}, headers=other_admin.headers
    )
    assert second.status_code == 200
    assert second.json()["review_note"] == "Advocate confirmed"
    assert second.json()["reviewed_at"] == first.json()["reviewed_at"]
    row = await db_txn_session.scalar(select(ChatMessage).where(ChatMessage.id == asked.id))
    await db_txn_session.refresh(row)
    assert str(row.reviewed_by_id) == admin.user_id


async def test_only_high_risk_user_messages_can_be_reviewed(
    db_client: AsyncClient, db_txn_session: Any
) -> None:
    admin = await make_admin(db_txn_session)
    low = await _chat(db_txn_session, question="Low one", risk="LOW", at=T0)
    unclassified = await _chat(db_txn_session, question="Unclassified", risk=None, at=T0)
    high = await _chat(db_txn_session, question="High one", risk="HIGH", at=T0)
    reply = await db_txn_session.scalar(
        select(ChatMessage).where(
            ChatMessage.conversation_id == high.conversation_id,
            ChatMessage.role == MessageRole.ASSISTANT,
        )
    )

    for target in (low.id, unclassified.id, reply.id, uuid.uuid4()):
        resp = await db_client.post(
            f"{ADMIN}/reviews/{target}/review", json={}, headers=admin.headers
        )
        assert resp.status_code == 404, target


async def test_reviewing_requires_an_admin(db_client: AsyncClient, db_txn_session: Any) -> None:
    consumer = await register_consumer(db_client)
    asked = await _chat(db_txn_session, question="High one", risk="HIGH", at=T0)

    resp = await db_client.post(
        f"{ADMIN}/reviews/{asked.id}/review", json={}, headers=consumer.headers
    )

    assert resp.status_code == 403
    await db_txn_session.refresh(asked)
    assert asked.reviewed_at is None
