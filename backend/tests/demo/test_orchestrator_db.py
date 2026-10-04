"""The single analysis path on the seeded demo dataset (Spec 15)."""

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.integrations.llm.base import LLMTimeoutError
from app.models import (
    Anomaly,
    AnomalyContributor,
    Brief,
    BriefClaim,
    LLMTrace,
    MetricSnapshot,
    ProposedAction,
)
from app.models.enums import AnomalySeverity, BriefStatus
from app.services.analysis.orchestrator import AnalysisOrchestrator
from tests.demo.conftest import LLM_SETTINGS, NO_LLM_SETTINGS, StubBriefClient, count

pytestmark = pytest.mark.db


class FailingBriefClient:
    def generate_brief(self, bundle: object) -> object:
        raise LLMTimeoutError("The model provider timed out.", latency_ms=5)


def test_run_produces_the_canonical_billing_scenario_and_a_valid_brief(
    seeded: Session, stub_brief: StubBriefClient
) -> None:
    result = AnalysisOrchestrator(seeded, LLM_SETTINGS, lambda: stub_brief).run()

    billing_volume = next(
        a
        for a in result.anomalies
        if a.metric_key == "ticket_volume" and a.dimensions == {"category": "billing"}
    )
    assert billing_volume.severity in (AnomalySeverity.HIGH, AnomalySeverity.CRITICAL)
    assert billing_volume.contributor_status == "computed"
    assert billing_volume.contributor_evidence_ids
    severities = [a.severity for a in result.anomalies]
    order = [AnomalySeverity.CRITICAL, AnomalySeverity.HIGH, AnomalySeverity.MEDIUM]
    assert severities == sorted(severities, key=lambda s: order.index(s) if s in order else 9)

    ids = result.evidence.allowed_evidence_ids
    for prefix in ("MTR-", "ANOM-", "SEG-", "EVT-"):
        assert any(i.startswith(prefix) for i in ids), prefix
    assert result.metric_windows_computed > 1  # trend history for the dashboard

    assert result.brief.state == "generated"
    assert result.brief.status is BriefStatus.VALID
    claims = " ".join(
        seeded.execute(
            select(BriefClaim.text).where(BriefClaim.brief_id == result.brief.brief_id)
        ).scalars()
    )
    assert "EMEA" in claims and "Enterprise" in claims
    assert "coincided" in claims


def test_rerun_reuses_every_deterministic_artifact(
    seeded: Session, stub_brief: StubBriefClient
) -> None:
    first = AnalysisOrchestrator(seeded, NO_LLM_SETTINGS).run()
    counts = [count(seeded, m) for m in (MetricSnapshot, Anomaly, AnomalyContributor)]
    second = AnalysisOrchestrator(seeded, NO_LLM_SETTINGS).run()

    assert second.metric_evidence_ids == first.metric_evidence_ids
    assert [a.evidence_id for a in second.anomalies] == [a.evidence_id for a in first.anomalies]
    assert {a.contributor_status for a in second.anomalies} <= {"reused", "not_supported"}
    assert second.evidence.signature == first.evidence.signature
    assert [count(seeded, m) for m in (MetricSnapshot, Anomaly, AnomalyContributor)] == counts


def test_without_llm_the_brief_is_explicitly_not_configured(seeded: Session) -> None:
    result = AnalysisOrchestrator(seeded, NO_LLM_SETTINGS, lambda: StubBriefClient()).run()

    assert result.brief.state == "not_configured"
    assert result.brief.error_code == "LLM_NOT_CONFIGURED"
    assert result.brief.brief_id is None
    assert count(seeded, Brief) == 0
    assert count(seeded, LLMTrace) == 0


def test_model_failure_keeps_the_deterministic_artifacts(seeded: Session) -> None:
    result = AnalysisOrchestrator(seeded, LLM_SETTINGS, lambda: FailingBriefClient()).run()  # type: ignore[arg-type,return-value]

    assert result.brief.state == "failed"
    assert result.brief.error_code == "LLM_TIMEOUT"
    assert count(seeded, Brief) == 0
    assert count(seeded, LLMTrace) == 1  # the failed call is traced
    assert count(seeded, Anomaly) == len(result.anomalies) > 0


def test_the_orchestrator_never_proposes_or_executes_actions(
    seeded: Session, stub_brief: StubBriefClient
) -> None:
    AnalysisOrchestrator(seeded, LLM_SETTINGS, lambda: stub_brief).run()

    assert count(seeded, ProposedAction) == 0
