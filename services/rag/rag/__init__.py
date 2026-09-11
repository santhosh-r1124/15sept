"""RAG engine (Phase 4).

Pipeline::

    query
      -> intent classification        (services.legal_classifier)
      -> jurisdiction detection
      -> query rewriting
      -> hybrid search (keyword + vector)
      -> reranking
      -> context selection
      -> Claude
      -> legal guardrails
      -> answer + citations

Hard rule: if retrieval yields insufficient grounded evidence, DO NOT GUESS —
return the "insufficient verified information" message
(``@legal-platform/shared`` → ``INSUFFICIENT_EVIDENCE_MESSAGE``).
"""

__all__: list[str] = []
