"""metric snapshot analysis signature

Adds a deterministic analysis signature to ``metric_snapshots`` so repeating the
same metric computation reuses the existing snapshot instead of duplicating it.
No code writes snapshots before this revision, so the NOT NULL column is safe.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-03 21:00:00.000000

"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "metric_snapshots",
        sa.Column("analysis_signature", sa.String(length=64), nullable=False),
    )
    op.create_unique_constraint(
        op.f("uq_metric_snapshots_analysis_signature"),
        "metric_snapshots",
        ["analysis_signature"],
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("uq_metric_snapshots_analysis_signature"), "metric_snapshots", type_="unique"
    )
    op.drop_column("metric_snapshots", "analysis_signature")
