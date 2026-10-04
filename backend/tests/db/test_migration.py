"""Alembic owns the schema: upgrade, downgrade, drift, indexes, timestamps."""

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

import app.models  # noqa: F401
from app.db.base import Base
from app.services.evidence_ids import EVIDENCE_SEQUENCES
from tests.db import migrations
from tests.db.safety import assert_safe_test_database

pytestmark = pytest.mark.db

DOMAIN_TABLES = {
    "customers",
    "support_teams",
    "tickets",
    "incidents",
    "metric_snapshots",
    "anomalies",
    "anomaly_contributors",
    "briefs",
    "brief_claims",
    "proposed_actions",
    "approvals",
    "action_executions",
    "llm_traces",
    "audit_logs",
}


def _sequences(engine: Engine) -> set[str]:
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT sequencename FROM pg_sequences")).scalars()
        return set(rows)


def test_upgrade_creates_all_domain_tables(engine: Engine) -> None:
    tables = set(inspect(engine).get_table_names())
    assert tables == DOMAIN_TABLES | {"alembic_version"}
    assert set(EVIDENCE_SEQUENCES.values()) <= _sequences(engine)


def test_models_match_migration(engine: Engine) -> None:
    with engine.connect() as conn:
        ctx = MigrationContext.configure(conn, opts={"compare_type": True})
        assert compare_metadata(ctx, Base.metadata) == []


def test_downgrade_then_upgrade_is_clean(engine: Engine, test_db_url: str) -> None:
    # Re-assert the guard immediately before the destructive step.
    from app.core.config import get_settings

    settings = get_settings()
    assert_safe_test_database(settings.test_database_url, settings.database_url)

    try:
        migrations.downgrade(test_db_url, "base")
        assert set(inspect(engine).get_table_names()) <= {"alembic_version"}
        assert not set(EVIDENCE_SEQUENCES.values()) & _sequences(engine)
    finally:
        migrations.upgrade(test_db_url, "head")

    assert set(inspect(engine).get_table_names()) == DOMAIN_TABLES | {"alembic_version"}


@pytest.mark.parametrize(
    ("table", "index"),
    [
        ("tickets", "ix_tickets_created_at"),
        ("tickets", "ix_tickets_category_created_at"),
        ("tickets", "ix_tickets_product_created_at"),
        ("tickets", "ix_tickets_customer_id_created_at"),
        ("tickets", "ix_tickets_support_team_id_created_at"),
        ("tickets", "ix_tickets_sla_breached_created_at"),
        ("metric_snapshots", "ix_metric_snapshots_metric_key_window_end"),
        ("anomalies", "ix_anomalies_status_detected_at"),
    ],
)
def test_required_indexes_exist(engine: Engine, table: str, index: str) -> None:
    names = {ix["name"] for ix in inspect(engine).get_indexes(table)}
    assert index in names


@pytest.mark.parametrize(
    ("table", "column"),
    [
        ("customers", "customer_ref"),
        ("support_teams", "team_key"),
        ("tickets", "ticket_ref"),
        ("incidents", "evidence_id"),
        ("metric_snapshots", "evidence_id"),
        ("metric_snapshots", "analysis_signature"),
        ("anomalies", "evidence_id"),
        ("anomaly_contributors", "evidence_id"),
        ("proposed_actions", "brief_id"),
        ("approvals", "action_id"),
        ("action_executions", "action_id"),
    ],
)
def test_unique_constraints_exist(engine: Engine, table: str, column: str) -> None:
    insp = inspect(engine)
    uniques = [tuple(u["column_names"]) for u in insp.get_unique_constraints(table)]
    uniques += [tuple(i["column_names"]) for i in insp.get_indexes(table) if i["unique"]]
    assert (column,) in uniques


def test_tickets_created_at_is_event_time_not_row_default(engine: Engine) -> None:
    cols = {c["name"]: c for c in inspect(engine).get_columns("tickets")}
    assert "created_at" in cols
    assert "resolved_at" in cols
    assert "updated_at" not in cols
    assert cols["created_at"]["default"] is None
    assert cols["created_at"]["nullable"] is False


@pytest.mark.parametrize("table", ["anomaly_contributors", "brief_claims"])
def test_tables_without_spec_timestamps_have_none(engine: Engine, table: str) -> None:
    names = {c["name"] for c in inspect(engine).get_columns(table)}
    assert not {n for n in names if n.endswith("_at")}


@pytest.mark.parametrize(
    "table", ["customers", "support_teams", "incidents", "briefs", "proposed_actions"]
)
def test_lifecycle_timestamps_only_where_specified(engine: Engine, table: str) -> None:
    names = {c["name"] for c in inspect(engine).get_columns(table)}
    assert {"created_at", "updated_at"} <= names


@pytest.mark.parametrize(
    "table",
    ["metric_snapshots", "anomalies", "approvals", "action_executions", "llm_traces", "audit_logs"],
)
def test_event_tables_have_no_updated_at(engine: Engine, table: str) -> None:
    names = {c["name"] for c in inspect(engine).get_columns(table)}
    assert "updated_at" not in names


def test_anomaly_snapshot_detector_pair_is_unique(engine: Engine) -> None:
    uniques = [
        tuple(u["column_names"]) for u in inspect(engine).get_unique_constraints("anomalies")
    ]
    assert ("metric_snapshot_id", "detector_key") in uniques
