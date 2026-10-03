"""Contributor computation against PostgreSQL: arithmetic, IDs, provenance, idempotency."""

import re
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AnomalyContributor
from app.models.enums import AnomalySeverity
from app.schemas.contributors import ContributorAnalysisResponse, ContributorGroupOut
from app.services.anomalies.errors import AnomalyNotFoundError, InvalidEvidenceIdError
from app.services.anomalies.service import AnomalyService
from app.services.contributors.errors import (
    ContributorsNotComputedError,
    SegmentationNotSupportedError,
)
from app.services.contributors.formulas import (
    FamilyStatus,
    contribution_pct,
    expected_events,
    parent_baseline_rate,
)
from app.services.contributors.provenance import ContributorProvenance
from app.services.contributors.service import ContributorService
from app.services.metrics.engine import analysis_window
from tests.contributors.conftest import END, billing_anomaly_id
from tests.db import factories
from tests.metrics.conftest import World

pytestmark = pytest.mark.db

SEG_ID = re.compile(r"^SEG-\d{6,}$")


def group(response: ContributorAnalysisResponse, family_key: str) -> ContributorGroupOut:
    return next(g for g in response.groups if g.family_key == family_key)


def row_count(session: Session) -> int:
    return session.execute(select(func.count()).select_from(AnomalyContributor)).scalar_one()


# --- count metric -------------------------------------------------------------------


def test_count_anomaly_ranks_segments_by_share_of_positive_change(volume_world: World) -> None:
    session = volume_world.session
    anomaly_id = billing_anomaly_id(session, "ticket_volume")

    response = ContributorService(session).compute(anomaly_id)

    assert response.status == "computed"
    assert response.metric_key == "ticket_volume"
    region = group(response, "region")
    assert [(c.segment, c.rank) for c in region.contributors] == [
        ({"region": "emea"}, 1),
        ({"region": "apac"}, 2),
    ]
    emea, apac = region.contributors
    assert (emea.current_value, emea.baseline_value, emea.delta_value) == (22.0, 5.0, 17.0)
    assert (apac.current_value, apac.baseline_value, apac.delta_value) == (8.0, 5.0, 3.0)
    assert (emea.contribution_pct, apac.contribution_pct) == (85.0, 15.0)
    assert region.positive_delta_total == 20.0
    assert region.other_contribution_pct == 0.0


def test_every_non_fixed_family_is_computed_and_the_fixed_one_is_skipped(
    volume_world: World,
) -> None:
    session = volume_world.session
    response = ContributorService(session).compute(billing_anomaly_id(session, "ticket_volume"))

    assert {g.family_key for g in response.groups} == {
        "region",
        "customer_tier",
        "product",
        "support_team",
        "region+customer_tier",
    }
    # category is fixed by the anomaly's own slice; it is reported, not segmented.
    assert [(f.family_key, f.status) for f in response.unranked_families] == [
        ("category", FamilyStatus.SKIPPED_FIXED_DIMENSION)
    ]


def test_combined_region_and_tier_segment_is_ranked_first(volume_world: World) -> None:
    session = volume_world.session
    response = ContributorService(session).compute(billing_anomaly_id(session, "ticket_volume"))

    combo = group(response, "region+customer_tier")
    top = combo.contributors[0]
    assert top.segment == {"region": "emea", "customer_tier": "enterprise"}
    assert top.label == "EMEA / Enterprise"
    assert top.contribution_pct == 85.0


def test_contributors_use_the_anomalys_own_windows(volume_world: World) -> None:
    session = volume_world.session
    response = ContributorService(session).compute(billing_anomaly_id(session, "ticket_volume"))
    window = analysis_window(END)

    assert response.window_start == window.current.start
    assert response.window_end == window.current.end
    for g in response.groups:
        for c in g.contributors:
            assert c.provenance.current_window.start == window.current.start
            assert c.provenance.baseline_window.start == window.baseline.start
            assert [d.start for d in c.provenance.baseline_days] == [
                d.start for d in window.baseline_days
            ]
            assert c.provenance.base_filters == {"category": "billing"}


# --- rate metric --------------------------------------------------------------------


def test_rate_anomaly_attributes_excess_events_not_percentages(breach_world: World) -> None:
    session = breach_world.session
    anomaly_id = billing_anomaly_id(session, "sla_breach_rate")

    response = ContributorService(session).compute(anomaly_id)

    region = group(response, "region")
    emea, apac = region.contributors
    assert emea.segment == {"region": "emea"}
    # actual events, expected events (20 tickets * 10% baseline), excess
    assert (emea.current_value, emea.baseline_value, emea.delta_value) == (16.0, 2.0, 14.0)
    assert (apac.current_value, apac.baseline_value, apac.delta_value) == (4.0, 2.0, 2.0)
    assert (emea.contribution_pct, apac.contribution_pct) == (87.5, 12.5)
    assert "excess" in emea.statement
    assert emea.provenance.method.value == "rate_excess"
    assert emea.provenance.current_denominator == 20
    assert (emea.provenance.baseline_numerator, emea.provenance.baseline_denominator) == (14, 140)
    assert emea.provenance.baseline_rate_source == "segment"


