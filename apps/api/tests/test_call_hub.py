"""Unit tests for the signaling hub, with in-memory fake sockets. No database, no network."""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from app.services.calls.hub import CLOSE_REPLACED, Peer, SignalingHub
from app.services.matters.lifecycle import Actor

MATTER = uuid.UUID("22222222-2222-4222-8222-222222222222")


class FakeSocket:
    def __init__(self, name: str) -> None:
        self.name = name
        self.sent: list[Any] = []
        self.closed: list[tuple[int, str | None]] = []
        self.broken = False

    async def send_json(self, data: Any) -> None:
        if self.broken:
            raise ConnectionError("socket is gone")
        self.sent.append(data)

    async def close(self, code: int = 1000, reason: str | None = None) -> None:
        self.closed.append((code, reason))


def _peer(actor: Actor, name: str | None = None, user_id: uuid.UUID | None = None) -> Peer:
    return Peer(
        user_id=user_id or uuid.uuid4(), actor=actor, socket=FakeSocket(name or actor.value)
    )


def _sock(peer: Peer) -> FakeSocket:
    assert isinstance(peer.socket, FakeSocket)
    return peer.socket


async def test_the_first_person_in_waits_alone_and_the_second_finds_them() -> None:
    hub = SignalingHub()
    client, advocate = _peer(Actor.CONSUMER), _peer(Actor.ADVOCATE)

    first = await hub.join(MATTER, client)
    second = await hub.join(MATTER, advocate)

    assert (first.other, first.replaced) == (None, False)
    assert second.other is client
    assert hub.present(MATTER) == {Actor.CONSUMER, Actor.ADVOCATE}


async def test_signals_go_to_the_other_person_only_and_are_passed_on_untouched() -> None:
    hub = SignalingHub()
    client, advocate = _peer(Actor.CONSUMER), _peer(Actor.ADVOCATE)
    await hub.join(MATTER, client)
    await hub.join(MATTER, advocate)
    offer = {"kind": "offer", "sdp": "v=0\r\n..."}

    delivered = await hub.relay(MATTER, client, offer)

    assert delivered is True
    assert _sock(advocate).sent == [{"type": "signal", "data": offer}]
    assert _sock(client).sent == []  # never echoed back to the sender


async def test_a_signal_with_nobody_else_in_the_room_is_not_delivered() -> None:
    hub = SignalingHub()
    client = _peer(Actor.CONSUMER)
    await hub.join(MATTER, client)

    assert await hub.relay(MATTER, client, {"kind": "offer"}) is False
    assert await hub.relay(uuid.uuid4(), client, {"kind": "offer"}) is False  # no such room


async def test_a_dead_socket_makes_relay_report_failure_instead_of_raising() -> None:
    hub = SignalingHub()
    client, advocate = _peer(Actor.CONSUMER), _peer(Actor.ADVOCATE)
    await hub.join(MATTER, client)
    await hub.join(MATTER, advocate)
    _sock(advocate).broken = True

    assert await hub.relay(MATTER, client, {"kind": "candidate"}) is False


async def test_the_same_user_connecting_again_replaces_their_old_connection() -> None:
    hub = SignalingHub()
    advocate = _peer(Actor.ADVOCATE)
    client = _peer(Actor.CONSUMER)
    await hub.join(MATTER, advocate)
    await hub.join(MATTER, client)
    refreshed = Peer(user_id=client.user_id, actor=Actor.CONSUMER, socket=FakeSocket("tab 2"))

    result = await hub.join(MATTER, refreshed)

    assert result.replaced is True
    assert result.other is advocate
    assert _sock(client).closed == [(CLOSE_REPLACED, "replaced")]
    # Signals now reach the new connection.
    await hub.relay(MATTER, advocate, {"kind": "offer"})
    assert _sock(refreshed).sent == [{"type": "signal", "data": {"kind": "offer"}}]
    assert _sock(client).sent == []


async def test_a_replaced_connection_cleaning_up_does_not_evict_its_successor() -> None:
    hub = SignalingHub()
    client = _peer(Actor.CONSUMER)
    await hub.join(MATTER, client)
    refreshed = Peer(user_id=client.user_id, actor=Actor.CONSUMER, socket=FakeSocket("tab 2"))
    await hub.join(MATTER, refreshed)

    stale = await hub.leave(MATTER, client)  # the old socket's handler finishing up

    assert stale.removed is False
    assert hub.present(MATTER) == {Actor.CONSUMER}  # the new connection is still in the room


async def test_leaving_tells_you_who_is_left_and_the_last_to_leave_closes_the_room() -> None:
    hub = SignalingHub()
    client, advocate = _peer(Actor.CONSUMER), _peer(Actor.ADVOCATE)
    joined = await hub.join(MATTER, client)
    joined.room.call_id = uuid.uuid4()
    await hub.join(MATTER, advocate)

    first = await hub.leave(MATTER, client)
    second = await hub.leave(MATTER, advocate)

    assert (first.removed, first.other, first.room_empty) == (True, advocate, False)
    assert (second.removed, second.other, second.room_empty) == (True, None, True)
    assert second.call_id == joined.room.call_id
    assert hub.present(MATTER) == frozenset()
    assert hub.room(MATTER) is None


async def test_when_someone_leaves_the_connected_flag_resets_so_a_return_is_recorded_again() -> (
    None
):
    hub = SignalingHub()
    client, advocate = _peer(Actor.CONSUMER), _peer(Actor.ADVOCATE)
    joined = await hub.join(MATTER, client)
    await hub.join(MATTER, advocate)
    joined.room.connected_recorded = True

    await hub.leave(MATTER, advocate)

    assert joined.room.connected_recorded is False


async def test_rooms_are_independent() -> None:
    hub = SignalingHub()
    other_matter = uuid.uuid4()
    a, b = _peer(Actor.CONSUMER), _peer(Actor.ADVOCATE)
    await hub.join(MATTER, a)
    await hub.join(other_matter, b)

    assert await hub.relay(MATTER, a, {"kind": "offer"}) is False  # b is in a different room
    assert hub.present(MATTER) == {Actor.CONSUMER}
    assert hub.present(other_matter) == {Actor.ADVOCATE}


@pytest.mark.parametrize(
    "actors", [(Actor.CONSUMER, Actor.ADVOCATE), (Actor.ADVOCATE, Actor.CONSUMER)]
)
async def test_either_side_can_arrive_first(actors: tuple[Actor, Actor]) -> None:
    hub = SignalingHub()
    early, late = _peer(actors[0]), _peer(actors[1])

    await hub.join(MATTER, early)
    result = await hub.join(MATTER, late)

    assert result.other is early
