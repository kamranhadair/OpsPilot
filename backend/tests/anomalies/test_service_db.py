"""Service-level behaviour against PostgreSQL: persistence, evidence IDs, idempotency."""

from datetime import timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Anomaly, MetricSnapshot
from app.models.enums import AnomalySeverity, AnomalyStatus
from app.schemas.anomalies import AnomalyDetectItem, AnomalyDetectResponse
from app.services.anomalies.detector import SkipReason, ThresholdDetails
from app.services.anomalies.service import AnomalyService
from app.services.metrics.errors import NoSourceDataError, WindowOutOfRangeError
from tests.anomalies.conftest import END
from tests.metrics.conftest import World

pytestmark = pytest.mark.db


def find(response: AnomalyDetectResponse, metric_key: str, **filters: str) -> AnomalyDetectItem:
    matches = [
        item for item in response.items if item.metric_key == metric_key and item.filters == filters
    ]
    assert len(matches) == 1, (metric_key, filters, len(matches))
    return matches[0]


def anomaly_count(session: Session) -> int:
    return session.execute(select(func.count()).select_from(Anomaly)).scalar_one()


def test_billing_spike_is_detected_as_high(spike_world: World) -> None:
    response = AnomalyService(spike_world.session).detect(END)

    item = find(response, "ticket_volume", category="billing")
    assert item.status == "detected"
    assert item.anomaly is not None
    assert item.anomaly.severity is AnomalySeverity.HIGH
    assert item.anomaly.status is AnomalyStatus.ACTIVE
    assert item.anomaly.score == pytest.approx(100.0)
    assert item.anomaly.evidence_id.startswith("ANOM-")
    assert item.metric_evidence_id is not None and item.metric_evidence_id.startswith("MTR-")
    assert item.anomaly.metric_evidence_id == item.metric_evidence_id
    assert "pct_change.v1" in item.anomaly.explanation


def test_anomaly_row_references_its_snapshot_and_stores_the_rule(spike_world: World) -> None:
    session = spike_world.session
    response = AnomalyService(session).detect(END)
    item = find(response, "ticket_volume", category="billing")
    assert item.anomaly is not None

    row = session.execute(
        select(Anomaly).where(Anomaly.evidence_id == item.anomaly.evidence_id)
    ).scalar_one()
    snapshot = session.get(MetricSnapshot, row.metric_snapshot_id)
    assert snapshot is not None
    assert snapshot.evidence_id == item.metric_evidence_id
    assert snapshot.metric_key == "ticket_volume"
    assert snapshot.dimensions_json == {"category": "billing"}
    assert row.detector_key == "pct_change.v1"
    assert float(row.score or 0) == pytest.approx(100.0)

    threshold = ThresholdDetails.model_validate(row.threshold_json)
    assert threshold.triggered_tier == "high"
    assert (threshold.medium_threshold, threshold.high_threshold) == (30.0, 50.0)


def test_quiet_queue_is_not_flagged(spike_world: World) -> None:
    response = AnomalyService(spike_world.session).detect(END)
    item = find(response, "ticket_volume", category="technical")
    assert item.status == "skipped"
    assert item.skip_reason is SkipReason.BELOW_THRESHOLD
    assert item.anomaly is None


def test_unconfigured_metrics_are_reported_not_hidden(spike_world: World) -> None:
    response = AnomalyService(spike_world.session).detect(END)
    for key in ("first_response_minutes", "resolution_minutes"):
        item = find(response, key)
        assert item.status == "skipped"
        assert item.skip_reason is SkipReason.NOT_CONFIGURED


def test_small_billing_rate_sample_is_guarded(spike_world: World) -> None:
    response = AnomalyService(spike_world.session).detect(END)
    # Only 20 Billing tickets in the window: below the 30-ticket rate guard (and no change).
    item = find(response, "sla_breach_rate", category="billing")
    assert item.status == "skipped"


def test_detection_is_idempotent(spike_world: World) -> None:
    session = spike_world.session
    service = AnomalyService(session)
    first = service.detect(END)
    rows_after_first = anomaly_count(session)
    snapshots_after_first = session.execute(
        select(func.count()).select_from(MetricSnapshot)
    ).scalar_one()
    assert first.detected_count > 0 and first.reused_count == 0

    second = service.detect(END)
    assert anomaly_count(session) == rows_after_first
    assert (
        session.execute(select(func.count()).select_from(MetricSnapshot)).scalar_one()
        == snapshots_after_first
    )
    assert second.detected_count == 0
    assert second.reused_count == first.detected_count
    assert second.skipped_count == first.skipped_count

    ids_first = {i.anomaly.evidence_id for i in first.items if i.anomaly}
    ids_second = {i.anomaly.evidence_id for i in second.items if i.anomaly}
    assert ids_first == ids_second


def test_redetection_does_not_reset_a_reviewed_anomaly(spike_world: World) -> None:
    session = spike_world.session
    service = AnomalyService(session)
    first = service.detect(END)
    item = find(first, "ticket_volume", category="billing")
    assert item.anomaly is not None

    row = session.execute(
        select(Anomaly).where(Anomaly.evidence_id == item.anomaly.evidence_id)
    ).scalar_one()
    row.status = AnomalyStatus.ACKNOWLEDGED
    session.flush()

    again = find(service.detect(END), "ticket_volume", category="billing")
    assert again.status == "reused"
    assert again.anomaly is not None
    assert again.anomaly.status is AnomalyStatus.ACKNOWLEDGED
    assert again.anomaly.evidence_id == item.anomaly.evidence_id


def test_detect_defaults_to_the_end_of_available_data(spike_world: World) -> None:
    response = AnomalyService(spike_world.session).detect(None)
    assert response.window_end == END
    assert find(response, "ticket_volume", category="billing").status == "detected"


def test_window_outside_the_data_is_rejected(spike_world: World) -> None:
    with pytest.raises(WindowOutOfRangeError):
        AnomalyService(spike_world.session).detect(END + timedelta(days=30))


def test_no_tickets_is_a_typed_error(clean_db: Session) -> None:
    with pytest.raises(NoSourceDataError):
        AnomalyService(clean_db).detect(None)
