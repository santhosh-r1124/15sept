"""Response hardening headers (Phase 13). No database."""

from __future__ import annotations

from httpx import ASGITransport, AsyncClient
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route

from app.core.config import Settings
from app.main import create_app
from app.middleware.security_headers import SecurityHeadersMiddleware


def _headers(response: object) -> dict[str, str]:
    return {k.lower(): v for k, v in response.headers.items()}  # type: ignore[attr-defined]


async def test_every_response_carries_the_hardening_headers(client: AsyncClient) -> None:
    resp = await client.get("/health")

    headers = _headers(resp)
    assert headers["x-content-type-options"] == "nosniff"
    assert headers["x-frame-options"] == "DENY"
    assert headers["referrer-policy"] == "no-referrer"
    assert headers["cross-origin-opener-policy"] == "same-origin"
    assert "camera=()" in headers["permissions-policy"]  # the API never needs the camera
    assert "strict-transport-security" not in headers  # HTTP in development


async def test_error_responses_and_preflights_have_them_too(client: AsyncClient) -> None:
    not_found = await client.get("/api/v1/nope")
    unauthorised = await client.get("/api/v1/users/me")
    preflight = await client.options(
        "/api/v1/users/me",
        headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "GET"},
    )

    for resp in (not_found, unauthorised, preflight):
        assert _headers(resp)["x-content-type-options"] == "nosniff"
    assert not_found.status_code == 404
    assert unauthorised.status_code == 401


async def test_production_adds_hsts() -> None:
    app = create_app(Settings(_env_file=None, app_env="production"))  # type: ignore[call-arg]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        headers = _headers(await client.get("/health"))

    assert headers["strict-transport-security"].startswith("max-age=")


async def test_a_header_the_route_set_itself_is_not_overwritten() -> None:
    async def page(_request: object) -> PlainTextResponse:
        return PlainTextResponse(
            "ok",
            headers={
                "X-Frame-Options": "SAMEORIGIN",
                "Content-Security-Policy": "default-src 'none'",
            },
        )

    app = SecurityHeadersMiddleware(Starlette(routes=[Route("/", page)]))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        headers = _headers(await client.get("/"))

    assert headers["x-frame-options"] == "SAMEORIGIN"  # the route's own choice wins
    assert headers["content-security-policy"] == "default-src 'none'"
    assert headers["x-content-type-options"] == "nosniff"  # everything else is filled in


async def test_the_invoice_page_keeps_its_own_strict_policy(client: AsyncClient) -> None:
    # Guards the interaction that matters: the middleware must not weaken a route's CSP. (The
    # route itself is exercised against a database in test_payments.py.)
    async def invoice(_request: object) -> PlainTextResponse:
        return PlainTextResponse(
            "<html></html>",
            media_type="text/html",
            headers={"Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'"},
        )

    app = SecurityHeadersMiddleware(Starlette(routes=[Route("/invoice", invoice)]))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        headers = _headers(await c.get("/invoice"))

    assert headers["content-security-policy"] == "default-src 'none'; style-src 'unsafe-inline'"
