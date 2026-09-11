"""Legal risk engine (Phase 5).

Scores each query:

    LOW       general legal education           -> AI information
    MEDIUM    document guidance                 -> AI information + caveats
    HIGH      specific dispute / consequences   -> AI information + advocate recommendation
    CRITICAL  active litigation, criminal,      -> advocate strongly recommended;
              regulatory action, major exposure    AI stays general

HIGH / CRITICAL responses must append ``ADVOCATE_RECOMMENDATION_MESSAGE``
(``@legal-platform/shared``).
"""

__all__: list[str] = []
