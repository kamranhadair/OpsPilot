"""anomaly contributor idempotency constraint

Adds a unique constraint on ``anomaly_contributors (anomaly_id, dimension_key,
segment_value)`` so repeating contributor analysis for an anomaly reuses the
stored segments instead of duplicating them. No code wrote contributors before
this revision, so the constraint cannot be violated by existing rows.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-04 09:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CONSTRAINT = "uq_anomaly_contributors_anomaly_dimension_segment"


def upgrade() -> None:
    op.create_unique_constraint(
        op.f(CONSTRAINT),
        "anomaly_contributors",
        ["anomaly_id", "dimension_key", "segment_value"],
    )


def downgrade() -> None:
    op.drop_constraint(op.f(CONSTRAINT), "anomaly_contributors", type_="unique")
