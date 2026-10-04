"""Request correlation IDs and request logging (Spec 14). Uses the stub-session client."""

import logging

import pytest
from fastapi.testclient import TestClient

from app.core import request_context
from app.core.request_context import REQUEST_ID_HEADER, resolve_request_id


def _request_logs(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.getMessage() == "http.request"]


def test_a_request_id_is_generated_and_echoed(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger="app.http")
    response = client.get("/api/health")

    assert response.status_code == 200
    request_id = response.headers[REQUEST_ID_HEADER]
    assert len(request_id) == 32
    (record,) = _request_logs(caplog)
    assert record.__dict__["status_code"] == 200
    assert record.__dict__["path"] == "/api/health"
    assert record.__dict__["duration_ms"] >= 0


def test_a_plain_caller_request_id_is_reused(client: TestClient) -> None:
    response = client.get("/api/health", headers={REQUEST_ID_HEADER: "demo-run.1"})
    assert response.headers[REQUEST_ID_HEADER] == "demo-run.1"


@pytest.mark.parametrize("bad", ["has space", "x" * 65, "line\nbreak", "semi;colon", ""])
def test_unsafe_caller_request_ids_are_replaced(bad: str) -> None:
    resolved = resolve_request_id(bad)
    assert resolved != bad
    assert len(resolved) == 32


def test_query_strings_are_not_logged(client: TestClient, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="app.http")
    client.get("/api/health?api_key=sk-test-abcdefghijkl")
    (record,) = _request_logs(caplog)
    assert record.__dict__["path"] == "/api/health"
    # Only application records are checked; the test client logs its own request URL.
    app_records = [r for r in caplog.records if r.name.startswith("app.")]
    assert all("sk-test-abcdefghijkl" not in str(vars(r)) for r in app_records)


def test_failed_requests_are_logged_as_warnings(
    client_with_broken_db: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger="app.http")
    response = client_with_broken_db.get("/api/health")
    assert response.status_code == 503
    (record,) = _request_logs(caplog)
    assert record.levelno == logging.WARNING
    assert record.__dict__["status_code"] == 503


def test_a_logging_fault_never_breaks_the_request(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(*args: object, **kwargs: object) -> None:
        raise RuntimeError("log sink down")

    monkeypatch.setattr(request_context.logger, "log", broken)
    response = client.get("/api/health")
    assert response.status_code == 200
    assert REQUEST_ID_HEADER in response.headers
