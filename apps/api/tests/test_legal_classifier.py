"""Unit tests for app.services.legal_classifier — no database, no real network
calls. Classification + risk scoring share one forced tool call (Phase 5); see
docs/adr/0008-risk-scoring.md for why they weren't split into two.
"""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.core.errors import ServiceUnavailableError
from app.services import legal_classifier

UNCONFIGURED = Settings(anthropic_api_key=None)
CONFIGURED = Settings(anthropic_api_key="fake-key-for-tests")


class _FakeToolUseBlock:
    type = "tool_use"

    def __init__(self, name: str, input_data: dict[str, object]) -> None:
        self.name = name
        self.input = input_data


class _FakeTextBlock:
    type = "text"

    def __init__(self, text: str) -> None:
        self.text = text


class _FakeMessages:
    def __init__(self, response: object) -> None:
        self._response = response

    async def create(self, **_kwargs: object) -> object:
        return self._response


class _FakeClient:
    def __init__(self, response: object) -> None:
        self.messages = _FakeMessages(response)


class _FakeResponse:
    def __init__(self, content: list[object]) -> None:
        self.content = content


class _RaisingMessages:
    async def create(self, **_kwargs: object) -> object:
        raise RuntimeError("simulated transport failure")


class _RaisingClient:
    def __init__(self) -> None:
        self.messages = _RaisingMessages()


def _tool_response(**overrides: object) -> _FakeResponse:
    data: dict[str, object] = {
        "category": "IT_LAW",
        "jurisdiction_scope": "CENTRAL",
        "risk_level": "LOW",
        "is_out_of_scope": False,
        **overrides,
    }
    return _FakeResponse([_FakeToolUseBlock("classify_legal_query", data)])


# ---------------------------------------------------------------------------
# Not configured (no ANTHROPIC_API_KEY) — the "build now, key later" path.
# ---------------------------------------------------------------------------


async def test_classify_query_raises_when_not_configured() -> None:
    with pytest.raises(ServiceUnavailableError) as exc_info:
        await legal_classifier.classify_query("hello", settings=UNCONFIGURED)
    assert exc_info.value.code == "llm_not_configured"
    assert exc_info.value.status_code == 503


# ---------------------------------------------------------------------------
# Response parsing (client swapped for a fake — no network, no API key needed)
# ---------------------------------------------------------------------------


async def test_classify_query_parses_tool_response(monkeypatch: pytest.MonkeyPatch) -> None:
    response = _tool_response(category="IT_LAW", jurisdiction_scope="CENTRAL", risk_level="LOW")
    monkeypatch.setattr(legal_classifier, "get_client", lambda settings: _FakeClient(response))

    result = await legal_classifier.classify_query("What is the IT Act, 2000?", settings=CONFIGURED)

    assert result.category == "IT_LAW"
    assert result.jurisdiction_scope == "CENTRAL"
    assert result.risk_level == "LOW"
    assert result.is_out_of_scope is False


async def test_classify_query_parses_high_risk(monkeypatch: pytest.MonkeyPatch) -> None:
    response = _tool_response(
        category="ADVOCATE_REQUIRED", risk_level="CRITICAL", jurisdiction_scope="COURT"
    )
    monkeypatch.setattr(legal_classifier, "get_client", lambda settings: _FakeClient(response))

    result = await legal_classifier.classify_query("I've been arrested", settings=CONFIGURED)

    assert result.risk_level == "CRITICAL"


async def test_classify_query_falls_back_on_invalid_enum_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = _tool_response(
        category="NOT_A_REAL_CATEGORY", jurisdiction_scope="MARS", risk_level="EXTREME"
    )
    monkeypatch.setattr(legal_classifier, "get_client", lambda settings: _FakeClient(response))

    result = await legal_classifier.classify_query("gibberish", settings=CONFIGURED)

    assert result.category == "OUT_OF_SCOPE"
    assert result.jurisdiction_scope == "UNKNOWN"
    # No "unknown" risk value exists — falls back to the conservative side
    # (recommend an advocate) rather than silently dropping the signal.
    assert result.risk_level == "HIGH"


async def test_classify_query_fails_safe_when_tool_not_called(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = _FakeResponse([_FakeTextBlock("I'd rather just chat.")])
    monkeypatch.setattr(legal_classifier, "get_client", lambda settings: _FakeClient(response))

    result = await legal_classifier.classify_query("hi", settings=CONFIGURED)

    assert result.is_out_of_scope is True
    assert result.risk_level == "HIGH"


async def test_classify_query_wraps_transport_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(legal_classifier, "get_client", lambda settings: _RaisingClient())
    with pytest.raises(ServiceUnavailableError) as exc_info:
        await legal_classifier.classify_query("hi", settings=CONFIGURED)
    assert exc_info.value.code == "llm_error"
