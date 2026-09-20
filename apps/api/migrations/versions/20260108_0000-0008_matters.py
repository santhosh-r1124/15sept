"""matters + matter_messages (On-Demand Consultation, Phase 8)

Matches ``app/models/matter.py``.

Revision ID: 0008_matters
Revises: 0007_document_requests
Create Date: 2026-01-08 00:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008_matters"
down_revision: str | None = "0007_document_requests"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Type lifecycle is managed explicitly below; create_type=False stops SQLAlchemy from also
# trying to (re)create/drop the type as a table DDL side effect.
_SERVICE_TYPE = postgresql.ENUM(
    "CONSULTATION",
    "DOCUMENT_DRAFT",
    "DOCUMENT_REVIEW",
    "DOCUMENT_MODIFICATION",
    "AFFIDAVIT_ASSISTANCE",
    "AGREEMENT_REVIEW",
    name="matter_service_type",
    create_type=False,
)
_STATUS = postgresql.ENUM(
    "REQUESTED",
    "ACCEPTED",
    "PAID",
    "SCHEDULED",
    "CLOSED",
    "REJECTED",
    "CANCELLED",
    name="matter_status",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    _SERVICE_TYPE.create(bind, checkfirst=False)
    _STATUS.create(bind, checkfirst=False)

    op.create_table(
        "matters",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "consumer_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE", name="fk_matters_consumer_id_users"),
            nullable=False,
        ),
        sa.Column(
            "advocate_profile_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "advocate_profiles.id",
                ondelete="CASCADE",
                name="fk_matters_advocate_profile_id_advocate_profiles",
            ),
            nullable=False,
        ),
        sa.Column("service_type", _SERVICE_TYPE, nullable=False),
        sa.Column("consultation_minutes", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("requirement", sa.Text(), nullable=False),
        sa.Column("preferred_language", sa.String(50), nullable=True),
        sa.Column("status", _STATUS, nullable=False, server_default="REQUESTED"),
        sa.Column("quoted_fee", sa.Numeric(10, 2), nullable=True),
        sa.Column("decision_note", sa.Text(), nullable=True),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("payment_reference", sa.String(100), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
    )
    op.create_index("ix_matters_consumer_id", "matters", ["consumer_id"])
    op.create_index("ix_matters_advocate_profile_id", "matters", ["advocate_profile_id"])
    op.create_index("ix_matters_status", "matters", ["status"])

    op.create_table(
        "matter_messages",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "matter_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "matters.id", ondelete="CASCADE", name="fk_matter_messages_matter_id_matters"
            ),
            nullable=False,
        ),
        sa.Column(
            "sender_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "users.id", ondelete="CASCADE", name="fk_matter_messages_sender_id_users"
            ),
            nullable=False,
        ),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.text("clock_timestamp()")
        ),
    )
    op.create_index("ix_matter_messages_matter_id", "matter_messages", ["matter_id"])


def downgrade() -> None:
    op.drop_table("matter_messages")
    op.drop_table("matters")

    bind = op.get_bind()
    _STATUS.drop(bind, checkfirst=False)
    _SERVICE_TYPE.drop(bind, checkfirst=False)
