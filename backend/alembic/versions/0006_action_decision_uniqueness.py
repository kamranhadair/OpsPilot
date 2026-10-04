"""one human decision and one execution per action

Replaces the plain ``action_id`` indexes on ``approvals`` and ``action_executions``
with unique constraints (Spec 12). A concurrent double approval or double execution
then fails in the database instead of recording two decisions or two mock
investigations. ``failed`` is terminal in the V1 state machine, so one execution row per
action is the complete history. No code wrote either table before this revision.

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-04 15:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# (table, old plain index, new unique constraint)
_TABLES = (
    ("approvals", "ix_approvals_action_id", "uq_approvals_action_id"),
    ("action_executions", "ix_action_executions_action_id", "uq_action_executions_action_id"),
)


def upgrade() -> None:
    for table, index, constraint in _TABLES:
        op.drop_index(index, table_name=table)
        op.create_unique_constraint(op.f(constraint), table, ["action_id"])


def downgrade() -> None:
    for table, index, constraint in _TABLES:
        op.drop_constraint(op.f(constraint), table, type_="unique")
        op.create_index(index, table, ["action_id"], unique=False)
