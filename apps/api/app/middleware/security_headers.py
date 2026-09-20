"""Response hardening headers for the API (Phase 13).

Pure ASGI (not ``BaseHTTPMiddleware``) so streaming responses, file downloads and WebSockets are
untouched. Headers a route already set (the invoice page's own CSP, a download's ``no-store``) win.

The API only serves JSON, downloads and the invoice page - never a page that should be framed or
that needs the camera - so the policy is strict. ``Strict-Transport-Security`` is sent in production
only: browsers ignore it over plain HTTP, and pinning HTTPS on a dev host would be a nuisance.
"""

from __future__ import annotations

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

_BASE: dict[str, str] = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=()",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-site",
}
_HSTS = "max-age=63072000; includeSubDomains"


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp, *, production: bool = False) -> None:
        self.app = app
        self.headers = dict(_BASE)
        if production:
            self.headers["Strict-Transport-Security"] = _HSTS

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for name, value in self.headers.items():
                    if name not in headers:
                        headers[name] = value
            await send(message)

        await self.app(scope, receive, send_with_headers)
