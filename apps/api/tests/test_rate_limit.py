"""Tests for rate limiting (Phase 13). The unit tests need no services; the HTTP ones use the
database client (a wrong-password login is then a clean 401, an invalid chat body a clean 422)."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from httpx import AsyncClient
from starlette.requests import Request

from app.services.rate_limit import (
    MemoryBackend,
    RateLimiter,
    RedisBackend,
    client_ip,
    set_rate_limiter,
)


class Clock:
    """A settable monotonic clock."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def _limiter(clock: Clock, **kwargs: Any) -> RateLimiter:
    return RateLimiter(kwargs.pop("primary", None), clock=clock, **kwargs)


async def _check(limiter: RateLimiter, identity: str = "ip:1.2.3.4", *, limit: int = 3) -> Any:
    return await limiter.check(scope="login", identity=identity, limit=limit, window_seconds=60)


# --- the counter ------------------------------------------------------------------------------


async def test_allows_up_to_the_limit_then_blocks_with_a_retry_after() -> None:
    clock = Clock()
    limiter = _limiter(clock)

    decisions = [await _check(limiter) for _ in range(5)]

    assert [d.allowed for d in decisions] == [True, True, True, False, False]
    assert [d.remaining for d in decisions] == [2, 1, 0, 0, 0]
    assert decisions[3].retry_after == 60
    clock.now += 45
    assert (await _check(limiter)).retry_after == 15  # counts down as the window runs out


async def test_the_window_resets() -> None:
    clock = Clock()
    limiter = _limiter(clock)
    for _ in range(4):
        await _check(limiter)

    clock.now += 60

    assert (await _check(limiter)).allowed is True


async def test_identities_and_scopes_are_counted_separately() -> None:
    limiter = _limiter(Clock())
    for _ in range(4):
        await _check(limiter, "ip:1.1.1.1")

    assert (await _check(limiter, "ip:1.1.1.1")).allowed is False
    assert (await _check(limiter, "ip:2.2.2.2")).allowed is True  # someone else
    other_scope = await limiter.check(
        scope="chat", identity="ip:1.1.1.1", limit=3, window_seconds=60
    )
    assert other_scope.allowed is True


async def test_a_disabled_limiter_allows_everything() -> None:
    limiter = _limiter(Clock(), enabled=False)

    allowed = [(await _check(limiter, limit=1)).allowed for _ in range(10)]

    assert all(allowed)


async def test_the_memory_backend_forgets_expired_windows_when_it_grows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.services.rate_limit as module

    monkeypatch.setattr(module, "_MEMORY_PRUNE_AT", 5)
    clock = Clock()
    backend = MemoryBackend(clock)
    for i in range(5):
        await backend.hit(f"k{i}", 10)
    clock.now += 11

    await backend.hit("fresh", 10)  # sixth key triggers the prune

    assert list(backend._windows) == ["fresh"]


# --- Redis, and what happens when it isn't there ----------------------------------------------


class FakeRedis:
    def __init__(self) -> None:
        self.calls: list[tuple[Any, ...]] = []
        self.fail = False

    async def eval(self, script: str, numkeys: int, key: str, window: int) -> list[int]:
        self.calls.append((numkeys, key, window))
        if self.fail:
            raise ConnectionError("redis is down")
        return [len(self.calls), window]


async def test_redis_backend_runs_one_atomic_script_per_hit() -> None:
    redis = FakeRedis()
    limiter = _limiter(Clock(), primary=RedisBackend(redis))

    first = await _check(limiter)
    second = await _check(limiter)

    assert (first.allowed, second.allowed, second.remaining) == (True, True, 1)
    assert redis.calls == [(1, "rl:login:ip:1.2.3.4", 60)] * 2


async def test_when_redis_dies_limiting_continues_in_process_and_redis_is_left_alone() -> None:
    clock = Clock()
    redis = FakeRedis()
    redis.fail = True
    limiter = _limiter(clock, primary=RedisBackend(redis))

    decisions = [await _check(limiter) for _ in range(5)]

    # No exception escaped, and the limit still applies (locally).
    assert [d.allowed for d in decisions] == [True, True, True, False, False]
    assert len(redis.calls) == 1  # one failure, then Redis is skipped for a while

    clock.now += 31  # pause over: it is tried again, and used once healthy
    redis.fail = False
    assert (await _check(limiter, "ip:9.9.9.9")).allowed is True
    assert len(redis.calls) == 2


# --- who is the client? -----------------------------------------------------------------------


def _request(peer: str | None, forwarded: str | None = None) -> Request:
    headers = [(b"x-forwarded-for", forwarded.encode())] if forwarded else []
    return Request(
        {
            "type": "http",
            "headers": headers,
            "client": (peer, 5000) if peer else None,
            "method": "GET",
            "path": "/",
        }
    )


