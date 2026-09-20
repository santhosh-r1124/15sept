"""Payment provider abstraction (mock until the owner picks a gateway - Phase 8/10).

The booking flow needs *something* to charge and refund, but which Indian payment gateway to
use is a paid, regulated decision that belongs to the project owner (docs/adr/0010, 0012, and
the standing "no paid services without asking" rule). So everything above this module - the
ledger, invoices, refunds, earnings - depends only on the ``PaymentProvider`` protocol, and the
only implementation shipped is a free ``MockPaymentProvider`` that always succeeds. It is
refused outright in production, so a mock can never take "payments" from real users.

Wiring a real gateway means adding one class that implements ``charge`` and ``refund`` (plus
webhook signature verification if the gateway is asynchronous) and registering it in
``get_payment_provider`` - nothing else changes.
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


@dataclass(frozen=True, slots=True)
class RefundResult:
    reference: str
    amount: Decimal


class PaymentProvider(Protocol):
    name: str

    async def charge(
        self, *, amount: Decimal, description: str, idempotency_key: str
    ) -> PaymentResult: ...

    async def refund(
        self, *, payment_reference: str, amount: Decimal, idempotency_key: str
    ) -> RefundResult: ...


class MockPaymentProvider:
    """Always succeeds. Development/test only - see ``get_payment_provider``."""

    name = "mock"

    async def charge(
        self, *, amount: Decimal, description: str, idempotency_key: str
    ) -> PaymentResult:
        return PaymentResult(reference=f"mock_{idempotency_key}", amount=amount)

    async def refund(
        self, *, payment_reference: str, amount: Decimal, idempotency_key: str
    ) -> RefundResult:
        return RefundResult(reference=f"mockrf_{idempotency_key}", amount=amount)


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
