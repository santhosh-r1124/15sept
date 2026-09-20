"""Unit tests for the matter state machine + pricing — pure logic, no DB."""

from __future__ import annotations

from decimal import Decimal
from itertools import product

import pytest

from app.core.config import Settings
from app.core.errors import ServiceUnavailableError
from app.models.matter import MatterServiceType as S
from app.models.matter import MatterStatus as M
from app.services.matters.lifecycle import (
    TERMINAL_STATUSES,
    Action,
    Actor,
    can_post_message,
    transition_for,
)
from app.services.matters.pricing import default_quote
from app.services.payments import MockPaymentProvider, get_payment_provider

DOC = S.DOCUMENT_REVIEW
CONSULT = S.CONSULTATION


def test_consultation_happy_path() -> None:
    assert transition_for(Action.ACCEPT, Actor.ADVOCATE, M.REQUESTED, CONSULT) is M.ACCEPTED
    assert transition_for(Action.PAY, Actor.CONSUMER, M.ACCEPTED, CONSULT) is M.PAID
    assert transition_for(Action.SCHEDULE, Actor.ADVOCATE, M.PAID, CONSULT) is M.SCHEDULED
    assert transition_for(Action.CLOSE, Actor.ADVOCATE, M.SCHEDULED, CONSULT) is M.CLOSED


def test_document_service_skips_scheduling() -> None:
    assert transition_for(Action.PAY, Actor.CONSUMER, M.ACCEPTED, DOC) is M.PAID
    assert transition_for(Action.SCHEDULE, Actor.ADVOCATE, M.PAID, DOC) is None
    assert transition_for(Action.CLOSE, Actor.ADVOCATE, M.PAID, DOC) is M.CLOSED


def test_consultation_cannot_close_before_being_scheduled() -> None:
    assert transition_for(Action.CLOSE, Actor.ADVOCATE, M.PAID, CONSULT) is None


def test_rescheduling_stays_scheduled() -> None:
    assert transition_for(Action.SCHEDULE, Actor.ADVOCATE, M.SCHEDULED, CONSULT) is M.SCHEDULED


def test_reject_and_cancel_paths() -> None:
    assert transition_for(Action.REJECT, Actor.ADVOCATE, M.REQUESTED, CONSULT) is M.REJECTED
    assert transition_for(Action.CANCEL, Actor.CONSUMER, M.REQUESTED, CONSULT) is M.CANCELLED
    assert transition_for(Action.CANCEL, Actor.CONSUMER, M.ACCEPTED, CONSULT) is M.CANCELLED
    assert transition_for(Action.CANCEL, Actor.ADVOCATE, M.ACCEPTED, CONSULT) is M.CANCELLED


def test_advocate_cannot_cancel_before_accepting_and_consumer_cannot_accept() -> None:
    assert transition_for(Action.CANCEL, Actor.ADVOCATE, M.REQUESTED, CONSULT) is None
    assert transition_for(Action.ACCEPT, Actor.CONSUMER, M.REQUESTED, CONSULT) is None
    assert transition_for(Action.PAY, Actor.ADVOCATE, M.ACCEPTED, CONSULT) is None


def test_paid_matters_cannot_be_cancelled_until_refunds_exist() -> None:
    for actor in Actor:
        assert transition_for(Action.CANCEL, actor, M.PAID, CONSULT) is None


@pytest.mark.parametrize(("action", "actor", "service"), list(product(Action, Actor, S)))
def test_terminal_states_allow_no_transitions(action: Action, actor: Actor, service: S) -> None:
    for status in TERMINAL_STATUSES:
        assert transition_for(action, actor, status, service) is None


def test_every_non_terminal_status_has_a_way_forward() -> None:
    for status in set(M) - TERMINAL_STATUSES:
        moves = [transition_for(a, actor, status, s) for a, actor, s in product(Action, Actor, S)]
        assert any(m is not None for m in moves), status


def test_message_threads_close_with_the_matter() -> None:
    for status in M:
        assert can_post_message(status) is (status not in TERMINAL_STATUSES)


@pytest.mark.parametrize(
    ("minutes", "expected"),
    [(60, "1200.00"), (30, "600.00"), (15, "300.00")],
)
def test_consultation_quote_is_prorated_from_the_hourly_fee(minutes: int, expected: str) -> None:
    assert default_quote(CONSULT, minutes, Decimal("1200.00")) == Decimal(expected)


def test_quote_rounds_to_paise() -> None:
    assert default_quote(CONSULT, 15, Decimal("999.99")) == Decimal("250.00")  # 249.9975


def test_no_default_quote_for_document_services_or_missing_fee() -> None:
    assert default_quote(DOC, None, Decimal("1200.00")) is None
    assert default_quote(CONSULT, 30, None) is None


def test_mock_payments_work_outside_production_and_are_refused_in_production() -> None:
    assert isinstance(get_payment_provider(Settings(app_env="development")), MockPaymentProvider)
    with pytest.raises(ServiceUnavailableError) as exc:
        get_payment_provider(Settings(app_env="production"))
    assert exc.value.code == "payments_not_configured"


def test_unknown_payment_provider_is_rejected() -> None:
    with pytest.raises(ServiceUnavailableError):
        get_payment_provider(Settings(payment_provider="nonsense"))
