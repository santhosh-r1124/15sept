"""In-process signaling hub: who is in which consultation room, and relaying their WebRTC
handshake messages.

The hub never looks inside a ``signal`` payload (SDP offers/answers, ICE candidates) - it only
hands it to the *other* participant. Media never comes here at all: it flows browser to browser
(or through a TURN relay, encrypted end to end).

A room holds at most one connection per user, so at most two people (the client and the
advocate). If the same user connects again (a refresh, a second tab) the older connection is
closed with code 4001 and the new one takes its place.

**Single-instance limit**: rooms live in this process's memory, so both participants must reach the
same API instance. Behind a load balancer, either pin call sockets to an instance (sticky routing
on the matter id) or replace this class with a Redis pub/sub relay - the interface below is all the
endpoint uses.
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol

from app.services.matters.lifecycle import Actor

CLOSE_REPLACED = 4001


class SocketLike(Protocol):
    async def send_json(self, data: Any) -> None: ...

    async def close(self, code: int = 1000, reason: str | None = None) -> None: ...


@dataclass(eq=False)
class Peer:
    user_id: uuid.UUID
    actor: Actor
    socket: SocketLike


@dataclass
class Room:
    peers: dict[uuid.UUID, Peer] = field(default_factory=dict)
    call_id: uuid.UUID | None = None
    connected_recorded: bool = False


@dataclass(frozen=True, slots=True)
class JoinResult:
    other: Peer | None  # the participant who was already in the room
    replaced: bool  # the same user was already connected (their old socket has been closed)
    room: Room


@dataclass(frozen=True, slots=True)
class LeaveResult:
    removed: bool  # False when this peer had already been replaced by a newer connection
    other: Peer | None
    room_empty: bool
    call_id: uuid.UUID | None


async def _quietly(coro: Any) -> None:
    with contextlib.suppress(Exception):  # a socket that is already gone is not our problem here
        await coro


class SignalingHub:
    def __init__(self) -> None:
        self._rooms: dict[uuid.UUID, Room] = {}
        self._lock = asyncio.Lock()

    async def join(self, matter_id: uuid.UUID, peer: Peer) -> JoinResult:
        async with self._lock:
            room = self._rooms.setdefault(matter_id, Room())
            previous = room.peers.get(peer.user_id)
            other = next((p for uid, p in room.peers.items() if uid != peer.user_id), None)
            room.peers[peer.user_id] = peer
        if previous is not None:
            await _quietly(previous.socket.close(CLOSE_REPLACED, "replaced"))
        return JoinResult(other=other, replaced=previous is not None, room=room)

    async def leave(self, matter_id: uuid.UUID, peer: Peer) -> LeaveResult:
        async with self._lock:
            room = self._rooms.get(matter_id)
            if room is None or room.peers.get(peer.user_id) is not peer:
                # Already replaced by a newer connection of the same user (or the room is gone):
                # the old socket's cleanup must not evict its successor.
                return LeaveResult(False, None, False, None)
            del room.peers[peer.user_id]
            other = next(iter(room.peers.values()), None)
            empty = not room.peers
            call_id = room.call_id
            if empty:
                del self._rooms[matter_id]
            else:
                room.connected_recorded = False
            return LeaveResult(True, other, empty, call_id)

    async def relay(self, matter_id: uuid.UUID, sender: Peer, data: Any) -> bool:
        """Deliver ``data`` to the other participant. False if nobody else is there."""
        room = self._rooms.get(matter_id)
        target = None
        if room is not None:
            target = next((p for uid, p in room.peers.items() if uid != sender.user_id), None)
        if target is None:
            return False
        try:
            await target.socket.send_json({"type": "signal", "data": data})
        except Exception:
            return False
        return True

    def room(self, matter_id: uuid.UUID) -> Room | None:
        return self._rooms.get(matter_id)

    def present(self, matter_id: uuid.UUID) -> frozenset[Actor]:
        room = self._rooms.get(matter_id)
        return frozenset(p.actor for p in room.peers.values()) if room else frozenset()


_hub: SignalingHub | None = None


def get_hub() -> SignalingHub:
    global _hub
    if _hub is None:
        _hub = SignalingHub()
    return _hub


def reset_hub() -> None:
    """Drop all rooms (tests)."""
    global _hub
    _hub = None
