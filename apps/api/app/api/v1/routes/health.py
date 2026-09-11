"""Liveness and readiness probes.

``/health``        — liveness: process is up. Never touches dependencies.
``/health/ready``  — readiness: can the app serve traffic? Checks Postgres and
                     Redis. Returns 503 when any dependency is unhealthy.
"""

from __future__ import annotations

import time
from typing import Literal

from fastapi import APIRouter, Response, status
from pydantic import BaseModel
from sqlalchemy import text

from app.api.deps import RedisDep, SettingsDep
from app.core.logging import get_logger
from app.db.session import get_sessionmaker

logger = get_logger("app.health")

router = APIRouter()

HealthState = Literal["ok", "degraded", "error"]


class LivenessResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: str
    version: str


class ComponentHealth(BaseModel):
    status: HealthState
    latency_ms: float | None = None
    detail: str | None = None


class ReadinessResponse(BaseModel):
    status: HealthState
    version: str
    environment: str
    checks: dict[str, ComponentHealth]


@router.get("/health", response_model=LivenessResponse, summary="Liveness probe")
async def liveness(settings: SettingsDep) -> LivenessResponse:
    return LivenessResponse(service=settings.app_name, version=settings.version)


async def _check_database() -> ComponentHealth:
    start = time.perf_counter()
    try:
        async with get_sessionmaker()() as session:
            await session.execute(text("SELECT 1"))
        return ComponentHealth(
            status="ok", latency_ms=round((time.perf_counter() - start) * 1000, 2)
        )
    except Exception as exc:  # report any failure as "unhealthy"
        logger.warning("readiness_db_failed", error=str(exc))
        return ComponentHealth(status="error", detail=type(exc).__name__)


async def _check_redis(redis: RedisDep) -> ComponentHealth:
    start = time.perf_counter()
    try:
        await redis.ping()
        return ComponentHealth(
            status="ok", latency_ms=round((time.perf_counter() - start) * 1000, 2)
        )
    except Exception as exc:  # report any failure as "unhealthy"
        logger.warning("readiness_redis_failed", error=str(exc))
        return ComponentHealth(status="error", detail=type(exc).__name__)


@router.get(
    "/health/ready",
    response_model=ReadinessResponse,
    summary="Readiness probe (checks Postgres + Redis)",
    responses={503: {"model": ReadinessResponse}},
)
async def readiness(
    response: Response, settings: SettingsDep, redis: RedisDep
) -> ReadinessResponse:
    checks = {
        "database": await _check_database(),
        "redis": await _check_redis(redis),
    }
    healthy = all(component.status == "ok" for component in checks.values())
    if not healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return ReadinessResponse(
        status="ok" if healthy else "error",
        version=settings.version,
        environment=settings.app_env.value,
        checks=checks,
    )
