"""Unit tests for consultation-call rules, ICE / TURN config and tickets. No database."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from app.core.config import Settings
from app.core.errors import ServiceUnavailableError
from app.models.matter import MatterServiceType, MatterStatus
from app.services.calls.rules import build_ice_config, call_access, turn_credentials
from app.services.calls.tickets import (
    InvalidTicketError,
    issue_ticket,
    reset_used_tickets,
    verify_ticket,
)
from app.services.matters.lifecycle import Actor

NOW = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)
EARLY = timedelta(minutes=10)
GRACE = timedelta(minutes=30)
USER = uuid.UUID("0f0f0f0f-0000-4000-8000-000000000001")


def _access(**overrides: Any) -> Any:
    args: dict[str, Any] = {
        "service_type": MatterServiceType.CONSULTATION,
        "status": MatterStatus.SCHEDULED,
        "scheduled_at": NOW + timedelta(minutes=30),
        "consultation_minutes": 30,
        "now": NOW,
        "join_early": EARLY,
        "grace": GRACE,
    }
    return call_access(**{**args, **overrides})


# --- who can have a call, and when ------------------------------------------------------------


@pytest.mark.parametrize(
    "service_type",
    [t for t in MatterServiceType if t is not MatterServiceType.CONSULTATION],
)
def test_only_consultations_have_a_call_room(service_type: MatterServiceType) -> None:
    result = _access(service_type=service_type, status=MatterStatus.PAID, scheduled_at=None)

    assert (result.allowed, result.reason) == (False, "not_a_consultation")


@pytest.mark.parametrize("status", [MatterStatus.REQUESTED, MatterStatus.ACCEPTED])
def test_an_unpaid_matter_has_no_room(status: MatterStatus) -> None:
    assert _access(status=status, scheduled_at=None).reason == "unpaid"


@pytest.mark.parametrize(
    "status", [MatterStatus.CLOSED, MatterStatus.REJECTED, MatterStatus.CANCELLED]
)
def test_an_ended_matter_has_no_room_even_inside_the_window(status: MatterStatus) -> None:
    assert _access(status=status, scheduled_at=NOW).reason == "ended"


def test_a_paid_but_unscheduled_consultation_can_be_joined_ad_hoc() -> None:
    result = _access(status=MatterStatus.PAID, scheduled_at=None)

    assert result.allowed is True
    assert (result.opens_at, result.closes_at) == (None, None)


def test_the_room_opens_ten_minutes_before_the_booked_time() -> None:
    booked = NOW + timedelta(minutes=30)

    too_early = _access(scheduled_at=booked, now=booked - EARLY - timedelta(seconds=1))
    just_open = _access(scheduled_at=booked, now=booked - EARLY)

    assert (too_early.allowed, too_early.reason) == (False, "too_early")
    assert too_early.opens_at == booked - EARLY
    assert just_open.allowed is True


def test_the_room_stays_open_for_the_booked_length_plus_a_grace_period() -> None:
    booked = NOW
    closes = booked + timedelta(minutes=30) + GRACE  # 30-minute consultation

    at_close = _access(scheduled_at=booked, now=closes)
    after = _access(scheduled_at=booked, now=closes + timedelta(seconds=1))

    assert at_close.allowed is True
    assert at_close.closes_at == closes
    assert (after.allowed, after.reason) == (False, "window_passed")


def test_a_missing_length_is_treated_as_an_hour() -> None:
    result = _access(scheduled_at=NOW, consultation_minutes=None)

    assert result.closes_at == NOW + timedelta(minutes=60) + GRACE


# --- TURN credentials and ICE servers ---------------------------------------------------------


def test_turn_credentials_match_an_independently_computed_hmac() -> None:
    # Expected value produced with `openssl dgst -sha1 -hmac` (coturn's "use-auth-secret" scheme).
    username, credential = turn_credentials("static-auth-secret", USER, expires_at=1_900_000_000)

    assert username == f"1900000000:{USER}"
    assert credential == "yZRfIspO7SCf2aX1rl0PeuiZ3Zs="


def _settings(**overrides: Any) -> Settings:
    return Settings(_env_file=None, **overrides)  # type: ignore[call-arg]


def test_by_default_only_a_stun_server_is_offered_and_relay_is_not_forced() -> None:
    config = build_ice_config(_settings(), user_id=USER, now=NOW)

    assert config.ice_servers == [{"urls": ["stun:stun.l.google.com:19302"]}]
    assert config.transport_policy == "all"


def test_a_turn_server_gets_per_user_credentials_that_expire() -> None:
    settings = _settings(
        webrtc_turn_urls=["turn:turn.example.com:3478?transport=udp"],
        webrtc_turn_secret="static-auth-secret",
        webrtc_turn_ttl_seconds=600,
    )

    config = build_ice_config(settings, user_id=USER, now=NOW)

    turn = config.ice_servers[1]
    expires_at = int(NOW.timestamp()) + 600
    assert turn["urls"] == ["turn:turn.example.com:3478?transport=udp"]
    assert turn["username"] == f"{expires_at}:{USER}"
    assert (
        turn["credential"] == turn_credentials("static-auth-secret", USER, expires_at=expires_at)[1]
    )
    # The shared secret itself is never handed to a browser.
    assert "static-auth-secret" not in str(config.ice_servers)


def test_turn_urls_without_a_secret_are_not_offered() -> None:
    config = build_ice_config(
        _settings(webrtc_turn_urls=["turn:turn.example.com"]), user_id=USER, now=NOW
    )

    assert len(config.ice_servers) == 1  # STUN only


def test_relay_only_forces_the_relay_policy_when_turn_is_configured() -> None:
    settings = _settings(
        webrtc_turn_urls=["turns:turn.example.com:5349"],
        webrtc_turn_secret="s3cret",
        webrtc_relay_only=True,
    )

    assert build_ice_config(settings, user_id=USER, now=NOW).transport_policy == "relay"


def test_relay_only_without_turn_refuses_rather_than_exposing_ip_addresses() -> None:
    with pytest.raises(ServiceUnavailableError) as raised:
        build_ice_config(_settings(webrtc_relay_only=True), user_id=USER, now=NOW)

    assert raised.value.code == "calls_misconfigured"


def test_url_lists_can_come_from_comma_separated_environment_values() -> None:
    settings = _settings(
        webrtc_stun_urls="stun:a.example:3478, stun:b.example:3478",
        webrtc_turn_urls="turn:t1.example, turn:t2.example",
    )

    assert settings.webrtc_stun_urls == ["stun:a.example:3478", "stun:b.example:3478"]
    assert settings.webrtc_turn_urls == ["turn:t1.example", "turn:t2.example"]


# --- tickets ----------------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _fresh_tickets() -> None:
    reset_used_tickets()


MATTER = uuid.UUID("22222222-2222-4222-8222-222222222222")


def test_a_ticket_identifies_the_user_matter_and_role() -> None:
    settings = _settings()
    ticket = issue_ticket(user_id=USER, matter_id=MATTER, actor=Actor.ADVOCATE, settings=settings)

    claims = verify_ticket(ticket, matter_id=MATTER, settings=settings)

    assert (claims.user_id, claims.matter_id, claims.actor) == (USER, MATTER, Actor.ADVOCATE)


def test_a_ticket_works_only_once() -> None:
    settings = _settings()
    ticket = issue_ticket(user_id=USER, matter_id=MATTER, actor=Actor.CONSUMER, settings=settings)
    verify_ticket(ticket, matter_id=MATTER, settings=settings)

    with pytest.raises(InvalidTicketError):
        verify_ticket(ticket, matter_id=MATTER, settings=settings)


def test_a_ticket_is_only_good_for_its_own_matter() -> None:
    settings = _settings()
    ticket = issue_ticket(user_id=USER, matter_id=MATTER, actor=Actor.CONSUMER, settings=settings)

    with pytest.raises(InvalidTicketError):
        verify_ticket(ticket, matter_id=uuid.uuid4(), settings=settings)


def test_an_expired_ticket_is_refused() -> None:
    settings = _settings(call_ticket_ttl_seconds=-5)
    ticket = issue_ticket(user_id=USER, matter_id=MATTER, actor=Actor.CONSUMER, settings=settings)

    with pytest.raises(InvalidTicketError):
        verify_ticket(ticket, matter_id=MATTER, settings=settings)


def test_an_ordinary_access_token_is_not_a_ticket() -> None:
    from app.core import security

    settings = _settings()
    access = security.create_access_token(user_id=USER, role="CONSUMER", settings=settings)

    with pytest.raises(InvalidTicketError):
        verify_ticket(access, matter_id=MATTER, settings=settings)


@pytest.mark.parametrize("garbage", ["", "not-a-jwt", "a.b.c", "x" * 200])
def test_garbage_and_tampered_tickets_are_refused(garbage: str) -> None:
    settings = _settings()
    with pytest.raises(InvalidTicketError):
        verify_ticket(garbage, matter_id=MATTER, settings=settings)

    good = issue_ticket(user_id=USER, matter_id=MATTER, actor=Actor.CONSUMER, settings=settings)
    header, payload, signature = good.split(".")
    tampered = f"{header}.{payload}.{signature[:-4]}AAAA"
    with pytest.raises(InvalidTicketError):
        verify_ticket(tampered, matter_id=MATTER, settings=settings)
