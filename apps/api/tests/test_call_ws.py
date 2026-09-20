"""The call WebSocket end to end over real frames (Starlette's TestClient), with a fake
gatekeeper so no database is needed. What the gatekeeper does against Postgres is covered in
test_calls.py; here the subject is the relay: who hears what, and what gets a connection closed."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

import app.api.v1.routes.calls as calls_module
from app.api.v1.routes.calls import get_call_gatekeeper
from app.main import create_app
from app.services.calls.gatekeeper import CallDeniedError, CallGrant
from app.services.calls.hub import reset_hub
from app.services.calls.tickets import reset_used_tickets
from app.services.matters.lifecycle import Actor

MATTER = uuid.UUID("22222222-2222-4222-8222-222222222222")
CLIENT_ID = uuid.UUID(int=1)
ADVOCATE_ID = uuid.UUID(int=2)
ORIGIN = {"origin": "http://localhost:3000"}


class FakeGatekeeper:
    def __init__(self) -> None:
        self.grants: dict[str, CallGrant] = {}
        self.denials: dict[str, str] = {}
        self.call_id = uuid.uuid4()
        self.opened: list[Actor] = []
        self.connected: list[uuid.UUID] = []
        self.closed: list[tuple[uuid.UUID, str]] = []
        self.notified: list[Actor] = []

    def allow(
        self,
        ticket: str,
        actor: Actor,
        *,
        user_id: uuid.UUID | None = None,
        deadline: datetime | None = None,
    ) -> None:
        self.grants[ticket] = CallGrant(
            user_id=user_id or (CLIENT_ID if actor is Actor.CONSUMER else ADVOCATE_ID),
            actor=actor,
            matter_id=MATTER,
            title="A matter",
            display_name=actor.value.title(),
            deadline=deadline or datetime.now(UTC) + timedelta(hours=1),
        )

    async def authorize(self, ticket: str, matter_id: uuid.UUID) -> CallGrant:
        if ticket in self.denials:
            raise CallDeniedError(self.denials[ticket])
        grant = self.grants.get(ticket)
        if grant is None:
            raise CallDeniedError("invalid_ticket")
        return grant

    async def open_call(self, grant: CallGrant) -> uuid.UUID:
        self.opened.append(grant.actor)
        return self.call_id

    async def mark_connected(self, call_id: uuid.UUID) -> None:
        self.connected.append(call_id)

    async def close_call(self, call_id: uuid.UUID, reason: str) -> None:
        self.closed.append((call_id, reason))

    async def notify_waiting(self, grant: CallGrant) -> None:
        self.notified.append(grant.actor)


@dataclass
class Harness:
    tc: TestClient
    gate: FakeGatekeeper

    def connect(self, ticket: str, headers: dict[str, str] | None = None) -> Any:
        return self.tc.websocket_connect(
            f"/api/v1/matters/{MATTER}/call/ws?ticket={ticket}", headers=headers or ORIGIN
        )


@pytest.fixture
def harness() -> Iterator[Harness]:
    reset_hub()
    reset_used_tickets()
    app = create_app()
    gate = FakeGatekeeper()
    gate.allow("ticket-client", Actor.CONSUMER)
    gate.allow("ticket-advocate", Actor.ADVOCATE)
    app.dependency_overrides[get_call_gatekeeper] = lambda: gate
    # One TestClient context = one event loop shared by every socket, like a real server.
    with TestClient(app) as tc:
        yield Harness(tc, gate)
    reset_hub()


def _closed(ws: Any) -> int:
    message = ws.receive()
    assert message["type"] == "websocket.close", message
    return int(message["code"])


# --- meeting -----------------------------------------------------------------------------------


def test_the_first_person_in_waits_and_the_other_side_is_told(harness: Harness) -> None:
    with harness.connect("ticket-advocate") as advocate:
        assert advocate.receive_json() == {
            "type": "joined",
            "role": "ADVOCATE",
            "peer_present": False,
        }

    assert harness.gate.opened == [Actor.ADVOCATE]
    assert harness.gate.notified == [Actor.ADVOCATE]  # "someone is waiting" goes to the client
    assert harness.gate.connected == []


def test_when_the_second_person_arrives_the_first_is_asked_to_make_the_offer(
    harness: Harness,
) -> None:
    with harness.connect("ticket-advocate") as advocate:
        advocate.receive_json()  # joined, alone
        with harness.connect("ticket-client") as client:
            assert client.receive_json() == {
                "type": "joined",
                "role": "CONSUMER",
                "peer_present": True,
            }
            assert advocate.receive_json() == {"type": "peer-joined"}

    assert harness.gate.connected == [harness.gate.call_id]  # recorded once, when both were in
    assert harness.gate.notified == [Actor.ADVOCATE]  # the late arrival didn't notify anyone


def test_handshake_messages_are_relayed_both_ways_untouched(harness: Harness) -> None:
    offer = {"kind": "offer", "sdp": "v=0\r\no=- 1 1 IN IP4 0.0.0.0\r\n"}
    answer = {"kind": "answer", "sdp": "v=0\r\no=- 2 2 IN IP4 0.0.0.0\r\n"}
    candidate = {
        "kind": "candidate",
        "candidate": {"candidate": "candidate:1 1 udp 1 1.2.3.4 5 typ host"},
    }
    with harness.connect("ticket-advocate") as advocate, harness.connect("ticket-client") as client:
        advocate.receive_json()
        client.receive_json()
        advocate.receive_json()  # peer-joined

        advocate.send_json({"type": "signal", "data": offer})
        assert client.receive_json() == {"type": "signal", "data": offer}
        client.send_json({"type": "signal", "data": answer})
        assert advocate.receive_json() == {"type": "signal", "data": answer}
        client.send_json({"type": "signal", "data": candidate})
        assert advocate.receive_json() == {"type": "signal", "data": candidate}


def test_a_signal_with_nobody_to_receive_it_is_reported(harness: Harness) -> None:
    with harness.connect("ticket-client") as client:
        client.receive_json()

        client.send_json({"type": "signal", "data": {"kind": "offer"}})

        assert client.receive_json() == {"type": "error", "code": "peer_absent"}


# --- leaving -----------------------------------------------------------------------------------


def test_hanging_up_tells_the_other_side_and_the_call_is_recorded_as_a_hangup(
    harness: Harness,
) -> None:
    with harness.connect("ticket-advocate") as advocate:
        advocate.receive_json()
        with harness.connect("ticket-client") as client:
            client.receive_json()
            advocate.receive_json()  # peer-joined

            client.send_json({"type": "bye"})

            assert advocate.receive_json() == {"type": "peer-left"}
        advocate.send_json({"type": "bye"})

    assert harness.gate.closed == [(harness.gate.call_id, "hangup")]


def test_dropping_the_connection_is_recorded_as_a_disconnect(harness: Harness) -> None:
    with harness.connect("ticket-client") as client:
        client.receive_json()

    assert harness.gate.closed == [(harness.gate.call_id, "disconnect")]


def test_the_call_is_only_closed_when_the_room_is_empty(harness: Harness) -> None:
    with harness.connect("ticket-advocate") as advocate:
        advocate.receive_json()
        with harness.connect("ticket-client") as client:
            client.receive_json()
        assert advocate.receive_json() == {"type": "peer-joined"}
        assert advocate.receive_json() == {"type": "peer-left"}
        assert harness.gate.closed == []  # the advocate is still there

    assert len(harness.gate.closed) == 1


def test_reconnecting_replaces_the_old_socket_and_the_other_side_renegotiates(
    harness: Harness,
) -> None:
    with harness.connect("ticket-advocate") as advocate:
        advocate.receive_json()
        with harness.connect("ticket-client") as old_tab:
            old_tab.receive_json()
            advocate.receive_json()  # peer-joined
            harness.gate.allow("ticket-client-2", Actor.CONSUMER)  # same user, second tab

            with harness.connect("ticket-client-2") as new_tab:
                assert new_tab.receive_json()["peer_present"] is True
                assert _closed(old_tab) == 4001
                assert advocate.receive_json() == {"type": "peer-left"}
                assert advocate.receive_json() == {"type": "peer-joined"}

                # The advocate now talks to the new tab.
                advocate.send_json({"type": "signal", "data": {"kind": "offer"}})
                assert new_tab.receive_json() == {"type": "signal", "data": {"kind": "offer"}}

    assert len(harness.gate.closed) == 1  # one call, not two


# --- refusals ----------------------------------------------------------------------------------


def test_an_unknown_ticket_is_told_so_and_closed(harness: Harness) -> None:
    with harness.connect("not-a-real-ticket") as ws:
        assert ws.receive_json() == {"type": "error", "code": "invalid_ticket"}
        assert _closed(ws) == 4401

    assert harness.gate.opened == []


@pytest.mark.parametrize("reason", ["too_early", "ended", "forbidden", "unpaid"])
def test_a_refused_join_is_closed_with_its_reason(harness: Harness, reason: str) -> None:
    harness.gate.denials["ticket-client"] = reason

    with harness.connect("ticket-client") as ws:
        assert ws.receive_json() == {"type": "error", "code": reason}
        assert _closed(ws) == 4403


def test_a_page_on_another_website_cannot_open_the_socket(harness: Harness) -> None:
    evil = {"origin": "https://evil.example"}
    with pytest.raises(WebSocketDisconnect) as refused, harness.connect("ticket-client", evil):
        pass

    assert refused.value.code == 1008
    assert harness.gate.opened == []


def test_a_client_that_sends_no_origin_header_is_allowed(harness: Harness) -> None:
    with harness.tc.websocket_connect(
        f"/api/v1/matters/{MATTER}/call/ws?ticket=ticket-client"
    ) as ws:
        assert ws.receive_json()["type"] == "joined"


def test_a_ticket_that_is_too_short_never_reaches_the_gatekeeper(harness: Harness) -> None:
    with pytest.raises(WebSocketDisconnect), harness.connect("x"):
        pass

    assert harness.gate.opened == []


# --- misbehaviour ------------------------------------------------------------------------------


def test_ping_gets_a_pong(harness: Harness) -> None:
    with harness.connect("ticket-client") as ws:
        ws.receive_json()
        ws.send_json({"type": "ping"})

        assert ws.receive_json() == {"type": "pong"}


@pytest.mark.parametrize(
    "frame",
    [
        "not json",
        "[1, 2, 3]",
        '"a string"',
        '{"type": "launch-missiles"}',
        '{"type": "signal"}',
        '{"type": "signal", "data": "not-an-object"}',
    ],
)
def test_malformed_messages_get_an_error_and_the_socket_stays_open(
    harness: Harness, frame: str
) -> None:
    with harness.connect("ticket-client") as ws:
        ws.receive_json()

        ws.send_text(frame)

        assert ws.receive_json() == {"type": "error", "code": "bad_message"}
        ws.send_json({"type": "ping"})
        assert ws.receive_json() == {"type": "pong"}  # still usable


def test_an_oversized_message_closes_the_connection(harness: Harness) -> None:
    with harness.connect("ticket-client") as ws:
        ws.receive_json()

        ws.send_text("x" * (calls_module.MAX_MESSAGE_BYTES + 1))

        assert _closed(ws) == 1009


def test_flooding_closes_the_connection(harness: Harness, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(calls_module, "RATE_MAX_MESSAGES", 3)
    with harness.connect("ticket-client") as ws:
        ws.receive_json()

        for _ in range(6):
            ws.send_json({"type": "ping"})

        seen: list[Any] = []
        while True:
            message = ws.receive()
            if message["type"] == "websocket.close":
                seen.append(message["code"])
                break
        assert seen == [4429]


def test_a_silent_connection_is_dropped_when_it_goes_idle(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(calls_module, "IDLE_TIMEOUT_SECONDS", 0.3)
    with harness.connect("ticket-client") as ws:
        ws.receive_json()

        assert _closed(ws) == 4408

    assert harness.gate.closed[-1][1] == "idle"


def test_the_socket_is_closed_when_the_bookable_window_ends(harness: Harness) -> None:
    harness.gate.allow(
        "ticket-short", Actor.CONSUMER, deadline=datetime.now(UTC) + timedelta(seconds=0.4)
    )
    with harness.connect("ticket-short") as ws:
        ws.receive_json()

        assert ws.receive_json() == {"type": "ended", "reason": "time_limit"}
        assert _closed(ws) == 4408

    assert harness.gate.closed[-1][1] == "time_limit"
