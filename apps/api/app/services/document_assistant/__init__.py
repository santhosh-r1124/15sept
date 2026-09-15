"""Legal Document Assistant (Phase 6, FRD §7).

No ``services/document-assistant`` stub exists from Phase 0 (unlike
``services/rag``, ``services/legal-classifier``, ...) — the architecture doc
never anticipated this as its own service, so there's no prior commitment to
reconcile. Logic lives directly in ``apps/api`` from the start, for the same
Docker-build-context reason ``docs/adr/0004`` gives for the others.
"""

from __future__ import annotations

__all__: list[str] = []
