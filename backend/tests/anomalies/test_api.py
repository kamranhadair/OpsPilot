"""Anomaly endpoints: request validation, typed errors, and a DB-backed round trip."""

from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.anomalies.conftest import END
from tests.metrics.conftest import World

# --- validation (no database needed) ------------------------------------------------


@pytest.mark.parametrize(
    "body",
    [
        {"window_end": "2026-03-10T00:00:00"},  # naive
        {"unexpected": True},
    ],
)
def test_invalid_detect_body_is_422(client: TestClient, body: dict[str, object]) -> None:
    assert client.post("/api/anomalies/detect", json=body).status_code == 422


@pytest.mark.parametrize(
    "params",
    [
        {"severity": "bogus"},
        {"status": "bogus"},
        {"limit": 0},
        {"limit": 10_000},
        {"offset": -1},
        {"start": "2026-03-01T00:00:00"},  # naive
    ],
)
def test_invalid_list_params_are_422(client: TestClient, params: dict[str, object]) -> None:
    assert client.get("/api/anomalies", params=params).status_code == 422


def test_unknown_metric_key_is_422_with_code(client: TestClient) -> None:
    response = client.get("/api/anomalies", params={"metric_key": "csat"})
    assert response.status_code == 422
    assert response.json()["code"] == "INVALID_METRIC_KEY"


def test_start_after_end_is_422_with_code(client: TestClient) -> None:
    response = client.get(
        "/api/anomalies",
        params={"start": "2026-03-10T00:00:00Z", "end": "2026-03-01T00:00:00Z"},
    )
    assert response.status_code == 422
    assert response.json()["code"] == "INVALID_DATE_RANGE"


@pytest.mark.parametrize("evidence_id", ["ANOM-1", "MTR-000001", "nonsense"])
def test_malformed_or_wrong_type_evidence_id_is_422(client: TestClient, evidence_id: str) -> None:
    response = client.get(f"/api/anomalies/{evidence_id}")
    assert response.status_code == 422
    assert response.json()["code"] == "INVALID_EVIDENCE_ID"


# --- DB-backed round trip -----------------------------------------------------------


def detect(client: TestClient, **body: Any) -> dict[str, Any]:
    response = client.post("/api/anomalies/detect", json={"window_end": END.isoformat(), **body})
    assert response.status_code == 200, response.text
    return dict(response.json())


@pytest.mark.db
def test_detect_then_list_and_detail(db_client: TestClient, spike_world: World) -> None:
    detected = detect(db_client)
    assert detected["detected_count"] >= 1
    assert detected["window_end"].startswith("2026-03-10T00:00:00")

    listing = db_client.get("/api/anomalies")
    assert listing.status_code == 200
    body = listing.json()
    assert body["total"] == detected["detected_count"] == len(body["items"])
    billing = next(
        item
        for item in body["items"]
        if item["metric_key"] == "ticket_volume" and item["dimensions"] == {"category": "billing"}
    )
    assert billing["severity"] == "high"

    detail = db_client.get(f"/api/anomalies/{billing['evidence_id']}")
    assert detail.status_code == 200
    d = detail.json()
    assert d["evidence_id"] == billing["evidence_id"]
    assert d["threshold"]["detector_key"] == "pct_change.v1"
    assert d["threshold"]["triggered_tier"] == "high"
    assert d["threshold"]["high_threshold"] == 50.0
    assert d["snapshot"]["evidence_id"] == d["metric_evidence_id"]
    assert d["snapshot"]["change_pct"] == pytest.approx(100.0)
    assert "high threshold of 50%" in d["explanation"]


@pytest.mark.db
def test_detect_is_idempotent_over_http(db_client: TestClient, spike_world: World) -> None:
    first = detect(db_client)
    second = detect(db_client)
    assert second["detected_count"] == 0
    assert second["reused_count"] == first["detected_count"]
    assert db_client.get("/api/anomalies").json()["total"] == first["detected_count"]


@pytest.mark.db
def test_list_filters(db_client: TestClient, spike_world: World) -> None:
    detect(db_client)

    high = db_client.get("/api/anomalies", params={"severity": "high"}).json()
    assert high["items"] and all(i["severity"] == "high" for i in high["items"])
    assert db_client.get("/api/anomalies", params={"severity": "critical"}).json()["total"] == 0

    active = db_client.get("/api/anomalies", params={"status": "active"}).json()
    assert active["total"] > 0
    assert db_client.get("/api/anomalies", params={"status": "resolved"}).json()["total"] == 0

    by_metric = db_client.get("/api/anomalies", params={"metric_key": "ticket_volume"}).json()
    assert by_metric["items"] and all(
        i["metric_key"] == "ticket_volume" for i in by_metric["items"]
    )
    assert (
        db_client.get("/api/anomalies", params={"metric_key": "resolution_minutes"}).json()["total"]
        == 0
    )

    inside = db_client.get(
        "/api/anomalies",
        params={"start": END.isoformat(), "end": (END + timedelta(hours=1)).isoformat()},
    ).json()
    assert inside["total"] == active["total"]
    after = db_client.get(
        "/api/anomalies", params={"start": (END + timedelta(days=1)).isoformat()}
    ).json()
    before = db_client.get("/api/anomalies", params={"end": (END - timedelta(days=1)).isoformat()})
    assert after["total"] == 0
    assert before.json()["total"] == 0


@pytest.mark.db
def test_list_pagination(db_client: TestClient, spike_world: World) -> None:
    detect(db_client)
    everything = db_client.get("/api/anomalies").json()
    assert everything["total"] >= 2
    page = db_client.get("/api/anomalies", params={"limit": 1, "offset": 1}).json()
    assert page["total"] == everything["total"]
    assert page["limit"] == 1 and page["offset"] == 1
    assert [i["evidence_id"] for i in page["items"]] == [everything["items"][1]["evidence_id"]]


@pytest.mark.db
def test_unknown_anomaly_is_404(db_client: TestClient, spike_world: World) -> None:
    response = db_client.get("/api/anomalies/ANOM-999999")
    assert response.status_code == 404
    assert response.json()["code"] == "ANOMALY_NOT_FOUND"


@pytest.mark.db
def test_detect_without_tickets_is_409(db_client: TestClient, clean_db: object) -> None:
    response = db_client.post("/api/anomalies/detect", json={})
    assert response.status_code == 409
    assert response.json()["code"] == "NO_SOURCE_DATA"


@pytest.mark.db
def test_detect_outside_data_is_422(db_client: TestClient, spike_world: World) -> None:
    response = db_client.post(
        "/api/anomalies/detect", json={"window_end": (END + timedelta(days=30)).isoformat()}
    )
    assert response.status_code == 422
    assert response.json()["code"] == "WINDOW_OUT_OF_RANGE"
