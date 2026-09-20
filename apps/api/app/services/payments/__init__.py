"""Payment provider abstraction (Phase 8 stub; the real gateway lands in Phase 10).

The matter flow (booking -> **payment** -> consultation -> closed) needs *something* to
charge, but which Indian payment gateway to use is a real, paid, regulated decision that
belongs to the project owner (docs/adr/0010, and the standing "no paid services without
asking" rule). So Phase 8 depends only on the ``PaymentProvider`` interface and ships a
free ``MockPaymentProvider`` that always succeeds — clearly marked, and refused outright in
production so a mock can never take "payments" from real users.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from app.core.config import Settings
from app.core.errors import ServiceUnavailableError


@dataclass(frozen=True, slots=True)
class PaymentResult:
    reference: str
    amount: Decimal
    currency: str = "INR"


class PaymentProvider(Protocol):
    name: str

    async def charge(
        self, *, amount: Decimal, description: str, idempotency_key: str
    ) -> PaymentResult: ...


class MockPaymentProvider:
    """Always succeeds. Development/test only — see ``get_payment_provider``."""

    name = "mock"

    async def charge(
        self, *, amount: Decimal, description: str, idempotency_key: str
    ) -> PaymentResult:
        return PaymentResult(reference=f"mock_{idempotency_key}", amount=amount)


def get_payment_provider(settings: Settings) -> PaymentProvider:
    if settings.payment_provider == "mock":
        if settings.app_env.is_production:
            raise ServiceUnavailableError(
                "Payments aren't configured yet (the mock provider is disabled in production).",
                code="payments_not_configured",
            )
        return MockPaymentProvider()
    raise ServiceUnavailableError(
        f"Unknown payment provider {settings.payment_provider!r}.", code="payments_not_configured"
    )
