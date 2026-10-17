"""Widen the screening outcome so `unavailable` fits.

`ScreeningOutcome.UNAVAILABLE` is eleven characters and the column was eight, so
recording a failed screening raised `StringDataRightTruncation`. That turned every
funding and payout into a 500 whenever the list could not be read, which is exactly
when the check has to be recorded and the money held.

Revision ID: 0022
Revises: 0021
Create Date: 2026-10-18
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Batch mode is the same ALTER on Postgres and the table rebuild SQLite needs.
    with op.batch_alter_table("screenings") as batch:
        batch.alter_column(
            "outcome",
            existing_type=sa.String(8),
            type_=sa.String(16),
            existing_nullable=False,
        )


def downgrade() -> None:
    """Left wide: rows already holding `unavailable` would not fit eight characters,
    and nothing reads the outcome back at that width."""
