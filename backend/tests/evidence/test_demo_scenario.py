"""The seeded demo dataset yields the planted Billing story as bundle evidence."""

import pytest
from sqlalchemy.orm import Session

from app.schemas.evidence import EvidenceBundle
from app.services.anomalies.service import AnomalyService
from app.services.contributors.service import ContributorService
from app.services.evidence.assembler import EvidenceBundleAssembler

pytestmark = pytest.mark.db


def demo_bundle(session: Session) -> EvidenceBundle:
    detected = AnomalyService(session).detect(None)
    for item in detected.items:
        if item.anomaly is not None and item.filters == {"category": "billing"}:
            ContributorService(session).compute(item.anomaly.evidence_id)
    return EvidenceBundleAssembler(session, event_lookback_hours=72).assemble()


def test_demo_bundle_tells_the_billing_story(demo_session: Session) -> None:
    bundle = demo_bundle(demo_session)

    billing = next(
        a
        for a in bundle.anomalies
        if a.metric_key == "ticket_volume" and a.dimensions == {"category": "billing"}
    )
    assert billing.contributor_status == "available"
    top = next(
        c
        for c in bundle.contributors
        if c.anomaly_evidence_id == billing.evidence_id and c.family_key == "region+customer_tier"
    )
    assert top.segment == {"region": "emea", "customer_tier": "enterprise"}
    assert top.rank == 1

    deployment = next(e for e in bundle.related_events if e.event_type == "deployment")
    assert deployment.evidence_class == "contextual_event"
    assert deployment.causal is False
    assert deployment.details["version"] == "2.14.0"
    assert deployment.evidence_id in bundle.allowed_evidence_ids


def test_demo_bundle_is_stable_and_bounded(demo_session: Session) -> None:
    first = demo_bundle(demo_session)
    second = EvidenceBundleAssembler(demo_session, event_lookback_hours=72).assemble()

    assert first == second
    assert len(first.anomalies) <= first.limits.max_anomalies
    assert len(first.model_dump_json()) < 200_000
