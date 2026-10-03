"""Dashboard endpoint: typed response over HTTP, and the canonical demo scenario."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.services.anomalies.service import AnomalyService
from app.services.contributors.service import ContributorService
from app.services.dashboard.service import DashboardService
from tests.anomalies.conftest import END
from tests.metrics.conftest import World

pytestmark = pytest.mark.db


def test_empty_overview_over_http(db_client: TestClient) -> None:
    response = db_client.get("/api/dashboard/overview")

    assert response.status_code == 200
    body = response.json()
    assert body["window_end"] is None
    assert body["cards"] == []
    assert body["active_anomalies"] == []
    assert body["active_anomaly_total"] == 0
    assert [t["definition"]["key"] for t in body["trends"]] == [
        "ticket_volume",
        "sla_breach_rate",
        "open_backlog",
    ]


def test_overview_after_detection_over_http(db_client: TestClient, spike_world: World) -> None:
    detected = db_client.post("/api/anomalies/detect", json={"window_end": END.isoformat()})
    assert detected.status_code == 200

    body = db_client.get("/api/dashboard/overview").json()

    assert body["window_end"].startswith("2026-03-10T00:00:00")
    assert body["cards"][0]["metric_key"] == "ticket_volume"
    assert body["cards"][0]["evidence_id"].startswith("MTR-")
    assert all(p["evidence_id"].startswith("MTR-") for t in body["trends"] for p in t["points"])
    assert body["active_anomaly_total"] >= 1
    assert all(a["status"] == "active" for a in body["active_anomalies"])

    # Rows carry the triggering snapshot's values and the score's unit (no N+1 detail calls).
    billing = next(
        a
        for a in body["active_anomalies"]
        if a["metric_key"] == "ticket_volume" and a["dimensions"] == {"category": "billing"}
    )
    assert (billing["unit"], billing["value"], billing["baseline_value"]) == ("count", 20, 10)
    assert billing["score"] == pytest.approx(100.0)
    assert billing["score_comparison"] == "relative_pct"


def test_canonical_billing_anomaly_is_active_on_the_dashboard(demo_session: Session) -> None:
    detected = AnomalyService(demo_session).detect(None)
    billing = next(
        i
        for i in detected.items
        if i.metric_key == "ticket_volume" and i.filters == {"category": "billing"}
    )
    assert billing.anomaly is not None
    contributors = ContributorService(demo_session).compute(billing.anomaly.evidence_id)

    overview = DashboardService(demo_session).overview()

    assert billing.anomaly.evidence_id in {a.evidence_id for a in overview.active_anomalies}
    top = next(g for g in contributors.groups if g.family_key == "region+customer_tier")
    assert top.contributors[0].label == "EMEA / Enterprise"
