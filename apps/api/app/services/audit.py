"""Recording privileged actions in the audit log (Phase 13).

Call ``record`` in the same request, before the commit that makes the action real: the audit row
then commits (or rolls back) together with it, so the log never claims something that didn't happen
and never misses something that did. For a read (an admin viewing private chat content) there is no
action to commit, so the route commits the row itself.

Keep ``detail`` to small, non-sensitive facts. Never put message text, document contents or personal
data in it: the log is retained long after the thing it describes may have been erased.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.audit import AuditLog
from app.models.user import User
from app.services.rate_limit import client_ip


def _plain(detail: dict[str, Any] | None) -> dict[str, Any] | None:
    """JSON-safe copy (Decimals, UUIDs and datetimes become strings)."""
    if not detail:
        return None
    result: dict[str, Any] = json.loads(json.dumps(detail, default=str))
    return result


def record(
    db: AsyncSession,
    *,
    actor: User | None,
    action: str,
    target_type: str | None = None,
    target_id: object | None = None,
    detail: dict[str, Any] | None = None,
    request: Request | None = None,
) -> AuditLog:
    ip: str | None = None
    request_id: str | None = None
    if request is not None:
        ip = client_ip(request, get_settings().trusted_proxy_count)
        raw_id = getattr(request.state, "request_id", None)
        request_id = raw_id if isinstance(raw_id, str) else None
    entry = AuditLog(
        actor_id=actor.id if actor else None,
        actor_role=actor.role.value if actor else None,
        action=action,
        target_type=target_type,
        target_id=str(target_id) if target_id is not None else None,
        detail=_plain(detail),
        ip=ip,
        request_id=request_id,
    )
    db.add(entry)
    return entry
