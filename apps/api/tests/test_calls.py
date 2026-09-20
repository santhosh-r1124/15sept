"""Integration tests for consultation calls: the REST endpoints and the database-backed
gatekeeper behind the WebSocket. Needs Postgres. The socket relay itself is in test_call_ws.py."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.config import get_settings
from app.models.call import MatterCall
from app.models.matter import Matter
from app.models.notification import Notification
from app.models.user import User, UserRole
from app.services.calls.gatekeeper import CallDeniedError, CallGatekeeper, CallGrant
from app.services.calls.tickets import issue_ticket, reset_used_tickets
from app.services.email import set_email_sender
from app.services.matters.lifecycle import Actor
from app.services.notifications import reset_delivery_pause
from tests.helpers import (
    Account,
    advance_matter,
    book_matter,
    make_admin,
    register_advocate,
    register_consumer,
)

MATTERS = "/api/v1/matters"


@pytest.fixture(autouse=True)
def _clean_state() -> Iterator[None]:
    reset_used_tickets()
    yield
    reset_used_tickets()


class Outbox:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str, str]] = []

    async def send(self, *, to: str, subject: str, body: str) -> None:
        self.sent.append((to, subject, body))


@pytest.fixture
def outbox() -> Iterator[Outbox]:
    box = Outbox()
    set_email_sender(box)
    reset_delivery_pause()
    yield box
    set_email_sender(None)
    reset_delivery_pause()


async def _consultation(
    client: AsyncClient, session: Any, *, stage: str = "PAID", **booking: Any
) -> tuple[Account, Account, dict[str, Any]]:
    consumer = await register_consumer(client)
    advocate = await register_advocate(client, session)
    matter = await book_matter(client, consumer, advocate, **booking)
    if stage != "REQUESTED":
        matter = await advance_matter(client, matter, consumer, advocate, stage)
    return consumer, advocate, matter


async def _session(client: AsyncClient, who: Account, matter_id: str) -> Any:
    return await client.post(f"{MATTERS}/{matter_id}/call/session", headers=who.headers)


def _gatekeeper(session: Any, **kwargs: Any) -> CallGatekeeper:
    @asynccontextmanager
    async def shared() -> AsyncIterator[Any]:
        yield session  # the test's transaction-bound session; never closed here

    return CallGatekeeper(shared, get_settings(), **kwargs)


async def _grant(
    client: AsyncClient, session: Any, who: Account, matter_id: str, **gatekeeper_kwargs: Any
) -> tuple[CallGatekeeper, CallGrant]:
    ticket = (await _session(client, who, matter_id)).json()["ticket"]
    gatekeeper = _gatekeeper(session, **gatekeeper_kwargs)
    return gatekeeper, await gatekeeper.authorize(ticket, uuid.UUID(matter_id))


# --- getting a ticket -------------------------------------------------------------------------


async def test_either_side_of_a_paid_consultation_can_get_a_ticket_and_ice_servers(
    db_client: AsyncClient, db_txn_session: Any
) -> None:
    consumer, advocate, matter = await _consultation(db_client, db_txn_session)

    as_client = await _session(db_client, consumer, matter["id"])
    as_advocate = await _session(db_client, advocate, matter["id"])

    assert as_client.status_code == 200, as_client.text
    body = as_client.json()
    assert body["role"] == "CONSUMER"
    assert as_advocate.json()["role"] == "ADVOCATE"
    assert body["expires_in"] == 60
    assert body["ws_path"] == f"/api/v1/matters/{matter['id']}/call/ws"
    assert body["ice_servers"] == [{"urls": ["stun:stun.l.google.com:19302"]}]
    assert body["ice_transport_policy"] == "all"
    assert body["closes_at"] is None  # not scheduled: an ad hoc call
    assert body["ticket"] != as_advocate.json()["ticket"]


async def test_outsiders_and_anonymous_callers_get_nothing(
    db_client: AsyncClient, db_txn_session: Any
) -> None:
    _consumer, _advocate, matter = await _consultation(db_client, db_txn_session)
    stranger = await register_consumer(db_client)
    other_advocate = await register_advocate(db_client, db_txn_session)

    assert (await _session(db_client, stranger, matter["id"])).status_code == 404
    assert (await _session(db_client, other_advocate, matter["id"])).status_code == 404
    anonymous = await db_client.post(f"{MATTERS}/{matter['id']}/call/session")
    assert anonymous.status_code == 401
    unknown = await _session(db_client, stranger, str(uuid.uuid4()))
    assert unknown.status_code == 404


@pytest.mark.parametrize("stage", ["REQUESTED", "ACCEPTED"])
async def test_an_unpaid_matter_has_no_call_room(
    db_client: AsyncClient, db_txn_session: Any, stage: str
) -> None:
    consumer, _advocate, matter = await _consultation(db_client, db_txn_session, stage=stage)

    resp = await _session(db_client, consumer, matter["id"])

    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "unpaid"
    assert "paid" in resp.json()["error"]["message"]


async def test_document_services_have_no_call_room(
    db_client: AsyncClient, db_txn_session: Any
) -> None:
    consumer = await register_consumer(db_client)
    advocate = await register_advocate(db_client, db_txn_session)
    matter = await book_matter(
        db_client, consumer, advocate, service_type="DOCUMENT_DRAFT", consultation_minutes=None
    )
    matter = await advance_matter(db_client, matter, consumer, advocate, "PAID", quote="900.00")

    resp = await _session(db_client, consumer, matter["id"])

    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "not_a_consultation"


async def test_a_consultation_booked_for_later_is_not_open_yet(
    db_client: AsyncClient, db_txn_session: Any
) -> None:
    consumer, _advocate, matter = await _consultation(db_client, db_txn_session, stage="SCHEDULED")

    resp = await _session(db_client, consumer, matter["id"])  # booked two days ahead

    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "too_early"
    assert "opens at" in resp.json()["error"]["message"]


async def test_a_consultation_starting_soon_is_open_until_its_window_closes(
    db_client: AsyncClient, db_txn_session: Any
) -> None:
    consumer, advocate, matter = await _consultation(db_client, db_txn_session, stage="PAID")
    starts = datetime.now(UTC) + timedelta(minutes=5)
    scheduled = await db_client.post(
        f"{MATTERS}/{matter['id']}/schedule",
        json={"scheduled_at": starts.isoformat()},
        headers=advocate.headers,
    )
    assert scheduled.status_code == 200

    resp = await _session(db_client, consumer, matter["id"])

    assert resp.status_code == 200, resp.text
    closes = datetime.fromisoformat(resp.json()["closes_at"])
    # A 60-minute booking plus the 30-minute grace period.
    assert abs(closes - (starts + timedelta(minutes=90))) < timedelta(seconds=1)


async def test_a_missed_window_is_refused_with_a_hint_to_reschedule(
    db_client: AsyncClient, db_txn_session: Any
) -> None:
    consumer, _advocate, matter = await _consultation(db_client, db_txn_session, stage="SCHEDULED")
    row = await db_txn_session.scalar(select(Matter).where(Matter.id == uuid.UUID(matter["id"])))
    row.scheduled_at = datetime.now(UTC) - timedelta(hours=5)
    await db_txn_session.commit()

    resp = await _session(db_client, consumer, matter["id"])

    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "window_passed"
    assert "reschedule" in resp.json()["error"]["message"]


async def test_a_closed_matter_has_no_call_room(
    db_client: AsyncClient, db_txn_session: Any
) -> None:
    consumer, _advocate, matter = await _consultation(db_client, db_txn_session, stage="CLOSED")

    resp = await _session(db_client, consumer, matter["id"])

    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "ended"


async def test_a_turn_server_is_offered_when_one_is_configured(
    db_client: AsyncClient, db_txn_session: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    consumer, _advocate, matter = await _consultation(db_client, db_txn_session)
    monkeypatch.setenv("WEBRTC_TURN_URLS", "turn:turn.example.com:3478")
    monkeypatch.setenv("WEBRTC_TURN_SECRET", "static-auth-secret")
    get_settings.cache_clear()

    body = (await _session(db_client, consumer, matter["id"])).json()

    turn = body["ice_servers"][1]
    assert turn["urls"] == ["turn:turn.example.com:3478"]
    assert turn["username"].endswith(f":{consumer.user_id}")
    assert "static-auth-secret" not in str(body)


async def test_relay_only_without_turn_is_reported_as_a_misconfiguration(
    db_client: AsyncClient, db_txn_session: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    consumer, _advocate, matter = await _consultation(db_client, db_txn_session)
    monkeypatch.setenv("WEBRTC_RELAY_ONLY", "true")
    get_settings.cache_clear()

    resp = await _session(db_client, consumer, matter["id"])

    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "calls_misconfigured"


# --- status -----------------------------------------------------------------------------------


async def test_status_shows_whether_the_room_is_open_and_who_is_in_it(
    db_client: AsyncClient, db_txn_session: Any
) -> None:
    consumer, advocate, matter = await _consultation(db_client, db_txn_session)

    before = (
        await db_client.get(f"{MATTERS}/{matter['id']}/call", headers=advocate.headers)
    ).json()

    assert before["access"] == {
        "allowed": True,
        "reason": None,
        "opens_at": None,
        "closes_at": None,
    }
    assert before["present"] == []
    assert before["calls"] == []

    # The client can read it too; a stranger can't.
    ok = await db_client.get(f"{MATTERS}/{matter['id']}/call", headers=consumer.headers)
    outsider = await register_consumer(db_client)
    forbidden = await db_client.get(f"{MATTERS}/{matter['id']}/call", headers=outsider.headers)
    assert ok.status_code == 200
    assert forbidden.status_code == 404


async def test_admins_can_read_the_status_but_cannot_join(
    db_client: AsyncClient, db_txn_session: Any
) -> None:
    _consumer, _advocate, matter = await _consultation(db_client, db_txn_session)
    admin = await make_admin(db_txn_session, UserRole.ADMIN)

    status = await db_client.get(f"{MATTERS}/{matter['id']}/call", headers=admin.headers)
    joined = await _session(db_client, admin, matter["id"])

    assert status.status_code == 200
    assert joined.status_code == 404  # admins may look, never join a private consultation


# --- the gatekeeper (what the WebSocket relies on) --------------------------------------------


async def test_a_valid_ticket_becomes_a_grant_with_a_deadline(
    db_client: AsyncClient, db_txn_session: Any
) -> None:
    consumer, _advocate, matter = await _consultation(db_client, db_txn_session)
    now = datetime.now(UTC)

    _gate, grant = await _grant(
        db_client, db_txn_session, consumer, matter["id"], clock=lambda: now
    )

    assert grant.actor is Actor.CONSUMER
    assert grant.user_id == uuid.UUID(consumer.user_id)
    assert grant.title == "Rental agreement review"
    assert grant.deadline == now + timedelta(minutes=180)  # ad hoc calls are capped


async def test_a_scheduled_call_ends_when_its_window_closes(
    db_client: AsyncClient, db_txn_session: Any
) -> None:
    _consumer, advocate, matter = await _consultation(db_client, db_txn_session)
    starts = datetime.now(UTC) + timedelta(minutes=2)
    await db_client.post(
        f"{MATTERS}/{matter['id']}/schedule",
        json={"scheduled_at": starts.isoformat()},
        headers=advocate.headers,
    )

    _gate, grant = await _grant(db_client, db_txn_session, advocate, matter["id"])

    assert grant.deadline == starts + timedelta(minutes=60 + 30)


async def test_a_ticket_cannot_be_reused(db_client: AsyncClient, db_txn_session: Any) -> None:
    consumer, _advocate, matter = await _consultation(db_client, db_txn_session)
    ticket = (await _session(db_client, consumer, matter["id"])).json()["ticket"]
    gate = _gatekeeper(db_txn_session)
    await gate.authorize(ticket, uuid.UUID(matter["id"]))

    with pytest.raises(CallDeniedError) as denied:
        await gate.authorize(ticket, uuid.UUID(matter["id"]))

    assert denied.value.code == "invalid_ticket"


async def test_a_ticket_for_one_matter_is_useless_for_another(
    db_client: AsyncClient, db_txn_session: Any
) -> None:
    consumer, advocate, matter = await _consultation(db_client, db_txn_session)
    other = await book_matter(db_client, consumer, advocate, title="Another matter")
    other = await advance_matter(db_client, other, consumer, advocate, "PAID")
    ticket = (await _session(db_client, consumer, matter["id"])).json()["ticket"]

    with pytest.raises(CallDeniedError) as denied:
        await _gatekeeper(db_txn_session).authorize(ticket, uuid.UUID(other["id"]))

    assert denied.value.code == "invalid_ticket"


async def test_the_matter_is_rechecked_at_connection_time(
    db_client: AsyncClient, db_txn_session: Any
) -> None:
    """A ticket only proves who asked a minute ago; the matter may have been cancelled since."""
    consumer, advocate, matter = await _consultation(db_client, db_txn_session)
    ticket = (await _session(db_client, consumer, matter["id"])).json()["ticket"]
    cancelled = await db_client.post(
        f"{MATTERS}/{matter['id']}/cancel", json={}, headers=advocate.headers
    )
    assert cancelled.status_code == 200

    with pytest.raises(CallDeniedError) as denied:
        await _gatekeeper(db_txn_session).authorize(ticket, uuid.UUID(matter["id"]))

    assert denied.value.code == "ended"


async def test_a_suspended_user_cannot_join_with_a_ticket_issued_before_suspension(
    db_client: AsyncClient, db_txn_session: Any
) -> None:
    consumer, _advocate, matter = await _consultation(db_client, db_txn_session)
    ticket = (await _session(db_client, consumer, matter["id"])).json()["ticket"]
    user = await db_txn_session.scalar(select(User).where(User.id == uuid.UUID(consumer.user_id)))
    user.is_active = False
    await db_txn_session.commit()

    with pytest.raises(CallDeniedError) as denied:
        await _gatekeeper(db_txn_session).authorize(ticket, uuid.UUID(matter["id"]))

    assert denied.value.code == "forbidden"


@pytest.mark.parametrize("who", ["outsider", "wrong_role"])
async def test_a_forged_ticket_for_someone_who_is_not_a_participant_is_refused(
    db_client: AsyncClient, db_txn_session: Any, who: str
) -> None:
    _consumer, advocate, matter = await _consultation(db_client, db_txn_session)
    outsider = await register_consumer(db_client)
    user_id, actor = (
        (uuid.UUID(outsider.user_id), Actor.CONSUMER)
        if who == "outsider"
        else (uuid.UUID(advocate.user_id), Actor.CONSUMER)  # a real participant, wrong role
    )
    forged = issue_ticket(
        user_id=user_id, matter_id=uuid.UUID(matter["id"]), actor=actor, settings=get_settings()
    )

    with pytest.raises(CallDeniedError) as denied:
        await _gatekeeper(db_txn_session).authorize(forged, uuid.UUID(matter["id"]))

    assert denied.value.code == "forbidden"


# --- call records -----------------------------------------------------------------------------


async def test_a_call_is_recorded_from_opening_to_end_with_its_duration(
    db_client: AsyncClient, db_txn_session: Any
) -> None:
    consumer, advocate, matter = await _consultation(db_client, db_txn_session)
    clock = {"now": datetime.now(UTC)}
    gate, grant = await _grant(
        db_client, db_txn_session, advocate, matter["id"], clock=lambda: clock["now"]
    )

    call_id = await gate.open_call(grant)
    assert await gate.open_call(grant) == call_id  # the same open call, not a second one
    clock["now"] += timedelta(seconds=5)
    await gate.mark_connected(call_id)
    clock["now"] += timedelta(seconds=60)
    await gate.close_call(call_id, "hangup")
    clock["now"] += timedelta(seconds=99)
    await gate.close_call(call_id, "disconnect")  # too late: the first ending stands

    status = (
        await db_client.get(f"{MATTERS}/{matter['id']}/call", headers=consumer.headers)
    ).json()
    (call,) = status["calls"]
    assert call["opened_by"] == "ADVOCATE"
    assert call["duration_seconds"] == 60
    assert call["ended_reason"] == "hangup"


async def test_a_call_nobody_joined_has_no_duration(
    db_client: AsyncClient, db_txn_session: Any
) -> None:
    consumer, advocate, matter = await _consultation(db_client, db_txn_session)
    gate, grant = await _grant(db_client, db_txn_session, consumer, matter["id"])
    call_id = await gate.open_call(grant)

    await gate.close_call(call_id, "disconnect")

    status = (
        await db_client.get(f"{MATTERS}/{matter['id']}/call", headers=advocate.headers)
    ).json()
    assert status["calls"][0]["connected_at"] is None
    assert status["calls"][0]["duration_seconds"] is None


async def test_an_open_call_left_by_a_crash_is_superseded_not_reused(
    db_client: AsyncClient, db_txn_session: Any
) -> None:
    consumer, _advocate, matter = await _consultation(db_client, db_txn_session)
    gate, grant = await _grant(db_client, db_txn_session, consumer, matter["id"])
    stale_id = await gate.open_call(grant)
    stale = await db_txn_session.scalar(select(MatterCall).where(MatterCall.id == stale_id))
    stale.opened_at = datetime.now(UTC) - timedelta(hours=7)
    await db_txn_session.commit()

    fresh_id = await gate.open_call(grant)

    assert fresh_id != stale_id
    await db_txn_session.refresh(stale)
    assert stale.ended_reason == "superseded"


# --- "someone is waiting" ---------------------------------------------------------------------


async def test_the_other_person_is_told_when_someone_is_waiting_in_the_room(
    db_client: AsyncClient, db_txn_session: Any, outbox: Outbox
) -> None:
    consumer, advocate, matter = await _consultation(db_client, db_txn_session)
    gate, grant = await _grant(db_client, db_txn_session, advocate, matter["id"])
    outbox.sent.clear()

    await gate.notify_waiting(grant)
    await gate.notify_waiting(grant)  # rejoining while the first is unread adds nothing

    feed = (await db_client.get("/api/v1/notifications", headers=consumer.headers)).json()
    waiting = [n for n in feed["items"] if n["kind"] == "CALL_WAITING"]
    assert len(waiting) == 1
    assert waiting[0]["link"] == f"/matters/{matter['id']}/call"
    assert "Adv. Kavya Rao" in waiting[0]["body"]
    # The advocate isn't told about their own arrival, and the email carries no details.
    advocate_feed = (await db_client.get("/api/v1/notifications", headers=advocate.headers)).json()
    assert all(n["kind"] != "CALL_WAITING" for n in advocate_feed["items"])
    assert len(outbox.sent) == 1
    assert "Kavya" not in outbox.sent[0][2]
    row = await db_txn_session.scalar(
        select(Notification).where(Notification.kind == "CALL_WAITING")
    )
    assert str(row.user_id) == consumer.user_id
