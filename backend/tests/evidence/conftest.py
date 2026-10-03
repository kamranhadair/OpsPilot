"""Fixtures for evidence-bundle tests: reuse the contributor/anomaly ticket worlds."""

import pytest
from sqlalchemy.orm import Session

from app.models import Incident
from app.services.anomalies.service import AnomalyService
from app.services.contributors.service import ContributorService
from tests.contributors.conftest import (  # noqa: F401  (re-exported fixtures)
    END,
    breach_world,
    clean_db,
    db_client,
    db_session,
    demo_session,
    engine,
    test_db_url,
    volume_world,
    world,
)
from tests.metrics.conftest import World


@pytest.fixture
def no_incidents(clean_db: Session) -> Session:  # noqa: F811
    """Make sure no timeline events leak in from other data in the test database."""
    clean_db.execute(Incident.__table__.delete())  # type: ignore[attr-defined]
    clean_db.flush()
    return clean_db


def detect_billing_volume(target: World, *, compute_contributors: bool = True) -> str:
    """Detect over the test window; optionally compute contributors. Returns the ANOM- ID."""
    session = target.session
    response = AnomalyService(session).detect(END)
    item = next(
        i
        for i in response.items
        if i.metric_key == "ticket_volume" and i.filters == {"category": "billing"}
    )
    assert item.anomaly is not None
    if compute_contributors:
        ContributorService(session).compute(item.anomaly.evidence_id)
    return item.anomaly.evidence_id
