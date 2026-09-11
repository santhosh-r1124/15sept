"""Unit tests for app.services.llm — no database, no real network calls."""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.core.errors import ServiceUnavailableError
from app.services import llm

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


# ---------------------------------------------------------------------------
# Not configured (no ANTHROPIC_API_KEY) — the "build now, key later" path.
# ---------------------------------------------------------------------------


async def test_classify_query_raises_when_not_configured() -> None:
    with pytest.raises(ServiceUnavailableError) as exc_info:
        await llm.classify_query("hello", settings=UNCONFIGURED)
    assert exc_info.value.code == "llm_not_configured"
    assert exc_info.value.status_code == 503


async def test_generate_answer_raises_when_not_configured() -> None:
    with pytest.raises(ServiceUnavailableError) as exc_info:
        await llm.generate_answer("hello", history=[], settings=UNCONFIGURED)
    assert exc_info.value.code == "llm_not_configured"


# ---------------------------------------------------------------------------
# Response parsing (client swapped for a fake — no network, no API key needed)
# ---------------------------------------------------------------------------


async def test_classify_query_parses_tool_response(monkeypatch: pytest.MonkeyPatch) -> None:
    response = _FakeResponse(
        [
            _FakeToolUseBlock(
                "classify_legal_query",
                {"category": "IT_LAW", "jurisdiction_scope": "CENTRAL", "is_out_of_scope": False},
            )
        ]
    )
    monkeypatch.setattr(llm, "_client", lambda settings: _FakeClient(response))

    result = await llm.classify_query("What is the IT Act, 2000?", settings=CONFIGURED)

    assert result.category == "IT_LAW"
    assert result.jurisdiction_scope == "CENTRAL"
    assert result.is_out_of_scope is False


async def test_classify_query_falls_back_on_invalid_category(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = _FakeResponse(
        [
            _FakeToolUseBlock(
                "classify_legal_query",
                {
                    "category": "NOT_A_REAL_CATEGORY",
                    "jurisdiction_scope": "MARS",
                    "is_out_of_scope": False,
                },
            )
        ]
    )
    monkeypatch.setattr(llm, "_client", lambda settings: _FakeClient(response))

    result = await llm.classify_query("gibberish", settings=CONFIGURED)

    assert result.category == "OUT_OF_SCOPE"
    assert result.jurisdiction_scope == "UNKNOWN"


async def test_classify_query_fails_safe_when_tool_not_called(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = _FakeResponse([_FakeTextBlock("I'd rather just chat.")])
    monkeypatch.setattr(llm, "_client", lambda settings: _FakeClient(response))

    result = await llm.classify_query("hi", settings=CONFIGURED)

    assert result.is_out_of_scope is True


async def test_classify_query_wraps_transport_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(llm, "_client", lambda settings: _RaisingClient())
    with pytest.raises(ServiceUnavailableError) as exc_info:
        await llm.classify_query("hi", settings=CONFIGURED)
    assert exc_info.value.code == "llm_error"


async def test_generate_answer_joins_text_blocks(monkeypatch: pytest.MonkeyPatch) -> None:
    response = _FakeResponse([_FakeTextBlock("Hello "), _FakeTextBlock("there.")])
    monkeypatch.setattr(llm, "_client", lambda settings: _FakeClient(response))

    text = await llm.generate_answer("hi", history=[], settings=CONFIGURED)

    assert text == "Hello \nthere."


async def test_generate_answer_has_a_fallback_for_empty_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(llm, "_client", lambda settings: _FakeClient(_FakeResponse([])))

    text = await llm.generate_answer("hi", history=[], settings=CONFIGURED)

    assert text  # non-empty fallback copy, not a blank string
