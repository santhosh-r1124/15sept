"""Unit tests for app.services.risk_engine — pure logic, no DB, no network."""

from __future__ import annotations

import pytest

from app.services.risk_engine import requires_advocate_recommendation


@pytest.mark.parametrize(
    ("risk_level", "expected"),
    [
        ("LOW", False),
        ("MEDIUM", False),
        ("HIGH", True),
        ("CRITICAL", True),
    ],
)
def test_requires_advocate_recommendation(risk_level: str, expected: bool) -> None:
    assert requires_advocate_recommendation(risk_level) is expected
