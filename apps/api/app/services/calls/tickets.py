"""Short-lived tickets for the call WebSocket.

Browsers cannot attach an ``Authorization`` header to a WebSocket, so the socket URL has to carry
the credential. Putting the real access token in a URL would leak it into proxy and server logs,
so a participant first asks the REST API (authenticated normally) for a *ticket*: a signed token
that is valid for about a minute, for one matter, for one user, and works once. That is all the
URL ever contains.

"Works once" is enforced per process (a small in-memory set), which is enough for a credential
that expires in a minute and is only ever presented at connection time.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt

from app.core.config import Settings
from app.services.matters.lifecycle import Actor

_TYPE = "call"
_used: dict[str, float] = {}  # jti -> expiry (epoch seconds)


class InvalidTicketError(Exception):
    """The ticket is missing, malformed, expired, for another matter, or already used."""


@dataclass(frozen=True, slots=True)
class TicketClaims:
    user_id: uuid.UUID
    matter_id: uuid.UUID
    actor: Actor
    jti: str
    expires_at: float


def issue_ticket(
    *, user_id: uuid.UUID, matter_id: uuid.UUID, actor: Actor, settings: Settings
) -> str:
    now = datetime.now(UTC)
    payload = {
        "typ": _TYPE,
        "sub": str(user_id),
        "mid": str(matter_id),
        "act": actor.value,
        "jti": uuid.uuid4().hex,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=settings.call_ticket_ttl_seconds)).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def verify_ticket(ticket: str, *, matter_id: uuid.UUID, settings: Settings) -> TicketClaims:
    """Validate and *consume* a ticket. Raises ``InvalidTicketError`` for any problem."""
    try:
        payload = jwt.decode(ticket, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        if payload.get("typ") != _TYPE or payload.get("mid") != str(matter_id):
            raise InvalidTicketError("wrong ticket")
        claims = TicketClaims(
            user_id=uuid.UUID(str(payload["sub"])),
            matter_id=matter_id,
            actor=Actor(str(payload["act"])),
            jti=str(payload["jti"]),
            expires_at=float(payload["exp"]),
        )
    except InvalidTicketError:
        raise
    except (jwt.PyJWTError, KeyError, ValueError) as exc:
        raise InvalidTicketError("invalid ticket") from exc

    now = time.time()
    for jti in [j for j, exp in _used.items() if exp < now]:  # forget expired ones
        del _used[jti]
    if claims.jti in _used:
        raise InvalidTicketError("ticket already used")
    _used[claims.jti] = claims.expires_at
    return claims


def reset_used_tickets() -> None:
    """Forget consumed tickets (tests)."""
    _used.clear()
