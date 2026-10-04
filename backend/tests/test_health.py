"""Health endpoint behaviour."""

from fastapi.testclient import TestClient

from app.services.health import DATABASE_UNAVAILABLE_CODE


def test_health_ok(client: TestClient) -> None:
    """A reachable database yields the typed 200 health response."""
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "opspilot-api",
        "database": "ok",
    }


def test_health_database_unavailable(client_with_broken_db: TestClient) -> None:
    """An unreachable database yields 503 with a stable error code."""
    response = client_with_broken_db.get("/api/health")

    assert response.status_code == 503

    body = response.json()
    assert body["code"] == DATABASE_UNAVAILABLE_CODE
    assert body["message"]
    # The failure must never be dressed up as healthy.
    assert body.get("database") != "ok"
    assert body.get("status") != "ok"


def test_health_route_is_under_api_prefix(client: TestClient) -> None:
    """Application endpoints are only reachable under the /api prefix."""
    assert client.get("/health").status_code == 404


def test_system_health_returns_503_with_typed_body_when_database_down(
    client_with_broken_db: TestClient,
) -> None:
    response = client_with_broken_db.get("/api/system/health")
    assert response.status_code == 503
    body = response.json()
    assert body["code"] == "DATABASE_UNAVAILABLE"
    assert body["health"]["status"] == "error"
    assert body["health"]["database"] == {"status": "error", "migration_revision": None}
    assert "connection refused" not in response.text
