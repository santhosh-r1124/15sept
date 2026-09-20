"""Everything the call WebSocket needs from the database, kept out of the socket handler.

The handler must not hold a database session for the length of a call (an hour is a long time to
pin a pooled connection), so each method here opens a short session of its own, and the handler
depends on this class rather than on a request-scoped session. That also lets the WebSocket tests
substitute a fake gatekeeper - the relay logic is testable without a database - while the real
one is tested against Postgres directly.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import NotFoundError
from app.core.logging import get_logger
from app.models.call import MatterCall
from app.models.matter import Matter
from app.models.user import User
from app.services.calls.rules import CallAccess, call_access
from app.services.calls.tickets import InvalidTicketError, verify_ticket
from app.services.matters.access import actor_for, load_matter
from app.services.matters.lifecycle import Actor
from app.services.notifications import content as notice
from app.services.notifications import deliver_request_emails, notify

logger = get_logger("app.calls")

SessionFactory = Callable[[], AbstractAsyncContextManager[AsyncSession]]

# A call row left open by a crash is superseded rather than reused after this long.
_STALE_AFTER = timedelta(hours=6)


class CallDeniedError(Exception):
    """The caller may not join. ``code`` is safe to show the client."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class CallGrant:
    user_id: uuid.UUID
    actor: Actor
    matter_id: uuid.UUID
    title: str
    display_name: str | None
    deadline: datetime  # the socket is closed at this moment


class CallGatekeeper:
    def __init__(
        self,
        session_factory: SessionFactory,
        settings: Settings,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._session = session_factory
        self._settings = settings
        self._clock = clock

    def access_for(self, matter: Matter) -> CallAccess:
        return call_access(
            service_type=matter.service_type,
            status=matter.status,
            scheduled_at=matter.scheduled_at,
            consultation_minutes=matter.consultation_minutes,
            now=self._clock(),
            join_early=timedelta(minutes=self._settings.call_join_early_minutes),
            grace=timedelta(minutes=self._settings.call_grace_minutes),
        )

    async def authorize(self, ticket: str, matter_id: uuid.UUID) -> CallGrant:
        """Consume the ticket and re-check *everything* against the database as it is now - the
        ticket only proves who asked a minute ago, not that they may still join."""
        try:
            claims = verify_ticket(ticket, matter_id=matter_id, settings=self._settings)
        except InvalidTicketError as exc:
            raise CallDeniedError("invalid_ticket") from exc

        async with self._session() as db:
            try:
                matter = await load_matter(db, matter_id)
            except NotFoundError as exc:
                raise CallDeniedError("not_found") from exc
            user = await db.get(User, claims.user_id)
            if user is None or not user.is_active:
                raise CallDeniedError("forbidden")
            actor = actor_for(user, matter)
            if actor is None or actor is not claims.actor:
                raise CallDeniedError("forbidden")
            access = self.access_for(matter)
            if not access.allowed:
                raise CallDeniedError(access.reason or "unavailable")
            deadline = access.closes_at or (
                self._clock() + timedelta(minutes=self._settings.call_max_unscheduled_minutes)
            )
            return CallGrant(
                user_id=user.id,
                actor=actor,
                matter_id=matter.id,
                title=matter.title,
                display_name=user.display_name,
                deadline=deadline,
            )

    async def open_call(self, grant: CallGrant) -> uuid.UUID:
        """The matter's open call row (created if there isn't one). Idempotent per room."""
        now = self._clock()
        async with self._session() as db:
            row = await db.scalar(
                select(MatterCall)
                .where(MatterCall.matter_id == grant.matter_id, MatterCall.ended_at.is_(None))
                .order_by(MatterCall.opened_at.desc())
                .limit(1)
            )
            if row is not None and now - row.opened_at < _STALE_AFTER:
                return row.id
            if row is not None:
                row.ended_at, row.ended_reason = now, "superseded"
            call = MatterCall(
                id=uuid.uuid4(), matter_id=grant.matter_id, opened_by=grant.actor.value
            )
            db.add(call)
            await db.commit()
            return call.id

    async def mark_connected(self, call_id: uuid.UUID) -> None:
        async with self._session() as db:
            await db.execute(
                update(MatterCall)
                .where(MatterCall.id == call_id, MatterCall.connected_at.is_(None))
                .values(connected_at=self._clock())
            )
            await db.commit()

    async def close_call(self, call_id: uuid.UUID, reason: str) -> None:
        async with self._session() as db:
            await db.execute(
                update(MatterCall)
                .where(MatterCall.id == call_id, MatterCall.ended_at.is_(None))
                .values(ended_at=self._clock(), ended_reason=reason)
            )
            await db.commit()

    async def notify_waiting(self, grant: CallGrant) -> None:
        """Tell the *other* participant someone is in the room (coalesced until they read it)."""
        async with self._session() as db:
            matter = await load_matter(db, grant.matter_id)
            other = (
                matter.advocate_profile.user if grant.actor is Actor.CONSUMER else matter.consumer
            )
            await notify(
                db,
                self._settings,
                other,
                notice.call_waiting(
                    matter_id=matter.id, title=matter.title, who=grant.display_name
                ),
                coalesce=True,
            )
            await db.commit()
            await deliver_request_emails(db)
