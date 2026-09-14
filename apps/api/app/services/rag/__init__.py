"""Production RAG (Phase 4): hybrid retrieval over `legal_chunks`.

See `retrieval.py` for the hybrid search + Reciprocal Rank Fusion
implementation, and `app.services.llm.generate_grounded_answer` for how
retrieved chunks are turned into a cited answer.
"""

from __future__ import annotations
