"""Database-backed suites on the seeded demo dataset (rolled-back test database)."""

from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.evals.context import seed_gate
from app.evals.pipeline import detection_input_from_result, evaluate_slice
from app.evals.replay import replay
from app.evals.run import open_context, run_evaluation
from app.evals.suites import anomalies, approval, contributors
from app.evals.suites.anomalies import ESCALATED
from app.models import (
    ActionExecution,
    Anomaly,
    Approval,
    AuditLog,
    Brief,
    MetricSnapshot,
    ProposedAction,
    Ticket,
)
from app.models.enums import ActionStatus
from app.schemas.metrics import MetricFilters
from app.services.anomalies.rules import DETECTION_SLICES
from app.services.anomalies.service import AnomalyService, _detection_input
from app.services.metrics.service import MetricsService
from tests.evals.conftest import ContextFactory, eval_settings

pytestmark = pytest.mark.db

COUNTED = (MetricSnapshot, Anomaly, Brief, ProposedAction, Approval, ActionExecution, AuditLog)


def counts(session: Session) -> dict[str, int]:
    return {
        m.__tablename__: int(session.execute(select(func.count()).select_from(m)).scalar_one())
        for m in (*COUNTED, Ticket)
    }


def by_id(results: list[Any]) -> dict[str, Any]:
    return {r.case_id: r for r in results}


def test_planted_billing_anomaly_detected_by_golden_cases(demo_context: ContextFactory) -> None:
    results = by_id(anomalies.run(demo_context()))
    volume = results["anomaly.planted_billing_volume"]
    assert volume.status == "pass", volume.failure_reason
    assert "high" in (volume.observed or "") or "critical" in (volume.observed or "")
    sla = results["anomaly.planted_billing_sla"]
    assert sla.status == "pass" and "critical" in (sla.observed or "")


def test_normal_cases_report_false_positive_tallies(demo_context: ContextFactory) -> None:
    results = [r for r in anomalies.run(demo_context()) if r.case_id.startswith("normal.")]
    assert results and all(r.tally is not None and r.tally.checked > 0 for r in results)
    for r in results:
        # The tally is the evidence: a case passes exactly when nothing was flagged.
        assert (r.status == "pass") == (r.tally.flagged == 0), r.case_id
    # The final-day non-Billing queues carry no planted change.
    finals = [r for r in results if r.case_id.endswith("_final_day")]
    assert finals and all(r.status == "pass" for r in finals)


