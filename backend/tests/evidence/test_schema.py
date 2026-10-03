"""Evidence Bundle schema: the model validates its own consistency (no database needed)."""

from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from app.models.enums import AnomalySeverity
from app.schemas.evidence import (
    EVENT_CONTEXT_NOTE,
    AnalysisWindowOut,
    AnomalyEvidence,
    BundleLimits,
    ContributorEvidence,
    EvidenceBundle,
    MetricEvidence,
    ProvenanceSummary,
    RelatedEventEvidence,
    WindowOut,
)
from app.services.anomalies.rules import Comparison
from app.services.metrics.definitions import MetricUnit

T = datetime(2026, 3, 10, tzinfo=UTC)
CURRENT = WindowOut(start=datetime(2026, 3, 9, tzinfo=UTC), end=T)
WINDOW = AnalysisWindowOut(
    current=CURRENT,
    baseline=WindowOut(start=datetime(2026, 3, 2, tzinfo=UTC), end=CURRENT.start),
    event_lookback_hours=72,
)
LIMITS = BundleLimits(
    max_anomalies=5, contributors_per_family=3, max_related_events=5, event_lookback_hours=72
)
PROVENANCE = ProvenanceSummary(source="test")


def metric(evidence_id: str = "MTR-000001", window: WindowOut = CURRENT) -> MetricEvidence:
    return MetricEvidence(
        evidence_id=evidence_id,
        label="Ticket volume (overall)",
        window=window,
        dimensions={},
        provenance=PROVENANCE,
        role="overview",
        metric_key="ticket_volume",
        unit=MetricUnit.COUNT,
        value=20.0,
        baseline_value=10.0,
        change_pct=100.0,
        change_pp=None,
        baseline_zero=False,
        baseline_empty=False,
        sample_size=20,
        sample_sufficient=True,
    )


def anomaly(
    evidence_id: str = "ANOM-000001",
    metric_id: str = "MTR-000001",
    contributor_ids: tuple[str, ...] = (),
) -> AnomalyEvidence:
    return AnomalyEvidence(
        evidence_id=evidence_id,
        label="High anomaly",
        window=CURRENT,
        dimensions={},
        provenance=PROVENANCE,
        metric_evidence_id=metric_id,
        metric_key="ticket_volume",
        severity=AnomalySeverity.HIGH,
        score=100.0,
        score_comparison=Comparison.RELATIVE_PCT,
        detector_key="test",
        explanation="Volume rose.",
        contributor_status="available" if contributor_ids else "not_computed",
        contributor_evidence_ids=list(contributor_ids),
    )


def contributor(evidence_id: str = "SEG-000001", anomaly_id: str = "ANOM-000001") -> Any:
    return ContributorEvidence(
        evidence_id=evidence_id,
        label="EMEA / Enterprise",
        window=CURRENT,
        dimensions={},
        provenance=PROVENANCE,
        anomaly_evidence_id=anomaly_id,
        metric_evidence_id="MTR-000001",
        family_key="region",
        segment={"region": "emea"},
        rank=1,
        current_value=22.0,
        baseline_value=5.0,
        delta_value=17.0,
        contribution_pct=85.0,
        method="count_delta",
        sample=22,
        min_sample=5,
        sample_sufficient=True,
        flags=[],
        statement="EMEA accounts for 85.0% of the observed positive change.",
    )


def event(evidence_id: str = "EVT-000001", **overrides: Any) -> RelatedEventEvidence:
    fields: dict[str, Any] = {
        "evidence_id": evidence_id,
        "label": "Deploy",
        "window": None,
        "dimensions": {},
        "provenance": PROVENANCE,
        "event_type": "deployment",
        "title": "Deploy",
        "occurred_at": T,
        "product": None,
        "hours_from_window_start": 1.0,
        "details": {},
    }
    return RelatedEventEvidence(**{**fields, **overrides})


def bundle(**overrides: Any) -> EvidenceBundle:
    fields: dict[str, Any] = {
        "analysis_window": WINDOW,
        "metrics": [metric()],
        "anomalies": [anomaly()],
        "contributors": [contributor()],
        "related_events": [event()],
        "excluded": [],
        "limits": LIMITS,
    }
    return EvidenceBundle.create(**{**fields, **overrides})


def test_valid_bundle_derives_sorted_allow_list_and_signature() -> None:
    result = bundle()

    assert result.allowed_evidence_ids == [
        "ANOM-000001",
        "EVT-000001",
        "MTR-000001",
        "SEG-000001",
    ]
    assert len(result.signature) == 64
    assert EvidenceBundle.model_validate_json(result.model_dump_json()) == result


def test_signature_is_stable_and_content_sensitive() -> None:
    assert bundle().signature == bundle().signature
    assert bundle(metrics=[metric(window=CURRENT)]).signature == bundle().signature
    assert bundle(related_events=[]).signature != bundle().signature


def test_duplicate_evidence_ids_are_rejected() -> None:
    with pytest.raises(ValidationError, match="Duplicate evidence IDs"):
        bundle(metrics=[metric(), metric()])


def test_allow_list_must_match_items() -> None:
    good = bundle()
    tampered = good.model_dump()
    tampered["allowed_evidence_ids"] = [*good.allowed_evidence_ids, "MTR-999999"]
    with pytest.raises(ValidationError, match="allowed_evidence_ids"):
        EvidenceBundle.model_validate(tampered)


def test_tampered_content_fails_the_signature_check() -> None:
    tampered = bundle().model_dump()
    tampered["metrics"][0]["value"] = 999.0
    with pytest.raises(ValidationError, match="signature"):
        EvidenceBundle.model_validate(tampered)


def test_dangling_cross_references_are_rejected() -> None:
    with pytest.raises(ValidationError, match="metric outside the bundle"):
        bundle(metrics=[metric("MTR-000002")], contributors=[])
    with pytest.raises(ValidationError, match="anomaly outside the bundle"):
        bundle(contributors=[contributor(anomaly_id="ANOM-000009")])
    with pytest.raises(ValidationError, match="contributors outside the bundle"):
        bundle(anomalies=[anomaly(contributor_ids=("SEG-000009",))], contributors=[])


def test_a_fact_outside_the_analysis_window_is_rejected() -> None:
    other = WindowOut(start=datetime(2026, 3, 8, tzinfo=UTC), end=CURRENT.start)
    with pytest.raises(ValidationError, match="outside the analysis window"):
        bundle(metrics=[metric(window=other)])


def test_evidence_without_an_analysis_window_is_rejected() -> None:
    with pytest.raises(ValidationError, match="without an analysis window"):
        bundle(analysis_window=None)
    empty = bundle(
        analysis_window=None, metrics=[], anomalies=[], contributors=[], related_events=[]
    )
    assert empty.allowed_evidence_ids == []


def test_related_event_is_contextual_and_never_causal() -> None:
    item = event()
    assert item.evidence_class == "contextual_event"
    assert item.relationship == "temporal_proximity"
    assert item.causal is False
    assert item.context_note == EVENT_CONTEXT_NOTE

    with pytest.raises(ValidationError):
        event(causal=True)
    with pytest.raises(ValidationError):
        event(evidence_class="observed_fact")
    with pytest.raises(ValidationError, match="context note"):
        event(context_note="The deployment caused the spike.")


def test_unknown_fields_are_rejected() -> None:
    with pytest.raises(ValidationError):
        MetricEvidence(**{**metric().model_dump(), "raw_rows": []})
