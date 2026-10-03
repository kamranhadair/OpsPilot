"""anomaly detection idempotency constraint

Adds a unique constraint on ``anomalies (metric_snapshot_id, detector_key)`` so
repeating detection over the same metric snapshot with the same versioned
detector reuses the existing anomaly instead of duplicating it. No code wrote
anomalies before this revision, so the constraint cannot be violated by
existing rows.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-03 22:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint(
        op.f("uq_anomalies_snapshot_detector"),
        "anomalies",
        ["metric_snapshot_id", "detector_key"],
    )


def downgrade() -> None:
    op.drop_constraint(op.f("uq_anomalies_snapshot_detector"), "anomalies", type_="unique")
