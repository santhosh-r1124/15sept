"""When can a consultation call happen, and how do peers reach each other? (pure, unit-tested)

The rules
---------
A call room exists only for a **CONSULTATION** matter that has been **paid** and not ended.

* If the advocate has *scheduled* it, the room opens ``join_early`` before the booked time and
  closes ``grace`` after the booked length has elapsed, so a late start or an overrun isn't cut off
  mid-sentence but a stale link can't be used days later.
* If it is paid but *not yet scheduled*, either side may open the room ad hoc (the "on-demand"
  consultation of the FRD); the other is notified. The call is capped (``max_unscheduled``).

ICE / TURN
----------
Media goes browser-to-browser. STUN (free, public) lets each side discover its address; when a
network blocks direct paths a TURN relay is needed. TURN credentials are the standard coturn
"REST API" scheme: a username that carries its own expiry, and a password that is the base64
HMAC-SHA1 of it under a shared secret - so the credentials handed to a browser stop working on
their own and no per-user state is stored.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.core.config import Settings
from app.core.errors import ServiceUnavailableError
from app.models.matter import MatterServiceType, MatterStatus

_UNPAID = (MatterStatus.REQUESTED, MatterStatus.ACCEPTED)
_ENDED = (MatterStatus.CLOSED, MatterStatus.REJECTED, MatterStatus.CANCELLED)


@dataclass(frozen=True, slots=True)
class CallAccess:
    allowed: bool
    # Why not, when not allowed: not_a_consultation, unpaid, ended, too_early, window_passed.
    reason: str | None = None
    opens_at: datetime | None = None
    closes_at: datetime | None = None


def call_access(
    *,
    service_type: MatterServiceType,
    status: MatterStatus,
    scheduled_at: datetime | None,
    consultation_minutes: int | None,
    now: datetime,
    join_early: timedelta,
    grace: timedelta,
) -> CallAccess:
    if service_type is not MatterServiceType.CONSULTATION:
        return CallAccess(False, "not_a_consultation")
    if status in _UNPAID:
        return CallAccess(False, "unpaid")
    if status in _ENDED:
        return CallAccess(False, "ended")
    if scheduled_at is None:
        return CallAccess(True)  # paid, unscheduled: an ad hoc call
    opens_at = scheduled_at - join_early
    closes_at = scheduled_at + timedelta(minutes=consultation_minutes or 60) + grace
    if now < opens_at:
        return CallAccess(False, "too_early", opens_at, closes_at)
    if now > closes_at:
        return CallAccess(False, "window_passed", opens_at, closes_at)
    return CallAccess(True, None, opens_at, closes_at)


@dataclass(frozen=True, slots=True)
class IceConfig:
    ice_servers: list[dict[str, object]]
    # "relay" hides both parties' IP addresses from each other (everything goes via TURN).
    transport_policy: str


def turn_credentials(secret: str, user_id: uuid.UUID, *, expires_at: int) -> tuple[str, str]:
    """coturn ``use-auth-secret`` credentials: (username, password) valid until ``expires_at``."""
    username = f"{expires_at}:{user_id}"
    digest = hmac.new(secret.encode(), username.encode(), hashlib.sha1).digest()
    return username, base64.b64encode(digest).decode()


def build_ice_config(settings: Settings, *, user_id: uuid.UUID, now: datetime) -> IceConfig:
    servers: list[dict[str, object]] = []
    if settings.webrtc_stun_urls:
        servers.append({"urls": list(settings.webrtc_stun_urls)})

    has_turn = bool(settings.webrtc_turn_urls and settings.webrtc_turn_secret)
    if has_turn and settings.webrtc_turn_secret:
        expires_at = int(now.timestamp()) + settings.webrtc_turn_ttl_seconds
        username, credential = turn_credentials(
            settings.webrtc_turn_secret, user_id, expires_at=expires_at
        )
        servers.append(
            {
                "urls": list(settings.webrtc_turn_urls),
                "username": username,
                "credential": credential,
            }
        )

    if settings.webrtc_relay_only and not has_turn:
        # Better to refuse than to silently expose both parties' IP addresses to each other
        # when the operator asked for them to be hidden.
        raise ServiceUnavailableError(
            "Calls are set to relay-only but no TURN server is configured.",
            code="calls_misconfigured",
        )
    return IceConfig(
        ice_servers=servers, transport_policy="relay" if settings.webrtc_relay_only else "all"
    )
