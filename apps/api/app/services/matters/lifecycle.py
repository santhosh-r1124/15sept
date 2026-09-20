r"""Matter lifecycle: which status changes are legal, and who may make them (Phase 8).

Pure logic — no DB, no I/O — so every transition is unit-testable exhaustively. The route
layer (app/api/v1/routes/matters.py) loads the matter, asks this module whether the
requested action is allowed for this actor, and only then mutates and persists.

    REQUESTED --accept--> ACCEPTED --pay--> PAID --schedule--> SCHEDULED --close--> CLOSED
        |                    |               \--close (document services)--------^
        |--reject--> REJECTED |--cancel--> CANCELLED
        \--cancel--> CANCELLED

PAID matters can't be cancelled yet: unwinding a payment needs the refund flow (Phase 10),
so until then a paid matter can only move forward (schedule/close).
"""

from __future__ import annotations

import enum

from app.models.matter import MatterServiceType, MatterStatus

__all__ = ["TERMINAL_STATUSES", "Action", "Actor", "can_post_message", "transition_for"]


class Actor(enum.StrEnum):
    CONSUMER = "CONSUMER"
    ADVOCATE = "ADVOCATE"


class Action(enum.StrEnum):
    ACCEPT = "ACCEPT"
    REJECT = "REJECT"
    CANCEL = "CANCEL"
    PAY = "PAY"
    SCHEDULE = "SCHEDULE"
    CLOSE = "CLOSE"


TERMINAL_STATUSES = frozenset({MatterStatus.CLOSED, MatterStatus.REJECTED, MatterStatus.CANCELLED})

# (action, actor, from_status) -> to_status
_TRANSITIONS: dict[tuple[Action, Actor, MatterStatus], MatterStatus] = {
    (Action.ACCEPT, Actor.ADVOCATE, MatterStatus.REQUESTED): MatterStatus.ACCEPTED,
    (Action.REJECT, Actor.ADVOCATE, MatterStatus.REQUESTED): MatterStatus.REJECTED,
    (Action.CANCEL, Actor.CONSUMER, MatterStatus.REQUESTED): MatterStatus.CANCELLED,
    (Action.CANCEL, Actor.CONSUMER, MatterStatus.ACCEPTED): MatterStatus.CANCELLED,
    (Action.CANCEL, Actor.ADVOCATE, MatterStatus.ACCEPTED): MatterStatus.CANCELLED,
    (Action.PAY, Actor.CONSUMER, MatterStatus.ACCEPTED): MatterStatus.PAID,
    (Action.SCHEDULE, Actor.ADVOCATE, MatterStatus.PAID): MatterStatus.SCHEDULED,
    # Rescheduling: SCHEDULED -> SCHEDULED.
    (Action.SCHEDULE, Actor.ADVOCATE, MatterStatus.SCHEDULED): MatterStatus.SCHEDULED,
    (Action.CLOSE, Actor.ADVOCATE, MatterStatus.PAID): MatterStatus.CLOSED,
    (Action.CLOSE, Actor.ADVOCATE, MatterStatus.SCHEDULED): MatterStatus.CLOSED,
}


def transition_for(
    action: Action, actor: Actor, current: MatterStatus, service_type: MatterServiceType
) -> MatterStatus | None:
    """The resulting status, or ``None`` if this actor can't do this now.

    Two rules depend on the service type: only a CONSULTATION is ever scheduled (document
    services have no appointment), and a CONSULTATION can't be closed straight from PAID —
    it has to be scheduled (and held) first.
    """
    target = _TRANSITIONS.get((action, actor, current))
    if target is None:
        return None
    is_consultation = service_type is MatterServiceType.CONSULTATION
    if action is Action.SCHEDULE and not is_consultation:
        return None
    if action is Action.CLOSE and current is MatterStatus.PAID and is_consultation:
        return None
    return target


def can_post_message(status: MatterStatus) -> bool:
    """Threads are open until the matter reaches a terminal state, then read-only."""
    return status not in TERMINAL_STATUSES
