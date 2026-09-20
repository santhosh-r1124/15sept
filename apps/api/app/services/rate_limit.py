"""Rate limiting (Phase 13).

A fixed-window counter per (scope, identity). Two backends:

* ``RedisBackend`` - shared across API instances; the normal production path. One Lua script
  does INCR + EXPIRE atomically, so a crash can't leave a counter without a TTL (which would be
  a permanent lock-out).
* ``MemoryBackend`` - per process. Used when Redis is unreachable, so a Redis outage *degrades*
  the limits (each instance counts separately) instead of removing them or failing requests.

So the limiter fails **open-ish**: it never turns a Redis problem into a 500, and it keeps
limiting locally while degraded. After a Redis error the primary is skipped for a short pause, so
a dead Redis costs one timeout, not one per request.

Identity is the caller's IP (anonymous endpoints) or user id. The IP comes from the socket unless
``TRUSTED_PROXY_COUNT`` says N reverse proxies sit in front - then it is the Nth entry from the
*right* of ``X-Forwarded-For``, the part our own proxies wrote. Trusting the header blindly would
let anyone dodge every limit by sending a fake one.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from fastapi import Depends, Request, params

from app.api.deps import OptionalUser, SettingsDep
from app.core.config import Settings
from app.core.errors import RateLimitedError
from app.core.logging import get_logger

logger = get_logger("app.rate_limit")

_REDIS_PAUSE_SECONDS = 30.0
_MEMORY_PRUNE_AT = 10_000

# INCR + EXPIRE atomically; heal a counter that somehow has no TTL. Returns {count, ttl}.
_LUA = """
local count = redis.call('INCR', KEYS[1])
local ttl = redis.call('TTL', KEYS[1])
if count == 1 or ttl < 0 then
  redis.call('EXPIRE', KEYS[1], ARGV[1])
  ttl = tonumber(ARGV[1])
end
return {count, ttl}
"""


class Backend(Protocol):
    async def hit(self, key: str, window_seconds: int) -> tuple[int, int]:
        """Count one request; return (requests so far in this window, seconds until reset)."""
        ...


class MemoryBackend:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._windows: dict[str, tuple[float, int]] = {}  # key -> (window ends at, count)

    async def hit(self, key: str, window_seconds: int) -> tuple[int, int]:
        now = self._clock()
        ends, count = self._windows.get(key, (0.0, 0))
        if now >= ends:
            ends, count = now + window_seconds, 0
        count += 1
        self._windows[key] = (ends, count)
        if len(self._windows) > _MEMORY_PRUNE_AT:
            self._windows = {k: v for k, v in self._windows.items() if v[0] > now}
        return count, max(1, int(ends - now + 0.999))


class RedisBackend:
    def __init__(self, redis: Any) -> None:
        self._redis = redis

    async def hit(self, key: str, window_seconds: int) -> tuple[int, int]:
        count, ttl = await self._redis.eval(_LUA, 1, key, window_seconds)
        return int(count), max(1, int(ttl))


@dataclass(frozen=True, slots=True)
class Decision:
    allowed: bool
    remaining: int
    retry_after: int  # seconds; meaningful when not allowed


class RateLimiter:
    def __init__(
        self,
        primary: Backend | None,
        *,
        fallback: Backend | None = None,
        enabled: bool = True,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.enabled = enabled
        self._primary = primary
        self._fallback: Backend = fallback or MemoryBackend(clock)
        self._clock = clock
        self._primary_down_until = 0.0

    async def check(
        self, *, scope: str, identity: str, limit: int, window_seconds: int
    ) -> Decision:
        if not self.enabled:
            return Decision(True, limit, 0)
        key = f"rl:{scope}:{identity}"
        count, ttl = await self._hit(key, window_seconds)
        return Decision(count <= limit, max(0, limit - count), ttl)

    async def _hit(self, key: str, window_seconds: int) -> tuple[int, int]:
        if self._primary is not None and self._clock() >= self._primary_down_until:
            try:
                return await self._primary.hit(key, window_seconds)
            except Exception as exc:
                self._primary_down_until = self._clock() + _REDIS_PAUSE_SECONDS
                logger.warning("rate_limit_backend_unavailable", error_type=type(exc).__name__)
        return await self._fallback.hit(key, window_seconds)


def client_ip(request: Request, trusted_proxy_count: int) -> str:
    peer = request.client.host if request.client else "unknown"
    if trusted_proxy_count > 0:
        forwarded = request.headers.get("x-forwarded-for", "")
        hops = [part.strip() for part in forwarded.split(",") if part.strip()]
        if len(hops) >= trusted_proxy_count:
            return hops[-trusted_proxy_count]
    return peer


# ---- process-wide limiter -------------------------------------------------------------------

_limiter: RateLimiter | None = None


def get_rate_limiter(settings: Settings) -> RateLimiter:
    global _limiter
    if _limiter is None:
        primary: Backend | None = None
        if settings.rate_limit_enabled:
            from app.services.redis import get_redis

            primary = RedisBackend(get_redis())
        _limiter = RateLimiter(primary, enabled=settings.rate_limit_enabled)
    return _limiter


def set_rate_limiter(limiter: RateLimiter | None) -> None:
    """Replace the process-wide limiter (tests). ``None`` rebuilds it from settings next use."""
    global _limiter
    _limiter = limiter


# ---- the FastAPI dependency -----------------------------------------------------------------


def rate_limit(
    scope: str,
    *,
    limit: int,
    window_seconds: int,
    anonymous_limit: int | None = None,
) -> params.Depends:
    """Dependency: allow ``limit`` requests per ``window_seconds`` per user (or per IP when the
    caller isn't logged in - with ``anonymous_limit`` if that should be stricter). Raises a 429
    with ``Retry-After`` beyond it."""

    async def _dependency(request: Request, settings: SettingsDep, user: OptionalUser) -> None:
        limiter = get_rate_limiter(settings)
        if not limiter.enabled:
            return
        if user is not None:
            identity, allowed = f"user:{user.id}", limit
        else:
            ip = client_ip(request, settings.trusted_proxy_count)
            identity, allowed = (
                f"ip:{ip}",
                anonymous_limit if anonymous_limit is not None else limit,
            )
        decision = await limiter.check(
            scope=scope, identity=identity, limit=allowed, window_seconds=window_seconds
        )
        if not decision.allowed:
            logger.info("rate_limited", scope=scope, kind=identity.split(":", 1)[0])
            raise RateLimitedError(retry_after=decision.retry_after)

    dependency: params.Depends = Depends(_dependency)
    return dependency
