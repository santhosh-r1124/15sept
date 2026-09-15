"""document_requests (Legal Document Assistant, Phase 6)

Matches ``app/models/document_request.py``. Every row is a successfully
generated draft — see that module's docstring for why there's no
status/error column.

Revision ID: 0007_document_requests
Revises: 0006_risk_level
Create Date: 2026-01-07 00:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007_document_requests"
down_revision: str | None = "0006_risk_level"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Type lifecycle is managed explicitly below (create()/drop()); create_type=False
# stops SQLAlchemy from also trying to (re)create/drop it as a table DDL side effect.
_ASSISTANT_DOCUMENT_TYPE = postgresql.ENUM(
    "RENTAL_AGREEMENT",
    "EMPLOYMENT_AGREEMENT",
    "NDA",
    "AFFIDAVIT",
    "DECLARATION",
    "BUSINESS_AGREEMENT",
    "PARTNERSHIP_DOCUMENT",
    "AUTHORIZATION_LETTER",
    "SERVICE_AGREEMENT",
    "LEGAL_NOTICE",
    "OTHER",
    name="assistant_document_type",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    _ASSISTANT_DOCUMENT_TYPE.create(bind, checkfirst=False)

    op.create_table(
        "document_requests",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "users.id", ondelete="CASCADE", name="fk_document_requests_user_id_users"
            ),
            nullable=True,
        ),
        sa.Column("document_type", _ASSISTANT_DOCUMENT_TYPE, nullable=False),
        sa.Column("state_code", sa.String(2), nullable=True),
        sa.Column("answers", postgresql.JSONB(), nullable=False),
        sa.Column("draft_text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
    )
    op.create_index("ix_document_requests_user_id", "document_requests", ["user_id"])


def downgrade() -> None:
    op.drop_table("document_requests")

    bind = op.get_bind()
    _ASSISTANT_DOCUMENT_TYPE.drop(bind, checkfirst=False)
