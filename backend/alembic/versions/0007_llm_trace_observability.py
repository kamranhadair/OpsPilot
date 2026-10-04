"""llm trace observability context and read-path indexes

Adds the action and request context Spec 14 records on every model call, plus indexes
for the system trace list (newest first, optionally by operation) and the time-window
summary. Purely additive: downgrade drops the new columns and indexes only.

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-04 18:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("llm_traces", sa.Column("action_id", sa.Integer(), nullable=True))
    op.add_column("llm_traces", sa.Column("request_id", sa.String(length=64), nullable=True))
    op.create_foreign_key(
        op.f("fk_llm_traces_action_id_proposed_actions"),
        "llm_traces",
        "proposed_actions",
        ["action_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_llm_traces_action_id", "llm_traces", ["action_id"], unique=False)
    op.create_index(
        "ix_llm_traces_created_at_id", "llm_traces", ["created_at", "id"], unique=False
    )
    op.create_index(
        "ix_llm_traces_operation_created_at",
        "llm_traces",
        ["operation", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_llm_traces_operation_created_at", table_name="llm_traces")
    op.drop_index("ix_llm_traces_created_at_id", table_name="llm_traces")
    op.drop_index("ix_llm_traces_action_id", table_name="llm_traces")
    op.drop_constraint(
        op.f("fk_llm_traces_action_id_proposed_actions"), "llm_traces", type_="foreignkey"
    )
    op.drop_column("llm_traces", "request_id")
    op.drop_column("llm_traces", "action_id")
