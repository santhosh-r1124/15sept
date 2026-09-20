"""payments, refunds, invoices (+ invoice number sequence) - Phase 10

Matches ``app/models/payment.py``. ``payments.matter_id`` is UNIQUE: one payment per matter,
which is also the database-level guard against a double charge.

Revision ID: 0010_payments
Revises: 0009_matter_documents
Create Date: 2026-01-10 00:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010_payments"
down_revision: str | None = "0009_matter_documents"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PAYMENT_STATUS = postgresql.ENUM(
    "SUCCEEDED", "PARTIALLY_REFUNDED", "REFUNDED", name="payment_status", create_type=False
)


def upgrade() -> None:
    bind = op.get_bind()
    _PAYMENT_STATUS.create(bind, checkfirst=False)
    op.execute("CREATE SEQUENCE invoice_number_seq START 1")

    op.create_table(
        "payments",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "matter_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("matters.id", ondelete="CASCADE", name="fk_payments_matter_id_matters"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "payer_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE", name="fk_payments_payer_id_users"),
            nullable=False,
        ),
        sa.Column("amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("refunded_amount", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(3), nullable=False, server_default="INR"),
        sa.Column("status", _PAYMENT_STATUS, nullable=False, server_default="SUCCEEDED"),
        sa.Column("provider", sa.String(30), nullable=False),
        sa.Column("provider_reference", sa.String(100), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.text("clock_timestamp()")
        ),
    )
    op.create_index("ix_payments_payer_id", "payments", ["payer_id"])

    op.create_table(
        "refunds",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "payment_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "payments.id", ondelete="CASCADE", name="fk_refunds_payment_id_payments"
            ),
            nullable=False,
        ),
        sa.Column("amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("provider_reference", sa.String(100), nullable=False),
        sa.Column(
            "initiated_by_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "users.id", ondelete="SET NULL", name="fk_refunds_initiated_by_id_users"
            ),
            nullable=True,
        ),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.text("clock_timestamp()")
        ),
    )
    op.create_index("ix_refunds_payment_id", "refunds", ["payment_id"])

    op.create_table(
        "invoices",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("invoice_number", sa.String(30), nullable=False, unique=True),
        sa.Column(
            "payment_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "payments.id", ondelete="CASCADE", name="fk_invoices_payment_id_payments"
            ),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "matter_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("matters.id", ondelete="CASCADE", name="fk_invoices_matter_id_matters"),
            nullable=False,
        ),
        sa.Column(
            "consumer_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE", name="fk_invoices_consumer_id_users"),
            nullable=False,
        ),
        sa.Column(
            "advocate_profile_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "advocate_profiles.id",
                ondelete="CASCADE",
                name="fk_invoices_advocate_profile_id_advocate_profiles",
            ),
            nullable=False,
        ),
        sa.Column("description", sa.String(300), nullable=False),
        sa.Column("client_name", sa.String(150), nullable=False),
        sa.Column("advocate_name", sa.String(150), nullable=False),
        sa.Column("amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="INR"),
        sa.Column(
            "issued_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("clock_timestamp()"),
        ),
    )
    op.create_index("ix_invoices_consumer_id", "invoices", ["consumer_id"])
    op.create_index("ix_invoices_advocate_profile_id", "invoices", ["advocate_profile_id"])


def downgrade() -> None:
    op.drop_table("invoices")
    op.drop_table("refunds")
    op.drop_table("payments")
    op.execute("DROP SEQUENCE invoice_number_seq")

    bind = op.get_bind()
    _PAYMENT_STATUS.drop(bind, checkfirst=False)
