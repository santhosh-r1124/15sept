"""Integration tests for /api/v1/matters (booking lifecycle, messaging, access control).
Needs Postgres - see conftest.db_client."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from httpx import AsyncClient

from app.models.user import UserRole
from tests.helpers import Account, make_admin, register_advocate, register_consumer

MATTERS = "/api/v1/matters"


def _booking(advocate: Account, **overrides: Any) -> dict[str, Any]:
    return {
        "advocate_id": advocate.profile_id,
        "service_type": "CONSULTATION",
        "consultation_minutes": 30,
        "title": "Rental agreement review",
        "requirement": "Review my existing rental agreement before I sign.",
        "preferred_language": "en",
        **overrides,
    }


async def _book(client: AsyncClient, consumer: Account, advocate: Account, **kw: Any) -> Any:
    resp = await client.post(MATTERS, json=_booking(advocate, **kw), headers=consumer.headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _act(
    client: AsyncClient, matter_id: str, action: str, who: Account, body: dict | None = None
) -> Any:
    return await client.post(
        f"{MATTERS}/{matter_id}/{action}", json=body or {}, headers=who.headers
    )


def _future() -> str:
    return (datetime.now(UTC) + timedelta(days=2)).isoformat()


# --- booking ---------------------------------------------------------------------------


async def test_booking_prefills_a_prorated_quote_for_consultations(
    db_client: AsyncClient, db_txn_session: Any
) -> None:
    consumer = await register_consumer(db_client)
    advocate = await register_advocate(db_client, db_txn_session, consultation_fee="1200.00")

    matter = await _book(db_client, consumer, advocate, consultation_minutes=30)

    assert matter["status"] == "REQUESTED"
    assert matter["quoted_fee"] == "600.00"
    assert matter["advocate"]["display_name"] == "Adv. Kavya Rao"
    assert matter["consumer"]["verified"] is False
    assert "email" not in matter["consumer"]


async def test_cannot_book_an_unverified_or_unknown_advocate(
    db_client: AsyncClient, db_txn_session: Any
) -> None:
    consumer = await register_consumer(db_client)
    pending = await register_advocate(db_client, db_txn_session, verified=False)

    resp = await db_client.post(MATTERS, json=_booking(pending), headers=consumer.headers)
    assert resp.status_code == 404

    unknown = Account(headers={}, user_id="x", profile_id="00000000-0000-0000-0000-000000000000")
    resp = await db_client.post(MATTERS, json=_booking(unknown), headers=consumer.headers)
    assert resp.status_code == 404


async def test_booking_requires_login_and_a_non_advocate_account(
    db_client: AsyncClient, db_txn_session: Any
) -> None:
    advocate = await register_advocate(db_client, db_txn_session)
    other_advocate = await register_advocate(db_client, db_txn_session)

    anon = await db_client.post(MATTERS, json=_booking(advocate))
    assert anon.status_code == 401
    as_advocate = await db_client.post(
        MATTERS, json=_booking(advocate), headers=other_advocate.headers
    )
    assert as_advocate.status_code == 403


async def test_booking_validates_minutes_against_service_type(
    db_client: AsyncClient, db_txn_session: Any
) -> None:
    consumer = await register_consumer(db_client)
    advocate = await register_advocate(db_client, db_txn_session)

    bad_minutes = await db_client.post(
        MATTERS, json=_booking(advocate, consultation_minutes=45), headers=consumer.headers
    )
    assert bad_minutes.status_code == 422
    minutes_on_document = await db_client.post(
        MATTERS,
        json=_booking(advocate, service_type="DOCUMENT_REVIEW", consultation_minutes=30),
        headers=consumer.headers,
    )
    assert minutes_on_document.status_code == 422


# --- full lifecycles -------------------------------------------------------------------


async def test_consultation_lifecycle_end_to_end(
    db_client: AsyncClient, db_txn_session: Any
) -> None:
    consumer = await register_consumer(db_client)
    advocate = await register_advocate(db_client, db_txn_session)
    matter = await _book(db_client, consumer, advocate)
    mid = matter["id"]

    accepted = await _act(db_client, mid, "accept", advocate, {"note": "Happy to help."})
    assert accepted.status_code == 200
    assert accepted.json()["status"] == "ACCEPTED"
    assert accepted.json()["decision_note"] == "Happy to help."

    paid = await _act(db_client, mid, "pay", consumer)
    assert paid.status_code == 200
    assert paid.json()["status"] == "PAID"
    assert paid.json()["paid_at"] is not None

    scheduled = await _act(db_client, mid, "schedule", advocate, {"scheduled_at": _future()})
    assert scheduled.status_code == 200
    assert scheduled.json()["status"] == "SCHEDULED"

    closed = await _act(db_client, mid, "close", advocate)
    assert closed.status_code == 200
    assert closed.json()["status"] == "CLOSED"
    assert closed.json()["closed_at"] is not None


async def test_document_service_lifecycle_skips_scheduling(
    db_client: AsyncClient, db_txn_session: Any
) -> None:
    consumer = await register_consumer(db_client)
    advocate = await register_advocate(db_client, db_txn_session)
    matter = await _book(
        db_client, consumer, advocate, service_type="AGREEMENT_REVIEW", consultation_minutes=None
    )
    assert matter["quoted_fee"] is None
    mid = matter["id"]

    no_quote = await _act(db_client, mid, "accept", advocate)
    assert no_quote.status_code == 422  # a document service must be quoted by the advocate

    accepted = await _act(db_client, mid, "accept", advocate, {"quoted_fee": "2500.00"})
    assert accepted.json()["quoted_fee"] == "2500.00"
    assert (await _act(db_client, mid, "pay", consumer)).json()["status"] == "PAID"

    no_schedule = await _act(db_client, mid, "schedule", advocate, {"scheduled_at": _future()})
    assert no_schedule.status_code == 409
    assert (await _act(db_client, mid, "close", advocate)).json()["status"] == "CLOSED"


async def test_reject_and_cancel(db_client: AsyncClient, db_txn_session: Any) -> None:
    consumer = await register_consumer(db_client)
    advocate = await register_advocate(db_client, db_txn_session)

    rejected = await _book(db_client, consumer, advocate)
    no_note = await _act(db_client, rejected["id"], "reject", advocate)
    assert no_note.status_code == 422
    resp = await _act(db_client, rejected["id"], "reject", advocate, {"note": "Not my area."})
    assert resp.json()["status"] == "REJECTED"

    cancelled = await _book(db_client, consumer, advocate)
    resp = await _act(db_client, cancelled["id"], "cancel", consumer, {"note": "Changed my mind"})
    assert resp.json()["status"] == "CANCELLED"


# --- state machine enforcement over HTTP ------------------------------------------------


async def test_illegal_transitions_are_409(db_client: AsyncClient, db_txn_session: Any) -> None:
    consumer = await register_consumer(db_client)
    advocate = await register_advocate(db_client, db_txn_session)
    mid = (await _book(db_client, consumer, advocate))["id"]

    # Can't pay before the advocate accepts, or accept your own request.
    assert (await _act(db_client, mid, "pay", consumer)).status_code == 409
    assert (await _act(db_client, mid, "accept", consumer)).status_code == 409

    await _act(db_client, mid, "accept", advocate)
    await _act(db_client, mid, "pay", consumer)

    # Paid: can't pay twice, can't close a consultation before it's scheduled, and the
    # advocate (not the client) is the one who closes.
    assert (await _act(db_client, mid, "pay", consumer)).status_code == 409
    assert (await _act(db_client, mid, "close", advocate)).status_code == 409
    assert (await _act(db_client, mid, "close", consumer)).status_code == 409
    resp = await _act(db_client, mid, "pay", consumer)
    assert resp.json()["error"]["code"] == "invalid_transition"


async def test_schedule_must_be_timezone_aware_and_in_the_future(
    db_client: AsyncClient, db_txn_session: Any
) -> None:
    consumer = await register_consumer(db_client)
    advocate = await register_advocate(db_client, db_txn_session)
    mid = (await _book(db_client, consumer, advocate))["id"]
    await _act(db_client, mid, "accept", advocate)
    await _act(db_client, mid, "pay", consumer)

    naive = (datetime.now() + timedelta(days=1)).replace(tzinfo=None).isoformat()
    assert (
        await _act(db_client, mid, "schedule", advocate, {"scheduled_at": naive})
    ).status_code == 422
    past = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    assert (
        await _act(db_client, mid, "schedule", advocate, {"scheduled_at": past})
    ).status_code == 422

    first = await _act(db_client, mid, "schedule", advocate, {"scheduled_at": _future()})
    later = (datetime.now(UTC) + timedelta(days=5)).isoformat()
    again = await _act(db_client, mid, "schedule", advocate, {"scheduled_at": later})
    assert first.status_code == again.status_code == 200  # rescheduling is allowed


# --- access control ----------------------------------------------------------------------


async def test_outsiders_get_404_and_admins_can_read(
    db_client: AsyncClient, db_txn_session: Any
) -> None:
    consumer = await register_consumer(db_client)
    stranger = await register_consumer(db_client)
    advocate = await register_advocate(db_client, db_txn_session)
    other_advocate = await register_advocate(db_client, db_txn_session)
    admin = await make_admin(db_txn_session, UserRole.LEGAL_ADMIN)
    mid = (await _book(db_client, consumer, advocate))["id"]

    for outsider in (stranger, other_advocate):
        detail = await db_client.get(f"{MATTERS}/{mid}", headers=outsider.headers)
        thread = await db_client.get(f"{MATTERS}/{mid}/messages", headers=outsider.headers)
        assert detail.status_code == 404
        assert thread.status_code == 404
        assert (await _act(db_client, mid, "accept", outsider)).status_code == 404

    assert (await db_client.get(f"{MATTERS}/{mid}", headers=admin.headers)).status_code == 200
    # Admins can read but not act.
    assert (await _act(db_client, mid, "accept", admin)).status_code == 404
    assert (await db_client.get(MATTERS)).status_code == 401


async def test_listing_is_scoped_to_the_caller(db_client: AsyncClient, db_txn_session: Any) -> None:
    consumer = await register_consumer(db_client)
    other_consumer = await register_consumer(db_client)
    advocate = await register_advocate(db_client, db_txn_session)
    other_advocate = await register_advocate(db_client, db_txn_session)
    mine = await _book(db_client, consumer, advocate)
    await _book(db_client, other_consumer, other_advocate)

    as_consumer = (await db_client.get(MATTERS, headers=consumer.headers)).json()
    assert [m["id"] for m in as_consumer["items"]] == [mine["id"]]
    as_advocate = (await db_client.get(MATTERS, headers=advocate.headers)).json()
    assert [m["id"] for m in as_advocate["items"]] == [mine["id"]]
    assert as_advocate["total"] == 1

    await _act(db_client, mine["id"], "accept", advocate)
    filtered = (
        await db_client.get(MATTERS, params={"status": "REQUESTED"}, headers=advocate.headers)
    ).json()
    assert filtered["total"] == 0


# --- messages ----------------------------------------------------------------------------


async def test_message_thread_between_participants(
    db_client: AsyncClient, db_txn_session: Any
) -> None:
    consumer = await register_consumer(db_client)
    advocate = await register_advocate(db_client, db_txn_session)
    mid = (await _book(db_client, consumer, advocate))["id"]
    url = f"{MATTERS}/{mid}/messages"

    first = await db_client.post(url, json={"body": "Any questions?"}, headers=advocate.headers)
    second = await db_client.post(url, json={"body": "About clause 4."}, headers=consumer.headers)
    assert first.status_code == second.status_code == 201
    assert first.json()["sender_role"] == "ADVOCATE"
    assert second.json()["sender_role"] == "CONSUMER"

    thread = (await db_client.get(url, headers=consumer.headers)).json()
    assert [m["body"] for m in thread] == ["Any questions?", "About clause 4."]

    empty = await db_client.post(url, json={"body": ""}, headers=consumer.headers)
    assert empty.status_code == 422


async def test_thread_becomes_read_only_when_the_matter_ends(
    db_client: AsyncClient, db_txn_session: Any
) -> None:
    consumer = await register_consumer(db_client)
    advocate = await register_advocate(db_client, db_txn_session)
    mid = (await _book(db_client, consumer, advocate))["id"]
    await _act(db_client, mid, "cancel", consumer)
    url = f"{MATTERS}/{mid}/messages"

    blocked = await db_client.post(url, json={"body": "still there?"}, headers=consumer.headers)
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "matter_closed"
    assert (await db_client.get(url, headers=consumer.headers)).status_code == 200
