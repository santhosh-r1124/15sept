"""Consultation call request/response models."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class CallAccessOut(BaseModel):
    allowed: bool
    # not_a_consultation | unpaid | ended | too_early | window_passed (when not allowed)
    reason: str | None
    opens_at: datetime | None
    closes_at: datetime | None


class CallRecordOut(BaseModel):
    id: uuid.UUID
    opened_by: str
    opened_at: datetime
    connected_at: datetime | None
    ended_at: datetime | None
    duration_seconds: int | None  # connected -> ended; None if the other side never joined
    ended_reason: str | None


class CallStatusOut(BaseModel):
    access: CallAccessOut
    # Who is in the room right now ("CONSUMER" / "ADVOCATE"). Live for this API instance only.
    present: list[str]
    calls: list[CallRecordOut]


class CallSessionOut(BaseModel):
    """Everything the browser needs to join: a one-minute ticket, and the ICE servers."""

    ticket: str
    expires_in: int
    ws_path: str  # relative to the API origin, e.g. /api/v1/matters/<id>/call/ws
    role: str
    ice_servers: list[dict[str, Any]]
    ice_transport_policy: str
    closes_at: datetime | None
