"""Unit tests for app.services.document_assistant.questions — pure logic,
no DB, no network.
"""

from __future__ import annotations

import pytest

from app.models.document_request import AssistantDocumentType
from app.services.document_assistant.questions import (
    QUESTION_SETS,
    missing_required_answers,
    questions_for,
)


@pytest.mark.parametrize("document_type", list(AssistantDocumentType))
def test_every_document_type_has_a_question_set(document_type: AssistantDocumentType) -> None:
    questions = questions_for(document_type)
    assert questions, f"{document_type} has no questions"


@pytest.mark.parametrize("document_type", list(AssistantDocumentType))
def test_every_question_set_asks_for_state(document_type: AssistantDocumentType) -> None:
    keys = {q.key for q in questions_for(document_type)}
    assert "state_code" in keys


@pytest.mark.parametrize("document_type", list(AssistantDocumentType))
def test_question_keys_are_unique_within_a_set(document_type: AssistantDocumentType) -> None:
    keys = [q.key for q in questions_for(document_type)]
    assert len(keys) == len(set(keys))


def test_question_sets_cover_every_enum_member() -> None:
    assert set(QUESTION_SETS) == set(AssistantDocumentType)


def test_missing_required_answers_reports_unanswered_required_fields() -> None:
    missing = missing_required_answers(AssistantDocumentType.AFFIDAVIT, {})
    assert "purpose" in missing
    assert "full_name" in missing
    # supporting_documents is optional — never reported as missing.
    assert "supporting_documents" not in missing


def test_missing_required_answers_treats_blank_strings_as_missing() -> None:
    missing = missing_required_answers(
        AssistantDocumentType.AFFIDAVIT,
        {
            "purpose": "   ",
            "full_name": "Jane Doe",
            "address": "123 Main St",
            "state_code": "MH",
            "facts_to_declare": "The facts.",
        },
    )
    assert missing == ["purpose"]


def test_missing_required_answers_empty_when_all_required_fields_present() -> None:
    missing = missing_required_answers(
        AssistantDocumentType.AFFIDAVIT,
        {
            "purpose": "Name change",
            "full_name": "Jane Doe",
            "address": "123 Main St",
            "state_code": "MH",
            "facts_to_declare": "The facts.",
        },
    )
    assert missing == []
