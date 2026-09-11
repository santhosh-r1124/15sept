"""ORM models.

Import every model module here so that ``Base.metadata`` is complete for
Alembic autogenerate. Models are added from Phase 1 (authentication) onward.

Example (Phase 1)::

    from app.models.user import User  # noqa: F401
"""

from __future__ import annotations

from app.db.base import Base

__all__ = ["Base"]
