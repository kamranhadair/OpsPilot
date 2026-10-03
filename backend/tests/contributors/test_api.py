"""Contributor endpoints: typed errors and a DB-backed compute/read round trip."""

from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.contributors.conftest import billing_anomaly_id
from tests.db import factories
from tests.metrics.conftest import World

pytestmark = pytest.mark.db


def compute_url(evidence_id: str) -> str:
    return f"/api/anomalies/{evidence_id}/contributors/compute"


def read_url(evidence_id: str) -> str:
    return f"/api/anomalies/{evidence_id}/contributors"


def test_compute_then_read_returns_the_same_groups(
    volume_world: World, db_client: TestClient
) -> None:
    anomaly_id = billing_anomaly_id(volume_world.session, "ticket_volume")

    computed = db_client.post(compute_url(anomaly_id))
    stored = db_client.get(read_url(anomaly_id))
    repeated = db_client.post(compute_url(anomaly_id))

    assert computed.status_code == stored.status_code == repeated.status_code == 200
    assert computed.json()["status"] == "computed"
    assert stored.json()["status"] == repeated.json()["status"] == "reused"
    assert stored.json()["groups"] == computed.json()["groups"] == repeated.json()["groups"]
    top = computed.json()["groups"][0]["contributors"][0]
    assert top["evidence_id"].startswith("SEG-")
    assert top["provenance"]["formula"]


@pytest.mark.parametrize("path", [compute_url, read_url])
def test_malformed_evidence_id_is_422(db_client: TestClient, path: Any) -> None:
    for bad in ("not-an-id", "MTR-000001"):
        response = db_client.post(path(bad)) if path is compute_url else db_client.get(path(bad))
        assert response.status_code == 422
        assert response.json()["code"] == "INVALID_EVIDENCE_ID"


def test_unknown_anomaly_is_404(db_client: TestClient) -> None:
    for response in (
        db_client.post(compute_url("ANOM-999999")),
        db_client.get(read_url("ANOM-999999")),
    ):
        assert response.status_code == 404
        assert response.json()["code"] == "ANOMALY_NOT_FOUND"


def test_read_before_compute_is_404_not_computed(
    volume_world: World, db_client: TestClient
) -> None:
    anomaly_id = billing_anomaly_id(volume_world.session, "ticket_volume")

    response = db_client.get(read_url(anomaly_id))

    assert response.status_code == 404
    assert response.json()["code"] == "CONTRIBUTORS_NOT_COMPUTED"


def test_metric_without_additive_split_is_422(world: World, db_client: TestClient) -> None:
    session: Session = world.session
    snapshot = factories.metric_snapshot(session, metric_key="resolution_minutes")
    session.add(snapshot)
    session.flush()
    anomaly = factories.anomaly(session, snapshot.id)
    session.add(anomaly)
    session.flush()

    response = db_client.post(compute_url(anomaly.evidence_id))

    assert response.status_code == 422
    assert response.json()["code"] == "SEGMENTATION_NOT_SUPPORTED"


def test_non_standard_snapshot_windows_are_409(world: World, db_client: TestClient) -> None:
    session: Session = world.session
    # A 48h current window is not the 24h window the analysis contract defines.
    snapshot = factories.metric_snapshot(
        session,
        metric_key="ticket_volume",
        dimensions_json={},
        window_end=factories.T0 + timedelta(hours=48),
    )
    session.add(snapshot)
    session.flush()
    anomaly = factories.anomaly(session, snapshot.id)
    session.add(anomaly)
    session.flush()

    response = db_client.post(compute_url(anomaly.evidence_id))

    assert response.status_code == 409
    assert response.json()["code"] == "CONTRIBUTOR_WINDOW_MISMATCH"
