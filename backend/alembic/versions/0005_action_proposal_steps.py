"""action proposal steps and one-proposal-per-brief

Adds ``investigation_steps_json`` to ``proposed_actions`` for the Spec 11 proposal
contract and replaces the plain ``brief_id`` index with a unique constraint: V1 allows
one proposal per brief, and the constraint makes concurrent duplicate requests fail
instead of creating two pending approvals. No code wrote proposals before this
revision, so the constraint cannot be violated by existing rows.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-04 12:00:00.000000

"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "proposed_actions"
CONSTRAINT = "uq_proposed_actions_brief_id"
INDEX = "ix_proposed_actions_brief_id"


def upgrade() -> None:
    op.add_column(
        TABLE,
        sa.Column(
            "investigation_steps_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.drop_index(op.f(INDEX), table_name=TABLE)
    op.create_unique_constraint(op.f(CONSTRAINT), TABLE, ["brief_id"])


def downgrade() -> None:
    op.drop_constraint(op.f(CONSTRAINT), TABLE, type_="unique")
    op.create_index(op.f(INDEX), TABLE, ["brief_id"], unique=False)
    op.drop_column(TABLE, "investigation_steps_json")
