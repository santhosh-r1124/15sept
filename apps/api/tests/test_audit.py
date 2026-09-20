"""Integration tests for the audit trail (Phase 13). Needs Postgres."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, select, text, update
from sqlalchemy.exc import DBAPIError

from app.core.errors import ServiceUnavailableError
from app.models.audit import AuditLog
from app.models.chat import ChatMessage, Conversation, MessageRole
from app.models.legal_document import DocumentType, LegalDocument
from app.models.user import UserRole
from app.services.payments import MockPaymentProvider
from tests.helpers import (
    Account,
    advance_matter,
    book_matter,
    make_admin,
    register_advocate,
    register_consumer,
)

ADMIN = "/api/v1/admin"


async def _entries(session: Any, action: str | None = None) -> list[AuditLog]:
    stmt = select(AuditLog).order_by(AuditLog.occurred_at, AuditLog.id)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    return list((await session.execute(stmt)).scalars().all())


# --- what gets recorded ------------------------------------------------------------------------


async def test_suspending_and_reactivating_a_user_are_recorded_with_who_and_from_where(
    db_client: AsyncClient, db_txn_session: Any
) -> None:
    admin = await make_admin(db_txn_session)
    consumer = await register_consumer(db_client)
    url = f"{ADMIN}/users/{consumer.user_id}"

    await db_client.patch(url, json={"is_active": False}, headers=admin.headers)
    await db_client.patch(url, json={"is_active": True}, headers=admin.headers)

    suspend, reactivate = (
        (await _entries(db_txn_session, "user.suspend"))[0],
        (await _entries(db_txn_session, "user.reactivate"))[0],
    )
    assert str(suspend.actor_id) == admin.user_id
    assert suspend.actor_role == "ADMIN"
    assert (suspend.target_type, suspend.target_id) == ("user", consumer.user_id)
    assert suspend.ip  # the caller's address
    assert suspend.request_id  # ties the entry to the request log line
    assert reactivate.occurred_at >= suspend.occurred_at


async def test_advocate_verification_decisions_are_recorded(
    db_client: AsyncClient, db_txn_session: Any
) -> None:
    admin = await make_admin(db_txn_session, UserRole.LEGAL_ADMIN)
    approved = await register_advocate(db_client, db_txn_session, verified=False)
    declined = await register_advocate(db_client, db_txn_session, verified=False)

    await db_client.post(
        f"{ADMIN}/advocates/{approved.profile_id}/verify", json={}, headers=admin.headers
    )
    await db_client.post(
        f"{ADMIN}/advocates/{declined.profile_id}/reject",
        json={"note": "No enrolment number"},
        headers=admin.headers,
    )

    (verify,) = await _entries(db_txn_session, "advocate.verify")
    (reject,) = await _entries(db_txn_session, "advocate.reject")
    assert (verify.target_id, verify.actor_role) == (approved.profile_id, "LEGAL_ADMIN")
    assert reject.target_id == declined.profile_id
    # The reason given to the advocate is not copied into the log.
    assert "No enrolment number" not in str(reject.detail)


async def test_refunds_are_recorded_with_the_amount(
    db_client: AsyncClient, db_txn_session: Any
) -> None:
    admin = await make_admin(db_txn_session)
    consumer = await register_consumer(db_client)
    advocate = await register_advocate(db_client, db_txn_session)
    matter = await advance_matter(
        db_client, await book_matter(db_client, consumer, advocate), consumer, advocate, "CLOSED"
    )
    payment = (
        await db_client.get(f"/api/v1/payments/matters/{matter['id']}", headers=consumer.headers)
    ).json()["payment"]

    resp = await db_client.post(
        f"{ADMIN}/payments/{payment['id']}/refund",
        json={"amount": "100.00", "reason": "Goodwill"},
        headers=admin.headers,
    )
    assert resp.status_code == 200

    (entry,) = await _entries(db_txn_session, "refund.issue")
    assert entry.target_id == payment["id"]
    assert entry.detail == {"amount": "100.00", "matter_id": matter["id"]}  # Decimal -> string
    assert "Goodwill" not in str(entry.detail)


async def test_a_refund_that_fails_leaves_no_audit_entry(
    db_client: AsyncClient, db_txn_session: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The log is written in the action's own transaction: it never claims what didn't happen."""
    admin = await make_admin(db_txn_session)
    consumer = await register_consumer(db_client)
    advocate = await register_advocate(db_client, db_txn_session)
    matter = await advance_matter(
        db_client, await book_matter(db_client, consumer, advocate), consumer, advocate, "CLOSED"
    )
    payment = (
        await db_client.get(f"/api/v1/payments/matters/{matter['id']}", headers=consumer.headers)
    ).json()["payment"]

    async def broken_refund(self: object, **_kw: object) -> None:
        raise ServiceUnavailableError("gateway down", code="payments_error")

    monkeypatch.setattr(MockPaymentProvider, "refund", broken_refund)
    resp = await db_client.post(
        f"{ADMIN}/payments/{payment['id']}/refund",
        json={"reason": "Dispute"},
        headers=admin.headers,
    )

    assert resp.status_code == 503
    assert await _entries(db_txn_session, "refund.issue") == []