def test_anomaly_severity_is_untouched_by_contributor_analysis(breach_world: World) -> None:
    session = breach_world.session
    anomaly_id = billing_anomaly_id(session, "sla_breach_rate")

    assert AnomalyService(session).get(anomaly_id).severity is AnomalySeverity.CRITICAL


# --- evidence IDs, provenance, idempotency ------------------------------------------


def test_contributors_get_seg_evidence_ids(volume_world: World) -> None:
    session = volume_world.session
    response = ContributorService(session).compute(billing_anomaly_id(session, "ticket_volume"))

    ids = [c.evidence_id for g in response.groups for c in g.contributors]
    assert ids and len(ids) == len(set(ids))
    assert all(SEG_ID.match(i) for i in ids)
    stored = session.execute(select(AnomalyContributor.evidence_id)).scalars().all()
    assert set(stored) == set(ids)


def test_provenance_holds_formula_window_and_sample_information(volume_world: World) -> None:
    session = volume_world.session
    anomaly_id = billing_anomaly_id(session, "ticket_volume")
    response = ContributorService(session).compute(anomaly_id)

    contributor = group(response, "region").contributors[0]
    p = contributor.provenance
    assert p.anomaly_evidence_id == anomaly_id
    assert p.metric_evidence_id == response.metric_evidence_id
    assert "contribution_pct = positive_delta / sum(positive_deltas) * 100" in p.formula
    assert len(p.baseline_days) == 7
    assert (p.sample, p.min_sample, p.sample_sufficient) == (22, 5, True)
    assert p.baseline_value == Decimal("5")
    # The stored JSON validates against the typed model, not just the response copy.
    row = session.execute(
        select(AnomalyContributor).where(AnomalyContributor.evidence_id == contributor.evidence_id)
    ).scalar_one()
    assert ContributorProvenance.model_validate(row.provenance_json) == p


def test_count_result_can_be_recomputed_from_provenance(volume_world: World) -> None:
    session = volume_world.session
    response = ContributorService(session).compute(billing_anomaly_id(session, "ticket_volume"))

    for c in group(response, "region").contributors:
        p = c.provenance
        assert p.baseline_value is not None
        delta = Decimal(p.current_events) - p.baseline_value
        assert delta == p.delta
        share = contribution_pct(delta, p.family_positive_delta_total)
        assert share is not None and float(share) == c.contribution_pct


def test_rate_result_can_be_recomputed_from_provenance(breach_world: World) -> None:
    session = breach_world.session
    response = ContributorService(session).compute(billing_anomaly_id(session, "sla_breach_rate"))

    for c in group(response, "region+customer_tier").contributors:
        p = c.provenance
        assert p.baseline_numerator is not None and p.baseline_denominator is not None
        assert p.current_denominator is not None
        rate = parent_baseline_rate(p.baseline_numerator, p.baseline_denominator)
        assert rate is not None
        expected = expected_events(p.current_denominator, rate)
        assert expected == p.expected_events
        assert Decimal(p.current_events) - expected == p.delta
        share = contribution_pct(p.delta, p.family_positive_delta_total)
        assert share is not None and float(share) == c.contribution_pct


def test_repeat_compute_reuses_rows_and_ids(volume_world: World) -> None:
    session = volume_world.session
    anomaly_id = billing_anomaly_id(session, "ticket_volume")
    service = ContributorService(session)

    first = service.compute(anomaly_id)
    rows = row_count(session)
    second = service.compute(anomaly_id)

    assert (first.status, second.status) == ("computed", "reused")
    assert row_count(session) == rows
    assert second.groups == first.groups


def test_get_returns_the_stored_groups(volume_world: World) -> None:
    session = volume_world.session
    anomaly_id = billing_anomaly_id(session, "ticket_volume")
    service = ContributorService(session)
    computed = service.compute(anomaly_id)

    stored = service.get(anomaly_id)

    assert stored.status == "reused"
    assert stored.groups == computed.groups


# --- errors -------------------------------------------------------------------------


def test_get_before_compute_is_not_computed(volume_world: World) -> None:
    session = volume_world.session
    anomaly_id = billing_anomaly_id(session, "ticket_volume")
    with pytest.raises(ContributorsNotComputedError):
        ContributorService(session).get(anomaly_id)


def test_bad_and_unknown_ids_are_typed_errors(volume_world: World) -> None:
    service = ContributorService(volume_world.session)
    with pytest.raises(InvalidEvidenceIdError):
        service.compute("MTR-000001")
    with pytest.raises(InvalidEvidenceIdError):
        service.get("nonsense")
    with pytest.raises(AnomalyNotFoundError):
        service.compute("ANOM-999999")


def test_mean_metric_anomaly_does_not_support_segmentation(volume_world: World) -> None:
    session = volume_world.session
    snapshot = factories.metric_snapshot(session, metric_key="first_response_minutes")
    session.add(snapshot)
    session.flush()
    anomaly = factories.anomaly(session, snapshot.id)
    session.add(anomaly)
    session.flush()

    with pytest.raises(SegmentationNotSupportedError):
        ContributorService(session).compute(anomaly.evidence_id)
    assert row_count(session) == 0