def test_injected_false_positive_is_counted(
    demo_context: ContextFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Any high anomaly on a designated normal slice makes the case fail and is counted."""
    real = anomalies.evaluate_slice

    def flag_technical(session: Session, window_end: Any, filters: dict[str, str]) -> Any:
        outcomes = real(session, window_end, filters)
        if filters != {"category": "technical"}:
            return outcomes
        planted = real(session, window_end, {"category": "billing"})
        hot = next(o for o in planted if o.metric_key == "ticket_volume")
        return [hot, *outcomes[1:]]

    monkeypatch.setattr(anomalies, "evaluate_slice", flag_technical)
    result = by_id(anomalies.run(demo_context()))["normal.technical_final_day"]
    assert result.status == "fail"
    assert result.tally is not None and result.tally.flagged == 1


def test_detector_that_never_fires_misses_the_planted_cases(
    demo_context: ContextFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.evals import pipeline  # noqa: PLC0415
    from app.services.anomalies.detector import Skip, SkipReason  # noqa: PLC0415

    monkeypatch.setattr(pipeline, "detect", lambda data: Skip(SkipReason.BELOW_THRESHOLD))
    results = by_id(anomalies.run(demo_context()))
    assert results["anomaly.planted_billing_volume"].status == "fail"
    assert results["anomaly.planted_billing_sla"].status == "fail"


def test_read_only_detection_input_matches_production(demo_session: Session) -> None:
    """The evaluator's in-memory detection input equals the persisted-snapshot input."""
    computed = MetricsService(demo_session).compute(
        None, MetricFilters.model_validate({"category": "billing"})
    )
    outcomes = {
        o.metric_key: o
        for o in evaluate_slice(demo_session, computed.window_end, {"category": "billing"})
    }
    service = AnomalyService(demo_session)
    for item in computed.items:
        if item.snapshot is None or item.metric_key not in outcomes:
            continue
        row = service.snapshots.get_by_evidence_id(item.snapshot.evidence_id)
        assert row is not None
        assert _detection_input(row) == detection_input_from_result(
            outcomes[item.metric_key].result
        )


def test_evaluator_severities_match_production_detection(demo_session: Session) -> None:
    production = AnomalyService(demo_session).detect(None)
    expected = {
        (i.metric_key, tuple(sorted(i.filters.items()))): i.anomaly.severity
        for i in production.items
        if i.anomaly is not None
    }
    observed = {}
    for slice_filters in DETECTION_SLICES:
        filters = {str(k): v for k, v in slice_filters.items()}
        for o in evaluate_slice(demo_session, production.window_end, filters):
            severity = getattr(o.outcome, "severity", None)
            if severity is not None:
                observed[(o.metric_key, tuple(sorted(filters.items())))] = severity
    assert observed == expected


def test_emea_enterprise_is_the_top_contributor(demo_context: ContextFactory) -> None:
    results = by_id(contributors.run(demo_context()))
    top = results["contributor.emea_enterprise_top"]
    assert top.status == "pass", top.observed
    assert "EMEA / Enterprise" in (top.observed or "")
    assert results["contributor.emea_region_top"].status == "pass"


def test_approval_bypass_is_blocked_and_nothing_executes(demo_context: ContextFactory) -> None:
    results = by_id(approval.run(demo_context()))
    for case_id in (
        "approval.execute_pending_blocked",
        "approval.execute_approved_status_without_record_blocked",
        "approval.system_reviewer_rejected",
        "approval.approved_executes_once",
    ):
        assert results[case_id].status == "pass", (case_id, results[case_id].observed)
    assert "executions recorded: 0" in (results["approval.execute_pending_blocked"].observed or "")
    assert "INV-" in (results["approval.approved_executes_once"].observed or "")


def test_executing_service_makes_the_bypass_case_fail(
    demo_context: ContextFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A broken execution service that ignores approval must turn the case red."""

    class Bypass:
        def __init__(self, session: Session, adapters: Any) -> None:
            self.session = session

        def execute(self, action_id: int) -> None:
            action = self.session.get(ProposedAction, action_id)
            assert action is not None
            action.status = ActionStatus.SUCCEEDED

    monkeypatch.setattr(approval, "ActionExecutionService", Bypass)
    results = by_id(approval.run(demo_context()))
    assert results["approval.execute_pending_blocked"].status == "fail"
    assert results["approval.execute_approved_status_without_record_blocked"].status == "fail"


def test_approval_cases_refuse_a_session_that_is_not_rollback_only(
    demo_context: ContextFactory,
) -> None:
    ctx = demo_context()
    ctx.rollback_only = False
    results = approval.run(ctx)
    assert {r.status for r in results} == {"not_run"}


def test_replay_summarises_the_final_seven_days(demo_session: Session) -> None:
    summary = replay(demo_session, 7)
    assert summary.status == "completed" and len(summary.days) == 7
    ends = [d.window_end for d in summary.days]
    assert ends == sorted(ends) and ends[-1].isoformat().startswith("2026-10-04")
    assert all(d.status == "ok" for d in summary.days)

    def billing_escalated(day: Any) -> bool:
        return any(
            a.filters == {"category": "billing"}
            and a.metric_key == "ticket_volume"
            and a.severity in ESCALATED
            for a in day.anomalies
        )

    assert billing_escalated(summary.days[-1])  # final day: planted spike
    assert not billing_escalated(summary.days[0])  # a pre-deployment day


def test_replay_reports_days_without_data(demo_session: Session) -> None:
    """An empty day and days whose baseline predates the data are no_data, not crashes."""
    demo_session.execute(
        delete(Ticket).where(
            or_(
                Ticket.created_at < datetime(2026, 9, 20, tzinfo=UTC),
                and_(
                    Ticket.created_at >= datetime(2026, 9, 30, tzinfo=UTC),
                    Ticket.created_at < datetime(2026, 10, 1, tzinfo=UTC),
                ),
            )
        )
    )
    demo_session.flush()
    summary = replay(demo_session, 10)
    assert summary.status == "completed" and len(summary.days) == 10
    status = {d.window_start.date().isoformat(): (d.status, d.detail) for d in summary.days}
    assert status["2026-09-24"][0] == "no_data" and "baseline" in (status["2026-09-24"][1] or "")
    assert status["2026-09-30"] == ("no_data", "No tickets were created in this window.")
    assert status["2026-10-03"][0] == "ok"
    assert all(not d.anomalies for d in summary.days if d.status == "no_data")


def test_full_run_never_writes_analytics_rows(demo_context: ContextFactory) -> None:
    """Golden cases and replay are read-only: no snapshot/anomaly/ticket row is written."""
    ctx = demo_context()
    assert ctx.session is not None
    analytics = ("metric_snapshots", "anomalies", "tickets")
    before = counts(ctx.session)
    report = run_evaluation(ctx, "all")
    after = counts(ctx.session)
    assert {k: after[k] for k in analytics} == {k: before[k] for k in analytics}
    assert report.replay is not None and report.replay.status == "completed"
    assert report.seed.matches
    assert [c for c in report.cases if c.status != "not_run"]
    assert not [c for c in report.cases if c.status == "error"]


def test_open_context_rolls_back_every_write(engine: Engine) -> None:
    """After a real run, a separate connection sees exactly the rows it saw before."""

    def snapshot() -> dict[str, int]:
        with Session(engine) as fresh:
            return counts(fresh)

    before = snapshot()
    with open_context(eval_settings(), engine) as ctx:
        report = run_evaluation(ctx, "deterministic")
    approval_cases = [c for c in report.cases if c.category.value == "approval_boundary"]
    assert approval_cases and all(c.status == "pass" for c in approval_cases)
    assert snapshot() == before


def test_seed_version_mismatch_makes_dataset_cases_not_run(demo_context: ContextFactory) -> None:
    ctx = demo_context()
    assert seed_gate(ctx, "999") is not None
    ctx.seed = ctx.seed.model_copy(
        update={"observed_state": "inconsistent", "observed_version": "0", "matches": False}
    )
    results = [*anomalies.run(ctx), *contributors.run(ctx)]
    assert {r.status for r in results} == {"not_run"}
    assert all("seed_version_mismatch" in (r.failure_reason or "") for r in results)


def test_empty_database_reports_seed_missing(
    demo_context: ContextFactory, demo_session: Session
) -> None:
    ctx = demo_context()
    ctx.seed = ctx.seed.model_copy(
        update={"observed_state": "empty", "observed_version": None, "matches": False}
    )
    results = anomalies.run(ctx)
    assert {r.status for r in results} == {"not_run"}
    assert "seed_missing" in (results[0].failure_reason or "")
