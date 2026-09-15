"""Unit tests for app.services.document_assistant.generation — no database,
no real network calls.
"""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.core.errors import ServiceUnavailableError
from app.models.document_request import AssistantDocumentType
from app.services.document_assistant import generation

UNCONFIGURED = Settings(anthropic_api_key=None)
CONFIGURED = Settings(anthropic_api_key="fake-key-for-tests")

SAMPLE_ANSWERS = {
    "purpose": "Name change",
    "full_name": "Jane Doe",
    "address": "123 Main St, Pune",
    "state_code": "MH",
    "facts_to_declare": "I have changed my name from X to Y.",
}


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


async def test_generate_draft_raises_when_not_configured() -> None:
    with pytest.raises(ServiceUnavailableError) as exc_info:
        await generation.generate_draft(
            AssistantDocumentType.AFFIDAVIT, answers=SAMPLE_ANSWERS, settings=UNCONFIGURED
        )
    assert exc_info.value.code == "llm_not_configured"


async def test_generate_draft_returns_text(monkeypatch: pytest.MonkeyPatch) -> None:
    response = _FakeResponse([_FakeTextBlock("DRAFT AFFIDAVIT\n\n...")])
    monkeypatch.setattr(generation, "get_client", lambda settings: _FakeClient(response))

    text = await generation.generate_draft(
        AssistantDocumentType.AFFIDAVIT, answers=SAMPLE_ANSWERS, settings=CONFIGURED
    )

    assert text == "DRAFT AFFIDAVIT\n\n..."


async def test_generate_draft_raises_on_empty_response(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(generation, "get_client", lambda settings: _FakeClient(_FakeResponse([])))

    with pytest.raises(ServiceUnavailableError) as exc_info:
        await generation.generate_draft(
            AssistantDocumentType.AFFIDAVIT, answers=SAMPLE_ANSWERS, settings=CONFIGURED
        )
    assert exc_info.value.code == "llm_error"


async def test_generate_draft_wraps_transport_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(generation, "get_client", lambda settings: _RaisingClient())

    with pytest.raises(ServiceUnavailableError) as exc_info:
        await generation.generate_draft(
            AssistantDocumentType.AFFIDAVIT, answers=SAMPLE_ANSWERS, settings=CONFIGURED
        )
    assert exc_info.value.code == "llm_error"


async def test_generate_draft_only_includes_answered_questions_in_the_prompt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class _CapturingMessages:
        async def create(self, **kwargs: object) -> object:
            captured.update(kwargs)
            return _FakeResponse([_FakeTextBlock("draft")])

    class _CapturingClient:
        def __init__(self) -> None:
            self.messages = _CapturingMessages()

    monkeypatch.setattr(generation, "get_client", lambda settings: _CapturingClient())

    await generation.generate_draft(
        AssistantDocumentType.AFFIDAVIT,
        answers={"full_name": "Jane Doe", "supporting_documents": ""},
        settings=CONFIGURED,
    )

    messages = captured["messages"]
    assert isinstance(messages, list)
    prompt = messages[0]["content"]
    assert "Jane Doe" in prompt
    # Blank/unanswered questions are omitted, not sent as empty lines.
    assert "supporting documents" not in prompt.lower()
