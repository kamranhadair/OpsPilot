"""GET /api/evidence-bundles/latest: safe inspection, demo/development only."""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.main import app
from app.schemas.evidence import EvidenceBundle
from tests.db import factories
from tests.evidence.conftest import END, detect_billing_volume
from tests.metrics.conftest import World

pytestmark = pytest.mark.db

URL = "/api/evidence-bundles/latest"


def test_latest_returns_a_valid_bundle(
    volume_world: World, no_incidents: Session, db_client: TestClient
) -> None:
    detect_billing_volume(volume_world)
    volume_world.session.add(
        factories.incident(volume_world.session, occurred_at=END - timedelta(hours=30))
    )
    volume_world.session.flush()

    response = db_client.get(URL)

    assert response.status_code == 200
    bundle = EvidenceBundle.model_validate(response.json())
    assert bundle.allowed_evidence_ids
    assert bundle.related_events[0].causal is False


def test_latest_on_an_empty_database_is_an_empty_bundle(
    no_incidents: Session, db_client: TestClient
) -> None:
    response = db_client.get(URL)

    assert response.status_code == 200
    assert response.json()["allowed_evidence_ids"] == []
    assert response.json()["analysis_window"] is None


def test_latest_is_disabled_outside_demo_environments(
    no_incidents: Session, db_client: TestClient
) -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(environment="production")
    try:
        response = db_client.get(URL)
    finally:
        app.dependency_overrides.pop(get_settings, None)

    assert response.status_code == 404
    assert response.json()["code"] == "EVIDENCE_INSPECTION_DISABLED"
