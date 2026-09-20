"""Voice / video consultations (roadmap Phase 8 follow-up; ADR 0015).

Media is WebRTC, browser to browser. This module is only the *signaling* side: it decides who may
join, hands out a short-lived ticket and ICE servers, and relays the handshake messages between the
two participants over a WebSocket. It never sees, records or stores audio or video.

    POST /matters/{id}/call/session   -> ticket + ICE servers (participants, when the room is open)
    GET  /matters/{id}/call           -> is the room open, who is in it, recent calls
    WS   /matters/{id}/call/ws?ticket -> signaling

Socket protocol (JSON text frames)
    server -> client   {"type": "joined", "role", "peer_present"}   you are in the room
                       {"type": "peer-joined"}      the other person arrived: create the offer
                       {"type": "peer-left"}        the other person left: tear down, wait
                       {"type": "signal", "data"}   the other side's offer / answer / ICE candidate
                       {"type": "ended", "reason"}  time limit reached
                       {"type": "error", "code"}    e.g. peer_absent, bad_message
                       {"type": "pong"}
    client -> server   {"type": "signal", "data"}   relayed verbatim to the other side
                       {"type": "ping"}  {"type": "bye"}
Close codes: 4001 replaced by a newer connection of the same user, 4401 bad ticket, 4403 not
allowed, 4408 idle / time limit, 4429 too many messages, 1009 message too large.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import time
import uuid
from collections import deque
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession, SettingsDep
from app.core.config import Settings
from app.core.errors import ConflictError
from app.core.logging import get_logger
from app.db.session import get_sessionmaker
from app.models.call import MatterCall
from app.schemas.call import (
    CallAccessOut,
    CallRecordOut,
    CallSessionOut,
    CallStatusOut,
)
from app.services.calls.gatekeeper import CallDeniedError, CallGatekeeper, CallGrant
from app.services.calls.hub import Peer, Room, get_hub
from app.services.calls.rules import CallAccess, build_ice_config
from app.services.calls.tickets import issue_ticket
from app.services.matters.access import load_matter, readable_by, require_actor
from app.services.notifications.content import format_when
from app.services.rate_limit import rate_limit

router = APIRouter()
logger = get_logger("app.calls")

IDLE_TIMEOUT_SECONDS = 90.0  # clients ping every ~25 s
MAX_MESSAGE_BYTES = 16 * 1024  # an SDP with several ICE candidates is a few KB
RATE_WINDOW_SECONDS = 10.0
RATE_MAX_MESSAGES = 120  # ICE candidates arrive in bursts

_DENIAL_TEXT = {
    "not_a_consultation": "Only consultations have a call room.",
    "unpaid": "The consultation room opens once the matter has been paid.",
    "ended": "This matter has ended, so its call room is closed.",
    "window_passed": (
        "The booked time for this consultation has passed. Ask the advocate to reschedule."
    ),
}


def get_call_gatekeeper(settings: SettingsDep) -> CallGatekeeper:
    return CallGatekeeper(get_sessionmaker(), settings)


Gatekeeper = Annotated[CallGatekeeper, Depends(get_call_gatekeeper)]


def _denial_message(access: CallAccess) -> str:
    if access.reason == "too_early" and access.opens_at is not None:
        return f"The room opens at {format_when(access.opens_at)}, shortly before the booked time."
    return _DENIAL_TEXT.get(access.reason or "", "This consultation can't be joined right now.")


def _access_out(access: CallAccess) -> CallAccessOut:
    return CallAccessOut(
        allowed=access.allowed,
        reason=access.reason,
        opens_at=access.opens_at,
        closes_at=access.closes_at,
    )


def _record_out(call: MatterCall) -> CallRecordOut:
    duration = (
        int((call.ended_at - call.connected_at).total_seconds())
        if call.connected_at and call.ended_at
        else None
    )
    return CallRecordOut(
        id=call.id,
        opened_by=call.opened_by,
        opened_at=call.opened_at,
        connected_at=call.connected_at,
        ended_at=call.ended_at,
        duration_seconds=duration,
        ended_reason=call.ended_reason,
    )


@router.get("/{matter_id}/call", response_model=CallStatusOut, summary="Call room status")
async def call_status(
    matter_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    gatekeeper: Gatekeeper,
) -> CallStatusOut:
    matter = await load_matter(db, matter_id)
    readable_by(user, matter)
    calls = (
        (
            await db.execute(
                select(MatterCall)
                .where(MatterCall.matter_id == matter.id)
                .order_by(MatterCall.opened_at.desc())
                .limit(5)
            )
        )
        .scalars()
        .all()
    )
    return CallStatusOut(
        access=_access_out(gatekeeper.access_for(matter)),
        present=sorted(a.value for a in get_hub().present(matter.id)),
        calls=[_record_out(c) for c in calls],
    )


@router.post(
    "/{matter_id}/call/session",
    response_model=CallSessionOut,
    summary="Get a ticket and ICE servers to join the call room",
    dependencies=[rate_limit("call-session", limit=30, window_seconds=3600)],
)
async def start_call_session(
    matter_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    settings: SettingsDep,
    gatekeeper: Gatekeeper,
) -> CallSessionOut:
    matter = await load_matter(db, matter_id)
    actor = require_actor(user, matter)
    access = gatekeeper.access_for(matter)
    if not access.allowed:
        raise ConflictError(_denial_message(access), code=access.reason or "call_unavailable")

    ice = build_ice_config(settings, user_id=user.id, now=datetime.now(UTC))
    return CallSessionOut(
        ticket=issue_ticket(user_id=user.id, matter_id=matter.id, actor=actor, settings=settings),
        expires_in=settings.call_ticket_ttl_seconds,
        ws_path=f"/api/v1/matters/{matter.id}/call/ws",
        role=actor.value,
        ice_servers=ice.ice_servers,
        ice_transport_policy=ice.transport_policy,
        closes_at=access.closes_at,
    )


# ---- the socket ------------------------------------------------------------------------------


def _origin_allowed(websocket: WebSocket, settings: Settings) -> bool:
    """Browsers always send Origin on a WebSocket handshake. Refuse other websites' pages; allow
    a missing Origin (non-browser clients, which can't be hijacked through a victim's browser)."""
    origin = websocket.headers.get("origin")
    return origin is None or origin in settings.cors_origins


async def _send(websocket: WebSocket, payload: dict[str, Any]) -> None:
    with contextlib.suppress(Exception):  # the peer already went away
        await websocket.send_json(payload)


async def _reject(websocket: WebSocket, code: str) -> None:
    close_code = 4401 if code == "invalid_ticket" else 4403
    await _send(websocket, {"type": "error", "code": code})
    await websocket.close(code=close_code)


@router.websocket("/{matter_id}/call/ws")
async def call_socket(
    websocket: WebSocket,
    matter_id: uuid.UUID,
    settings: SettingsDep,
    gatekeeper: Gatekeeper,
    ticket: Annotated[str, Query(min_length=10, max_length=2000)],
) -> None:
    if not _origin_allowed(websocket, settings):
        await websocket.close(code=1008)
        return
    await websocket.accept()

    try:
        grant = await gatekeeper.authorize(ticket, matter_id)
    except CallDeniedError as denied:
        await _reject(websocket, denied.code)
        return

    hub = get_hub()
    me = Peer(user_id=grant.user_id, actor=grant.actor, socket=websocket)
    joined = await hub.join(matter_id, me)
    other = joined.other

    await _send(
        websocket,
        {"type": "joined", "role": grant.actor.value, "peer_present": other is not None},
    )
    if joined.replaced and other is not None:
        await _send_peer(other, {"type": "peer-left"})  # they re-negotiate with the new socket
    if other is not None:
        await _send_peer(other, {"type": "peer-joined"})  # ...and the one already here offers

    await _record_join(gatekeeper, joined.room, grant, both_present=other is not None)

    reason = "disconnect"
    last_seen = time.monotonic()
    recent: deque[float] = deque()
    try:
        while True:
            remaining = (grant.deadline - datetime.now(UTC)).total_seconds()
            if remaining <= 0:
                reason = "time_limit"
                await _send(websocket, {"type": "ended", "reason": "time_limit"})
                await websocket.close(code=4408)
                break
            try:
                raw = await asyncio.wait_for(
                    websocket.receive_text(), timeout=min(IDLE_TIMEOUT_SECONDS, remaining)
                )
            except TimeoutError:
                if time.monotonic() - last_seen >= IDLE_TIMEOUT_SECONDS:
                    reason = "idle"
                    await websocket.close(code=4408)
                    break
                continue
            last_seen = time.monotonic()

            if len(raw.encode()) > MAX_MESSAGE_BYTES:
                await websocket.close(code=1009)
                break
            recent.append(last_seen)
            while recent and last_seen - recent[0] > RATE_WINDOW_SECONDS:
                recent.popleft()
            if len(recent) > RATE_MAX_MESSAGES:
                await websocket.close(code=4429)
                break

            message = _parse(raw)
            if message is None:
                await _send(websocket, {"type": "error", "code": "bad_message"})
                continue
            kind = message.get("type")
            if kind == "ping":
                await _send(websocket, {"type": "pong"})
            elif kind == "signal" and isinstance(message.get("data"), dict):
                if not await hub.relay(matter_id, me, message["data"]):
                    await _send(websocket, {"type": "error", "code": "peer_absent"})
            elif kind == "bye":
                reason = "hangup"
                break
            else:
                await _send(websocket, {"type": "error", "code": "bad_message"})
    except WebSocketDisconnect:
        pass
    finally:
        await _leave(gatekeeper, matter_id, me, reason)


def _parse(raw: str) -> dict[str, Any] | None:
    try:
        value = json.loads(raw)
    except ValueError:
        return None
    return value if isinstance(value, dict) else None


async def _send_peer(peer: Peer, payload: dict[str, Any]) -> None:
    with contextlib.suppress(Exception):
        await peer.socket.send_json(payload)


async def _record_join(
    gatekeeper: CallGatekeeper, room: Room, grant: CallGrant, *, both_present: bool
) -> None:
    """Bookkeeping and the "someone is waiting" notification. Never allowed to break a call."""
    try:
        call_id = await gatekeeper.open_call(grant)
        if room.call_id is None:
            room.call_id = call_id
        if both_present:
            if not room.connected_recorded:
                room.connected_recorded = True
                await gatekeeper.mark_connected(call_id)
        else:
            await gatekeeper.notify_waiting(grant)
    except Exception:
        logger.exception("call_record_failed", matter_id=str(grant.matter_id))


async def _leave(gatekeeper: CallGatekeeper, matter_id: uuid.UUID, me: Peer, reason: str) -> None:
    hub = get_hub()
    left = await hub.leave(matter_id, me)
    if not left.removed:
        return
    if left.other is not None:
        await _send_peer(left.other, {"type": "peer-left"})
    if left.room_empty and left.call_id is not None:
        try:
            await gatekeeper.close_call(left.call_id, reason)
        except Exception:
            logger.exception("call_record_failed", matter_id=str(matter_id))
