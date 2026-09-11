"""initial: enable Postgres extensions

Enables the extensions the platform relies on:
  * vector    — pgvector, embeddings storage / similarity search (Phase 3+)
  * pgcrypto  — gen_random_uuid() for UUID primary keys (Phase 1+)
  * pg_trgm   — trigram indexes for hybrid keyword search (Phase 4)

Revision ID: 0001_initial_extensions
Revises:
Create Date: 2026-01-01 00:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0001_initial_extensions"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_EXTENSIONS = ("vector", "pgcrypto", "pg_trgm")


def upgrade() -> None:
    for ext in _EXTENSIONS:
        op.execute(f'CREATE EXTENSION IF NOT EXISTS "{ext}"')


def downgrade() -> None:
    for ext in reversed(_EXTENSIONS):
        op.execute(f'DROP EXTENSION IF EXISTS "{ext}"')