async def test_reading_private_chat_content_is_recorded_without_the_content(
    db_client: AsyncClient, db_txn_session: Any
) -> None:
    admin = await make_admin(db_txn_session)
    conversation = Conversation(title="q")
    db_txn_session.add(conversation)
    await db_txn_session.flush()
    db_txn_session.add(
        ChatMessage(
            conversation_id=conversation.id,
            role=MessageRole.USER,
            content="My husband hits me and I want to leave",
            risk_level="CRITICAL",
            created_at=datetime(2026, 1, 1),
        )
    )
    await db_txn_session.commit()

    resp = await db_client.get(f"{ADMIN}/reviews", params={"limit": 100}, headers=admin.headers)
    assert resp.status_code == 200
    message_id = next(i["id"] for i in resp.json()["items"] if "husband" in i["question"])
    await db_client.post(f"{ADMIN}/reviews/{message_id}/review", json={}, headers=admin.headers)

    listed = (await _entries(db_txn_session, "review.list"))[0]
    marked = (await _entries(db_txn_session, "review.mark"))[0]
    assert listed.detail is not None
    assert listed.detail["status"] == "pending"
    assert listed.detail["returned"] >= 1
    assert marked.target_id == message_id
    assert "husband" not in str(listed.detail) + str(marked.detail)


async def test_removing_a_legal_source_is_recorded_with_its_title(
    db_client: AsyncClient, db_txn_session: Any
) -> None:
    admin = await make_admin(db_txn_session)
    document = LegalDocument(
        title="An obsolete rule",
        source_url="https://example.test/rule",
        document_type=DocumentType.RULES,
        checksum="x",
    )
    db_txn_session.add(document)
    await db_txn_session.commit()

    resp = await db_client.delete(f"{ADMIN}/legal-sources/{document.id}", headers=admin.headers)

    assert resp.status_code == 204
    (entry,) = await _entries(db_txn_session, "source.delete")
    assert entry.target_id == str(document.id)
    assert entry.detail == {"title": "An obsolete rule"}


# --- it cannot be rewritten --------------------------------------------------------------------


async def test_the_database_refuses_to_change_or_delete_audit_entries(
    db_client: AsyncClient, db_txn_session: Any
) -> None:
    admin = await make_admin(db_txn_session)
    consumer = await register_consumer(db_client)
    await db_client.patch(
        f"{ADMIN}/users/{consumer.user_id}", json={"is_active": False}, headers=admin.headers
    )
    (entry,) = await _entries(db_txn_session, "user.suspend")

    for statement in (
        update(AuditLog).where(AuditLog.id == entry.id).values(action="user.nothing"),
        delete(AuditLog).where(AuditLog.id == entry.id),
        text("TRUNCATE audit_logs"),
    ):
        with pytest.raises(DBAPIError, match="append-only"):
            async with db_txn_session.begin_nested():
                await db_txn_session.execute(statement)

    assert len(await _entries(db_txn_session, "user.suspend")) == 1  # untouched


