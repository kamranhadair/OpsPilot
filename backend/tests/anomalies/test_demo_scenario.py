"""The planted Billing scenario in the seeded demo dataset, end to end."""

import pytest
from sqlalchemy.orm import Session

from app.models.enums import AnomalySeverity
from app.schemas.anomalies import AnomalyDetectItem
from app.services.anomalies.service import AnomalyService

pytestmark = pytest.mark.db

ESCALATED = {AnomalySeverity.HIGH, AnomalySeverity.CRITICAL}


def slice_items(items: list[AnomalyDetectItem], **filters: str) -> list[AnomalyDetectItem]:
    return [i for i in items if i.filters == filters]


def test_planted_billing_anomaly_is_detected_as_high_or_higher(demo_session: Session) -> None:
    response = AnomalyService(demo_session).detect(None)
    assert response.window_end.isoformat().startswith("2026-10-04T00:00:00")

    volume = next(
        i
        for i in slice_items(response.items, category="billing")
        if i.metric_key == "ticket_volume"
    )
    assert volume.anomaly is not None
    assert volume.anomaly.severity in ESCALATED
    assert volume.anomaly.score is not None and volume.anomaly.score >= 50.0


def test_billing_sla_breach_hits_the_documented_critical_rule(demo_session: Session) -> None:
    response = AnomalyService(demo_session).detect(None)
    sla = next(
        i
        for i in slice_items(response.items, category="billing")
        if i.metric_key == "sla_breach_rate"
    )
    assert sla.anomaly is not None
    assert sla.anomaly.severity is AnomalySeverity.CRITICAL
    assert "25%" in sla.anomaly.explanation


def test_overall_volume_hides_the_spike_but_billing_slice_does_not(demo_session: Session) -> None:
    response = AnomalyService(demo_session).detect(None)
    overall = next(i for i in slice_items(response.items) if i.metric_key == "ticket_volume")
    assert overall.anomaly is None  # why detection also runs per queue


def test_normal_queues_do_not_become_high_or_critical(demo_session: Session) -> None:
    response = AnomalyService(demo_session).detect(None)
    for category in ("technical", "integration", "account"):
        items = slice_items(response.items, category=category)
        assert items
        flagged = [i for i in items if i.anomaly is not None]
        assert not [i for i in flagged if i.anomaly and i.anomaly.severity in ESCALATED]
        assert not flagged  # the planted scenario is Billing-only


def test_demo_detection_is_idempotent(demo_session: Session) -> None:
    service = AnomalyService(demo_session)
    first = service.detect(None)
    second = service.detect(None)
    assert first.detected_count > 0
    assert second.detected_count == 0
    assert second.reused_count == first.detected_count
