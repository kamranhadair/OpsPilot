"""domain model

Revision ID: 0001
Revises:
Create Date: 2026-10-03 18:37:07.973357

"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


EVIDENCE_SEQUENCES = (
    "evidence_evt_seq",
    "evidence_mtr_seq",
    "evidence_anom_seq",
    "evidence_seg_seq",
)


def upgrade() -> None:
    for sequence in EVIDENCE_SEQUENCES:
        op.execute(sa.schema.CreateSequence(sa.Sequence(sequence)))
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "actor_type",
            sa.Enum(
                "human",
                "system",
                "ai",
                name="audit_actor_type",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("actor_id", sa.String(length=200), nullable=True),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("entity_type", sa.String(length=100), nullable=False),
        sa.Column("entity_id", sa.String(length=100), nullable=False),
        sa.Column("payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_logs")),
    )
    op.create_index(
        "ix_audit_logs_entity", "audit_logs", ["entity_type", "entity_id"], unique=False
    )
    op.create_table(
        "briefs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("analysis_window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("analysis_window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("headline", sa.String(length=500), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "draft",
                "valid",
                "invalid",
                name="brief_status",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("model_name", sa.String(length=100), nullable=False),
        sa.Column(
            "validation_errors_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "analysis_window_end > analysis_window_start", name=op.f("ck_briefs_window_order")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_briefs")),
    )
    op.create_table(
        "customers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("customer_ref", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column(
            "tier",
            sa.Enum(
                "starter",
                "business",
                "enterprise",
                name="customer_tier",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column(
            "region",
            sa.Enum(
                "emea",
                "north_america",
                "apac",
                name="customer_region",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_customers")),
        sa.UniqueConstraint("customer_ref", name=op.f("uq_customers_customer_ref")),
    )
    op.create_table(
        "incidents",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("evidence_id", sa.String(length=32), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "product",
            sa.Enum(
                "billing_api",
                "invoicing",
                "subscriptions",
                "core_platform",
                name="incident_product",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=True,
        ),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "evidence_id ~ '^EVT-[0-9]+$'", name=op.f("ck_incidents_evidence_prefix")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_incidents")),
        sa.UniqueConstraint("evidence_id", name=op.f("uq_incidents_evidence_id")),
    )
    op.create_table(
        "metric_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("evidence_id", sa.String(length=32), nullable=False),
        sa.Column("metric_key", sa.String(length=100), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("baseline_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("baseline_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dimensions_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("value", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("baseline_value", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("change_pct", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("sample_size", sa.Integer(), nullable=False),
        sa.Column("provenance_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "evidence_id ~ '^MTR-[0-9]+$'", name=op.f("ck_metric_snapshots_evidence_prefix")
        ),
        sa.CheckConstraint(
            "(baseline_start IS NULL AND baseline_end IS NULL) OR (baseline_start IS NOT NULL AND baseline_end IS NOT NULL AND baseline_end > baseline_start)",
            name=op.f("ck_metric_snapshots_baseline_order"),
        ),
        sa.CheckConstraint("sample_size >= 0", name=op.f("ck_metric_snapshots_sample_size_nonneg")),
        sa.CheckConstraint(
            "window_end > window_start", name=op.f("ck_metric_snapshots_window_order")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_metric_snapshots")),
        sa.UniqueConstraint("evidence_id", name=op.f("uq_metric_snapshots_evidence_id")),
    )
    op.create_index(
        "ix_metric_snapshots_metric_key_window_end",
        "metric_snapshots",
        ["metric_key", "window_end"],
        unique=False,
    )
    op.create_table(
        "support_teams",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("team_key", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_support_teams")),
        sa.UniqueConstraint("team_key", name=op.f("uq_support_teams_team_key")),
    )
    op.create_table(
        "anomalies",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("evidence_id", sa.String(length=32), nullable=False),
        sa.Column("metric_snapshot_id", sa.Integer(), nullable=False),
        sa.Column("detector_key", sa.String(length=100), nullable=False),
        sa.Column(
            "severity",
            sa.Enum(
                "low",
                "medium",
                "high",
                "critical",
                name="anomaly_severity",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("score", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("threshold_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "active",
                "acknowledged",
                "resolved",
                name="anomaly_status",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "evidence_id ~ '^ANOM-[0-9]+$'", name=op.f("ck_anomalies_evidence_prefix")
        ),
        sa.ForeignKeyConstraint(
            ["metric_snapshot_id"],
            ["metric_snapshots.id"],
            name=op.f("fk_anomalies_metric_snapshot_id_metric_snapshots"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_anomalies")),
        sa.UniqueConstraint("evidence_id", name=op.f("uq_anomalies_evidence_id")),
    )
    op.create_index(
        "ix_anomalies_metric_snapshot_id", "anomalies", ["metric_snapshot_id"], unique=False
    )
    op.create_index(
        "ix_anomalies_status_detected_at", "anomalies", ["status", "detected_at"], unique=False
    )
    op.create_table(
        "brief_claims",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("brief_id", sa.Integer(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column(
            "claim_type",
            sa.Enum(
                "observation",
                "inference",
                name="claim_type",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("evidence_ids_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "validation_status",
            sa.Enum(
                "pending",
                "valid",
                "invalid",
                name="claim_validation_status",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column(
            "validation_errors_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["brief_id"],
            ["briefs.id"],
            name=op.f("fk_brief_claims_brief_id_briefs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_brief_claims")),
        sa.UniqueConstraint("brief_id", "ordinal", name="uq_brief_claims_brief_id_ordinal"),
    )
    op.create_index("ix_brief_claims_brief_id", "brief_claims", ["brief_id"], unique=False)
    op.create_table(
        "llm_traces",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("brief_id", sa.Integer(), nullable=True),
        sa.Column("operation", sa.String(length=100), nullable=False),
        sa.Column("model_name", sa.String(length=100), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("estimated_cost_usd", sa.Numeric(precision=12, scale=6), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "success", "error", name="trace_status", native_enum=False, create_constraint=True
            ),
            nullable=False,
        ),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("latency_ms >= 0", name=op.f("ck_llm_traces_latency_nonneg")),
        sa.ForeignKeyConstraint(
            ["brief_id"],
            ["briefs.id"],
            name=op.f("fk_llm_traces_brief_id_briefs"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_llm_traces")),
    )
    op.create_index("ix_llm_traces_brief_id", "llm_traces", ["brief_id"], unique=False)
    op.create_table(
        "proposed_actions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("brief_id", sa.Integer(), nullable=False),
        sa.Column(
            "action_type",
            sa.Enum(
                "open_investigation", name="action_type", native_enum=False, create_constraint=True
            ),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("evidence_ids_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "proposed",
                "pending_approval",
                "approved",
                "rejected",
                "executing",
                "succeeded",
                "failed",
                name="action_status",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["brief_id"],
            ["briefs.id"],
            name=op.f("fk_proposed_actions_brief_id_briefs"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_proposed_actions")),
    )
    op.create_index("ix_proposed_actions_brief_id", "proposed_actions", ["brief_id"], unique=False)
    op.create_table(
        "tickets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ticket_ref", sa.String(length=64), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("support_team_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "priority",
            sa.Enum(
                "p1",
                "p2",
                "p3",
                "p4",
                name="ticket_priority",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "open",
                "pending",
                "solved",
                "closed",
                name="ticket_status",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column(
            "channel",
            sa.Enum(
                "email",
                "web",
                "api",
                "chat",
                name="ticket_channel",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column(
            "category",
            sa.Enum(
                "billing",
                "technical",
                "integration",
                "account",
                name="ticket_category",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column(
            "product",
            sa.Enum(
                "billing_api",
                "invoicing",
                "subscriptions",
                "core_platform",
                name="ticket_product",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("first_response_minutes", sa.Integer(), nullable=True),
        sa.Column("resolution_minutes", sa.Integer(), nullable=True),
        sa.Column("sla_target_minutes", sa.Integer(), nullable=False),
        sa.Column("sla_breached", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("sentiment_score", sa.Numeric(precision=4, scale=3), nullable=False),
        sa.Column("escalated", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("subject", sa.String(length=200), nullable=True),
        sa.CheckConstraint(
            "first_response_minutes IS NULL OR first_response_minutes >= 0",
            name=op.f("ck_tickets_first_response_nonneg"),
        ),
        sa.CheckConstraint(
            "resolution_minutes IS NULL OR resolution_minutes >= 0",
            name=op.f("ck_tickets_resolution_nonneg"),
        ),
        sa.CheckConstraint(
            "resolved_at IS NULL OR resolved_at >= created_at",
            name=op.f("ck_tickets_resolved_order"),
        ),
        sa.CheckConstraint(
            "sentiment_score >= -1 AND sentiment_score <= 1",
            name=op.f("ck_tickets_sentiment_range"),
        ),
        sa.CheckConstraint("sla_target_minutes > 0", name=op.f("ck_tickets_sla_target_positive")),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["customers.id"],
            name=op.f("fk_tickets_customer_id_customers"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["support_team_id"],
            ["support_teams.id"],
            name=op.f("fk_tickets_support_team_id_support_teams"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tickets")),
        sa.UniqueConstraint("ticket_ref", name=op.f("uq_tickets_ticket_ref")),
    )
    op.create_index(
        "ix_tickets_category_created_at", "tickets", ["category", "created_at"], unique=False
    )
    op.create_index("ix_tickets_created_at", "tickets", ["created_at"], unique=False)
    op.create_index(
        "ix_tickets_customer_id_created_at", "tickets", ["customer_id", "created_at"], unique=False
    )
    op.create_index(
        "ix_tickets_product_created_at", "tickets", ["product", "created_at"], unique=False
    )
    op.create_index(
        "ix_tickets_sla_breached_created_at",
        "tickets",
        ["sla_breached", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_tickets_support_team_id_created_at",
        "tickets",
        ["support_team_id", "created_at"],
        unique=False,
    )
    op.create_table(
        "action_executions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("action_id", sa.Integer(), nullable=False),
        sa.Column("adapter_key", sa.String(length=100), nullable=False),
        sa.Column("external_ref", sa.String(length=200), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "executing",
                "succeeded",
                "failed",
                name="execution_status",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("request_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("response_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["action_id"],
            ["proposed_actions.id"],
            name=op.f("fk_action_executions_action_id_proposed_actions"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_action_executions")),
    )
    op.create_index(
        "ix_action_executions_action_id", "action_executions", ["action_id"], unique=False
    )
    op.create_table(
        "anomaly_contributors",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("evidence_id", sa.String(length=32), nullable=False),
        sa.Column("anomaly_id", sa.Integer(), nullable=False),
        sa.Column("dimension_key", sa.String(length=100), nullable=False),
        sa.Column("segment_value", sa.String(length=200), nullable=False),
        sa.Column("current_value", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("baseline_value", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("delta_value", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("contribution_pct", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("provenance_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.CheckConstraint(
            "evidence_id ~ '^SEG-[0-9]+$'", name=op.f("ck_anomaly_contributors_evidence_prefix")
        ),
        sa.CheckConstraint("rank >= 1", name=op.f("ck_anomaly_contributors_rank_positive")),
        sa.ForeignKeyConstraint(
            ["anomaly_id"],
            ["anomalies.id"],
            name=op.f("fk_anomaly_contributors_anomaly_id_anomalies"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_anomaly_contributors")),
        sa.UniqueConstraint("evidence_id", name=op.f("uq_anomaly_contributors_evidence_id")),
    )
    op.create_index(
        "ix_anomaly_contributors_anomaly_id", "anomaly_contributors", ["anomaly_id"], unique=False
    )
    op.create_table(
        "approvals",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("action_id", sa.Integer(), nullable=False),
        sa.Column(
            "decision",
            sa.Enum(
                "approved",
                "rejected",
                name="approval_decision",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("reviewer", sa.String(length=200), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column(
            "edited_payload_json",
            postgresql.JSONB(none_as_null=True, astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["action_id"],
            ["proposed_actions.id"],
            name=op.f("fk_approvals_action_id_proposed_actions"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_approvals")),
    )
    op.create_index("ix_approvals_action_id", "approvals", ["action_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_approvals_action_id", table_name="approvals")
    op.drop_table("approvals")
    op.drop_index("ix_anomaly_contributors_anomaly_id", table_name="anomaly_contributors")
    op.drop_table("anomaly_contributors")
    op.drop_index("ix_action_executions_action_id", table_name="action_executions")
    op.drop_table("action_executions")
    op.drop_index("ix_tickets_support_team_id_created_at", table_name="tickets")
    op.drop_index("ix_tickets_sla_breached_created_at", table_name="tickets")
    op.drop_index("ix_tickets_product_created_at", table_name="tickets")
    op.drop_index("ix_tickets_customer_id_created_at", table_name="tickets")
    op.drop_index("ix_tickets_created_at", table_name="tickets")
    op.drop_index("ix_tickets_category_created_at", table_name="tickets")
    op.drop_table("tickets")
    op.drop_index("ix_proposed_actions_brief_id", table_name="proposed_actions")
    op.drop_table("proposed_actions")
    op.drop_index("ix_llm_traces_brief_id", table_name="llm_traces")
    op.drop_table("llm_traces")
    op.drop_index("ix_brief_claims_brief_id", table_name="brief_claims")
    op.drop_table("brief_claims")
    op.drop_index("ix_anomalies_status_detected_at", table_name="anomalies")
    op.drop_index("ix_anomalies_metric_snapshot_id", table_name="anomalies")
    op.drop_table("anomalies")
    op.drop_table("support_teams")
    op.drop_index("ix_metric_snapshots_metric_key_window_end", table_name="metric_snapshots")
    op.drop_table("metric_snapshots")
    op.drop_table("incidents")
    op.drop_table("customers")
    op.drop_table("briefs")
    op.drop_index("ix_audit_logs_entity", table_name="audit_logs")
    op.drop_table("audit_logs")
    for sequence in EVIDENCE_SEQUENCES:
        op.execute(sa.schema.DropSequence(sa.Sequence(sequence)))
