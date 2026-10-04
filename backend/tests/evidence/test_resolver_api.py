"""GET /api/evidence/{evidence_id}: typed provenance envelope for MTR/ANOM/SEG/EVT."""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.schemas.evidence import CONTRIBUTOR_CONTEXT_NOTE, EVENT_CONTEXT_NOTE, EvidenceDetailOut
from app.services.anomalies.service import AnomalyService
from app.services.contributors.service import ContributorService
from tests.db import factories
from tests.evidence.conftest import END, detect_billing_volume
from tests.metrics.conftest import World

pytestmark = pytest.mark.db


def _get(client: TestClient, evidence_id: str) -> EvidenceDetailOut:
    response = client.get(f"/api/evidence/{evidence_id}")
    assert response.status_code == 200, response.json()
    return EvidenceDetailOut.model_validate(response.json())


def _values(detail: EvidenceDetailOut) -> dict[str, object]:
    return {v.key: v.value for v in detail.values}


def test_metric_resolves_with_window_values_sample_and_formula(
    volume_world: World, no_incidents: Session, db_client: TestClient
) -> None:
    anomaly_id = detect_billing_volume(volume_world)
    anomaly = AnomalyService(volume_world.session).get(anomaly_id)

    detail = _get(db_client, anomaly.metric_evidence_id)

    snapshot = anomaly.snapshot
    assert detail.evidence_type == "MTR" and detail.evidence_class == "observed_fact"
    assert detail.window is not None and detail.window.end == END
    assert detail.baseline_window is not None
    assert detail.dimensions == {"category": "billing"}
    assert detail.sample_size == snapshot.sample_size
    assert _values(detail)["value"] == snapshot.value
    assert _values(detail)["baseline_value"] == snapshot.baseline_value
    assert detail.method.kind == "metric_calculation"
    assert detail.method.formula == snapshot.provenance.definition.formula
    assert detail.provenance.evidence_type == "MTR"
    assert detail.contextual_disclaimer is None


def test_anomaly_resolves_with_detector_metadata(
    volume_world: World, no_incidents: Session, db_client: TestClient
) -> None:
    anomaly_id = detect_billing_volume(volume_world)
    anomaly = AnomalyService(volume_world.session).get(anomaly_id)

    detail = _get(db_client, anomaly_id)

    assert detail.evidence_type == "ANOM"
    assert detail.method.kind == "anomaly_detector"
    assert detail.method.name == anomaly.detector_key
    assert detail.method.description == anomaly.explanation
    assert _values(detail)["severity"] == anomaly.severity.value
    assert detail.related_evidence_ids == [anomaly.metric_evidence_id]
    assert detail.sample_size == anomaly.snapshot.sample_size
    assert detail.provenance.evidence_type == "ANOM"


def test_segment_resolves_with_contribution_metadata(
    volume_world: World, no_incidents: Session, db_client: TestClient
) -> None:
    anomaly_id = detect_billing_volume(volume_world)
    analysis = ContributorService(volume_world.session).get(anomaly_id)
    group = analysis.groups[0]
    top = group.contributors[0]

    detail = _get(db_client, top.evidence_id)

    assert detail.evidence_type == "SEG"
    assert _values(detail)["contribution_pct"] == top.contribution_pct
    assert _values(detail)["rank"] == top.rank
    assert detail.method.kind == "contribution" and detail.method.formula == group.formula
    assert detail.sample_size == top.provenance.sample
    assert detail.related_evidence_ids == [anomaly_id, analysis.metric_evidence_id]
    assert detail.contextual_disclaimer == CONTRIBUTOR_CONTEXT_NOTE
    assert detail.window is not None and detail.window.end == END


def test_event_resolves_with_disclaimer_and_allow_listed_details_only(
    volume_world: World, no_incidents: Session, db_client: TestClient
) -> None:
    session = volume_world.session
    row = factories.incident(
        session,
        occurred_at=END - timedelta(hours=30),
        metadata_json={"version": "2.4.0", "ticket_body": "secret customer text", "owner": "x"},
    )
    session.add(row)
    session.flush()

    detail = _get(db_client, row.evidence_id)

    assert detail.evidence_type == "EVT" and detail.evidence_class == "contextual_event"
    assert detail.contextual_disclaimer == EVENT_CONTEXT_NOTE
    assert detail.window is None and detail.sample_size is None
    assert detail.provenance.evidence_type == "EVT"
    assert detail.provenance.details == {"version": "2.4.0"}
    response = db_client.get(f"/api/evidence/{row.evidence_id}")
    assert "secret customer text" not in response.text


@pytest.mark.parametrize("evidence_id", ["MTR-999999", "ANOM-999999", "SEG-999999", "EVT-999999"])
def test_unknown_id_is_404_with_stable_code(
    no_incidents: Session, db_client: TestClient, evidence_id: str
) -> None:
    response = db_client.get(f"/api/evidence/{evidence_id}")
    assert response.status_code == 404
    assert response.json()["code"] == "EVIDENCE_NOT_FOUND"


@pytest.mark.parametrize("evidence_id", ["FOO-000001", "MTR-1", "mtr-000001"])
def test_malformed_id_is_422(
    no_incidents: Session, db_client: TestClient, evidence_id: str
) -> None:
    response = db_client.get(f"/api/evidence/{evidence_id}")
    assert response.status_code == 422
    assert response.json()["code"] == "INVALID_EVIDENCE_ID"