def test_without_trusted_proxies_the_forwarded_header_is_ignored() -> None:
    # Anyone can send this header; believing it would let them dodge every limit.
    assert client_ip(_request("10.0.0.7", "6.6.6.6"), trusted_proxy_count=0) == "10.0.0.7"


def test_behind_one_proxy_the_client_is_the_last_hop_our_proxy_wrote() -> None:
    # The client forged "6.6.6.6"; our proxy appended the address it really saw.
    request = _request("10.0.0.7", "6.6.6.6, 203.0.113.5")
    assert client_ip(request, trusted_proxy_count=1) == "203.0.113.5"


def test_behind_two_proxies_skip_both() -> None:
    request = _request("10.0.0.7", "6.6.6.6, 203.0.113.5, 10.1.1.1")
    assert client_ip(request, trusted_proxy_count=2) == "203.0.113.5"


def test_a_missing_or_short_forwarded_chain_falls_back_to_the_socket() -> None:
    assert client_ip(_request("10.0.0.7"), trusted_proxy_count=1) == "10.0.0.7"
    assert client_ip(_request("10.0.0.7", "1.1.1.1"), trusted_proxy_count=2) == "10.0.0.7"
    assert client_ip(_request(None), trusted_proxy_count=0) == "unknown"


# --- over HTTP --------------------------------------------------------------------------------

LOGIN = "/api/v1/auth/login"
BAD_LOGIN = {"email": "nobody@example.com", "password": "wrong-password-123"}


@pytest.fixture
def live_limiter() -> Iterator[RateLimiter]:
    """A limiter that is switched on (the suite runs with limits off)."""
    limiter = RateLimiter(None, enabled=True)
    set_rate_limiter(limiter)
    yield limiter
    set_rate_limiter(None)


async def test_login_is_limited_with_the_standard_error_and_retry_after(
    db_client: AsyncClient, live_limiter: RateLimiter
) -> None:
    # 10 attempts a minute get as far as the credential check (401)...
    first_ten = [(await db_client.post(LOGIN, json=BAD_LOGIN)).status_code for _ in range(10)]
    assert set(first_ten) == {401}

    # ...the 11th is refused before any password is looked at.
    blocked = await db_client.post(LOGIN, json=BAD_LOGIN)
    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "rate_limited"
    assert blocked.json()["error"]["request_id"]
    assert 1 <= int(blocked.headers["retry-after"]) <= 60


async def test_the_forwarded_header_only_counts_when_proxies_are_trusted(
    db_client: AsyncClient, live_limiter: RateLimiter, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.core.config import get_settings

    def forged(i: int) -> dict[str, str]:
        return {"X-Forwarded-For": f"9.9.9.{i}"}

    # Default (no trusted proxy): rotating a forged header does not buy fresh allowances.
    for i in range(10):
        await db_client.post(LOGIN, json=BAD_LOGIN, headers=forged(i))
    assert (await db_client.post(LOGIN, json=BAD_LOGIN, headers=forged(99))).status_code == 429

    # Behind one trusted proxy the last hop is the real client, so distinct clients are distinct.
    set_rate_limiter(RateLimiter(None, enabled=True))
    monkeypatch.setenv("TRUSTED_PROXY_COUNT", "1")
    get_settings.cache_clear()
    codes = [
        (await db_client.post(LOGIN, json=BAD_LOGIN, headers=forged(i))).status_code
        for i in range(12)
    ]
    assert set(codes) == {401}


async def test_anonymous_chat_is_limited_harder_than_logged_in_chat(
    db_client: AsyncClient, live_limiter: RateLimiter
) -> None:
    from tests.helpers import register_consumer

    consumer = await register_consumer(db_client)
    chat = "/api/v1/chat/messages"

    # An empty body is a 422 - it still counts, but never reaches an LLM.
    anonymous = [(await db_client.post(chat, json={})).status_code for _ in range(11)]
    assert anonymous[:10] == [422] * 10
    assert anonymous[10] == 429

    signed_in = [
        (await db_client.post(chat, json={}, headers=consumer.headers)).status_code
        for _ in range(11)
    ]
    assert signed_in == [422] * 11  # their ceiling is 30 a minute, tracked per account


async def test_registration_is_limited_per_address(
    db_client: AsyncClient, live_limiter: RateLimiter
) -> None:
    from tests.conftest import unique_email

    codes = []
    for _ in range(6):
        resp = await db_client.post(
            "/api/v1/auth/register",
            json={"email": unique_email("rl"), "password": "correct horse battery staple"},
        )
        codes.append(resp.status_code)

    assert codes == [201, 201, 201, 201, 201, 429]
