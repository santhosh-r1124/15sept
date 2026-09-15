"""Shared Anthropic client construction — used by both `legal_classifier.py`
and `llm.py` so the "not configured" check/error lives in exactly one place.
"""

from __future__ import annotations

import anthropic

from app.core.config import Settings
from app.core.errors import ServiceUnavailableError


def get_client(settings: Settings) -> anthropic.AsyncAnthropic:
    if not settings.anthropic_api_key:
        raise ServiceUnavailableError(
            "The legal assistant isn't configured yet (missing ANTHROPIC_API_KEY).",
            code="llm_not_configured",
        )
    return anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
