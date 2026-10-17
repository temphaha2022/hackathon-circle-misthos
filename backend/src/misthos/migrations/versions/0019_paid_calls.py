"""The ledger of paid x402 calls (#201).

The edge settles a buyer's payment only after the core has answered the call it paid
for, and then writes one row here, so the books can be reconciled with Circle Gateway.
Appended, never edited.

Revision ID: 0019
Revises: 0018
Create Date: 2026-10-17
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "paid_calls",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("route", sa.String(length=64), nullable=False),
        sa.Column("request_digest", sa.String(length=64), nullable=False),
        sa.Column("payer", sa.String(length=64), nullable=False),
        sa.Column("amount_base_units", sa.BigInteger(), nullable=False),
        sa.Column("network", sa.String(length=32), nullable=False),
        sa.Column("asset", sa.String(length=64), nullable=False),
        sa.Column("transaction", sa.String(length=128), nullable=False),
        sa.Column("ref", sa.String(length=64), nullable=True),
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_paid_calls")),
        sa.UniqueConstraint(
            "route",
            "request_digest",
            "transaction",
            name=op.f("uq_paid_calls_route_request_digest_transaction"),
        ),
    )
    op.create_index("ix_paid_calls_settled", "paid_calls", ["settled_at"])


def downgrade() -> None:
    op.drop_index("ix_paid_calls_settled", table_name="paid_calls")
    op.drop_table("paid_calls")
