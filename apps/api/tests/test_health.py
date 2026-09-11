"""Smoke tests for the Phase 0 skeleton."""

from __future__ import annotations

from httpx import AsyncClient


async def test_liveness_ok(client: AsyncClient) -> None:
    resp = await client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["service"]
    assert body["version"]


async def test_root_ok(client: AsyncClient) -> None:
    resp = await client.get("/")
    assert resp.status_code == 200
    assert resp.json()["health"] == "/health"


async def test_meta_ok(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/meta")
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"]
    assert body["environment"] == "development"


async def test_request_id_header_present(client: AsyncClient) -> None:
    resp = await client.get("/health")
    assert resp.headers.get("x-request-id")


async def test_unknown_route_uses_error_envelope(client: AsyncClient) -> None:
    resp = await client.get("/does-not-exist")
    assert resp.status_code == 404
    body = resp.json()
    assert body["error"]["code"] == "not_found"
    assert body["error"]["request_id"]


async def test_readiness_shape(client: AsyncClient) -> None:
    """Readiness returns 200 (deps up, e.g. in CI) or 503 (deps down), with a
    consistent body either way."""
    resp = await client.get("/health/ready")
    assert resp.status_code in (200, 503)
    body = resp.json()
    assert set(body["checks"]) == {"database", "redis"}
    assert body["environment"] == "development"
