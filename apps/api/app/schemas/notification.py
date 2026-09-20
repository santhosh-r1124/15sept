"""Notification request/response models (Phase 11)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class NotificationOut(BaseModel):
    id: uuid.UUID
    kind: str
    title: str
    body: str
    # Relative path inside the recipient's own app, e.g. "/matters/<id>".
    link: str | None
    read: bool
    created_at: datetime


class PaginatedNotifications(BaseModel):
    items: list[NotificationOut]
    total: int
    unread: int
    limit: int
    offset: int


class UnreadCountOut(BaseModel):
    unread: int


class MarkedReadOut(BaseModel):
    updated: int


class NotificationPreferences(BaseModel):
    """What the user can control. Account emails (verify / reset) are not optional."""

    email_notifications: bool
