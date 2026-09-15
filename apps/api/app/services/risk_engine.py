"""Legal risk engine (Phase 5): decides product behaviour from a risk level.

Scores are assigned by `app.services.legal_classifier` (part of the same
Claude call as category/jurisdiction); this module only decides what to do
with the result — kept separate so "how risky is this" and "what do we do
about it" can change independently::

    LOW       general legal education           -> AI information
    MEDIUM    document guidance                 -> AI information + caveats
    HIGH      specific dispute / consequences   -> AI information + advocate recommendation
    CRITICAL  active litigation, criminal,      -> advocate strongly recommended;
              regulatory action, major exposure    AI stays general
"""

from __future__ import annotations

# Mirrors packages/shared/src/legal.ts::requiresAdvocate — keep in sync.
_ADVOCATE_RISK_LEVELS = frozenset({"HIGH", "CRITICAL"})


def requires_advocate_recommendation(risk_level: str) -> bool:
    """HIGH/CRITICAL replies must append ADVOCATE_RECOMMENDATION_MESSAGE
    (app.core.legal_text) — the caller decides where/how, this just decides
    whether.
    """
    return risk_level in _ADVOCATE_RISK_LEVELS
