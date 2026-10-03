"""Metrics endpoints: request validation, typed errors, and a DB-backed round trip."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.services.metrics.definitions import METRIC_REGISTRY
from tests.metrics.conftest import World

END = datetime(2026, 3, 10, tzinfo=UTC)

# --- validation (no database needed) -----------------------------------------------


def test_unknown_metric_key_is_404_with_code(client: TestClient) -> None:
    response = client.get("/api/metrics/csat")
    assert response.status_code == 404
    assert response.json()["code"] == "METRIC_NOT_FOUND"


def test_start_after_end_is_422_with_code(client: TestClient) -> None:
    response = client.get(
        "/api/metrics/ticket_volume",
        params={"start": "2026-03-10T00:00:00Z", "end": "2026-03-01T00:00:00Z"},
    )
    assert response.status_code == 422
    assert response.json()["code"] == "INVALID_WINDOW_RANGE"


@pytest.mark.parametrize(
    "params",
    [
        {"start": "2026-03-01T00:00:00"},  # naive datetime
        {"limit": 0},
        {"limit": 10_000},
        {"region": "mars"},
        {"category": "sales"},
    ],
)
def test_invalid_series_params_are_422(client: TestClient, params: dict[str, object]) -> None:
    assert client.get("/api/metrics/ticket_volume", params=params).status_code == 422


@pytest.mark.parametrize(
    "body",
    [
        {"window_end": "2026-03-10T00:00:00"},  # naive
        {"filters": {"region": "mars"}},
        {"filters": {"queue": "billing"}},  # unknown dimension
        {"unexpected": True},
    ],
)
def test_invalid_compute_body_is_422(client: TestClient, body: dict[str, object]) -> None:
    assert client.post("/api/metrics/compute", json=body).status_code == 422


def test_naive_overview_window_is_422(client: TestClient) -> None:
    response = client.get("/api/metrics/overview", params={"window_end": "2026-03-10T00:00:00"})
    assert response.status_code == 422


# --- database-backed ---------------------------------------------------------------


@pytest.mark.db
def test_overview_is_empty_before_any_computation(db_client: TestClient) -> None:
    response = db_client.get("/api/metrics/overview")
    assert response.status_code == 200
    body = response.json()
    assert body["window_end"] is None
    assert body["items"] == []
    assert set(body["missing_metric_keys"]) == set(METRIC_REGISTRY)


@pytest.mark.db
def test_compute_without_tickets_is_409(db_client: TestClient) -> None:
    response = db_client.post("/api/metrics/compute", json={})
    assert response.status_code == 409
    assert response.json()["code"] == "NO_SOURCE_DATA"


@pytest.mark.db
def test_compute_overview_series_round_trip(db_client: TestClient, world: World) -> None:
    for hours in range(0, 9 * 24, 2):
        world.ticket(END - timedelta(hours=hours + 1), resolved_after=timedelta(minutes=30))
    world.session.flush()

    computed = db_client.post("/api/metrics/compute", json={"window_end": END.isoformat()})
    assert computed.status_code == 200
    body = computed.json()
    assert body["window_end"] == "2026-03-10T00:00:00Z"
    assert {item["status"] for item in body["items"]} == {"computed"}

    again = db_client.post("/api/metrics/compute", json={"window_end": END.isoformat()})
    assert {item["status"] for item in again.json()["items"]} == {"reused"}

    overview = db_client.get("/api/metrics/overview").json()
    assert len(overview["items"]) == 8
    volume = next(i for i in overview["items"] if i["metric_key"] == "ticket_volume")
    assert volume["evidence_id"].startswith("MTR-")
    assert volume["value"] == 12
    assert volume["baseline_value"] == 12
    assert volume["change_pct"] == 0
    assert volume["provenance"]["current_window"]["end"] == "2026-03-10T00:00:00Z"

    series = db_client.get("/api/metrics/ticket_volume").json()
    assert series["definition"]["key"] == "ticket_volume"
    assert [p["evidence_id"] for p in series["points"]] == [volume["evidence_id"]]


@pytest.mark.db
def test_window_outside_data_is_422_with_code(db_client: TestClient, world: World) -> None:
    world.ticket(END - timedelta(hours=1))
    world.session.flush()
    response = db_client.post("/api/metrics/compute", json={"window_end": END.isoformat()})
    assert response.status_code == 422
    assert response.json()["code"] == "WINDOW_OUT_OF_RANGE"


@pytest.mark.db
def test_unknown_support_team_is_422_with_code(db_client: TestClient, world: World) -> None:
    for days in range(9):
        world.ticket(END - timedelta(days=days, hours=1))
    world.session.flush()
    response = db_client.post("/api/metrics/compute", json={"filters": {"support_team": "x"}})
    assert response.status_code == 422
    assert response.json()["code"] == "INVALID_DIMENSION_VALUE"