# --- reading the trail -------------------------------------------------------------------------


async def _generate_history(
    db_client: AsyncClient, db_txn_session: Any
) -> tuple[Account, Account, Account]:
    admin = await make_admin(db_txn_session)
    other_admin = await make_admin(db_txn_session)
    consumer = await register_consumer(db_client)
    url = f"{ADMIN}/users/{consumer.user_id}"
    await db_client.patch(url, json={"is_active": False}, headers=admin.headers)
    await db_client.patch(url, json={"is_active": True}, headers=other_admin.headers)
    return admin, other_admin, consumer


async def test_only_admins_can_read_the_audit_trail(
    db_client: AsyncClient, db_txn_session: Any
) -> None:
    legal_admin = await make_admin(db_txn_session, UserRole.LEGAL_ADMIN)
    consumer = await register_consumer(db_client)
    url = f"{ADMIN}/audit-logs"

    assert (await db_client.get(url)).status_code == 401
    assert (await db_client.get(url, headers=consumer.headers)).status_code == 403
    # Legal ops can act, but can't read the record of their own actions.
    assert (await db_client.get(url, headers=legal_admin.headers)).status_code == 403


async def test_the_trail_lists_newest_first_and_filters(
    db_client: AsyncClient, db_txn_session: Any
) -> None:
    admin, other_admin, consumer = await _generate_history(db_client, db_txn_session)
    reader = await make_admin(db_txn_session)
    url = f"{ADMIN}/audit-logs"

    everything = await db_client.get(url, params={"limit": 100}, headers=reader.headers)
    by_action = await db_client.get(
        url, params={"action": "user.", "limit": 100}, headers=reader.headers
    )
    by_actor = await db_client.get(url, params={"actor_id": admin.user_id}, headers=reader.headers)
    by_target = await db_client.get(
        url, params={"target_id": consumer.user_id}, headers=reader.headers
    )
    future = await db_client.get(
        url,
        params={"since": (datetime.now(UTC) + timedelta(hours=1)).isoformat()},
        headers=reader.headers,
    )

    assert everything.status_code == 200
    actions = [e["action"] for e in everything.json()["items"]]
    assert actions.index("user.reactivate") < actions.index("user.suspend")  # newest first
    assert {e["action"] for e in by_action.json()["items"]} >= {"user.suspend", "user.reactivate"}
    assert [e["action"] for e in by_actor.json()["items"]] == ["user.suspend"]
    assert {e["actor_id"] for e in by_target.json()["items"]} == {
        admin.user_id,
        other_admin.user_id,
    }
    assert future.json()["total"] == 0


async def test_an_action_filter_treats_wildcards_literally_and_paginates(
    db_client: AsyncClient, db_txn_session: Any
) -> None:
    await _generate_history(db_client, db_txn_session)
    reader = await make_admin(db_txn_session)
    url = f"{ADMIN}/audit-logs"

    wildcard = await db_client.get(url, params={"action": "%"}, headers=reader.headers)
    page = await db_client.get(url, params={"limit": 1, "offset": 1}, headers=reader.headers)

    assert wildcard.json()["total"] == 0  # "%" means a literal percent sign, not "everything"
    assert len(page.json()["items"]) == 1
    assert page.json()["total"] >= 2


async def test_entries_carry_no_secrets_or_content(
    db_client: AsyncClient, db_txn_session: Any
) -> None:
    await _generate_history(db_client, db_txn_session)
    reader = await make_admin(db_txn_session)

    body = (await db_client.get(f"{ADMIN}/audit-logs", headers=reader.headers)).text

    assert "password" not in body.lower()
    assert "@example.com" not in body  # entries reference ids, not email addresses
