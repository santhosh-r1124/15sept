"""chat_messages.risk_level (+ index)

Phase 5 — risk engine. Matches ``app/models/chat.py::ChatMessage.risk_level``.
Indexed for the Phase 12 admin "high-risk query review" queue.

Revision ID: 0006_risk_level
Revises: 0005_rag_grounding
Create Date: 2026-01-06 00:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_risk_level"
down_revision: str | None = "0005_rag_grounding"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("chat_messages", sa.Column("risk_level", sa.String(10), nullable=True))
    op.create_index("ix_chat_messages_risk_level", "chat_messages", ["risk_level"])


def downgrade() -> None:
    op.drop_index("ix_chat_messages_risk_level", table_name="chat_messages")
    op.drop_column("chat_messages", "risk_level")
