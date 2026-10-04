"""Demo status/run endpoints: environment guard, typed bodies and errors."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.routes.briefs import get_client_factory
from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.main import app
from app.models import ProposedAction
from tests.demo.conftest import (
    LLM_SETTINGS,
    NO_LLM_SETTINGS,
    PROD_SETTINGS,
    StubBriefClient,
    count,
)

pytestmark = pytest.mark.db


def client_for(session: Session, settings: Settings) -> Iterator[TestClient]:
    app.dependency_overrides[get_db] = lambda: session
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_client_factory] = lambda: lambda: StubBriefClient()
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


@pytest.fixture
def api(seeded: Session) -> Iterator[TestClient]:
    yield from client_for(seeded, LLM_SETTINGS)


@pytest.fixture
def prod_api(seeded: Session) -> Iterator[TestClient]:
    yield from client_for(seeded, PROD_SETTINGS)


def test_status_before_and_after_analysis(api: TestClient) -> None:
    before = api.get("/api/demo/status")
    assert before.status_code == 200
    assert before.json() == {
        "enabled": True,
        "dataset_seeded": True,
        "analysis_window_end": None,
        "llm_configured": True,
    }

    run = api.post("/api/demo/analysis/run")
    assert run.status_code == 200
    body = run.json()
    assert body["brief"]["state"] == "generated"
    assert body["brief"]["status"] == "valid"
    assert body["anomalies"][0]["evidence_id"].startswith("ANOM-")

    after = api.get("/api/demo/status").json()
    assert after["analysis_window_end"] is not None


def test_run_does_not_create_actions(api: TestClient, seeded: Session) -> None:
    assert api.post("/api/demo/analysis/run").status_code == 200
    assert count(seeded, ProposedAction) == 0


@pytest.mark.parametrize(
    ("method", "path"), [("get", "/api/demo/status"), ("post", "/api/demo/analysis/run")]
)
def test_demo_endpoints_are_unavailable_outside_demo_environments(
    prod_api: TestClient, method: str, path: str
) -> None:
    response = getattr(prod_api, method)(path)
    assert response.status_code == 404
    assert response.json()["code"] == "DEMO_DISABLED"


def test_run_without_source_data_is_a_typed_conflict(clean_db: Session) -> None:
    for client in client_for(clean_db, NO_LLM_SETTINGS):
        response = client.post("/api/demo/analysis/run")
        assert response.status_code == 409
        assert response.json()["code"] == "NO_SOURCE_DATA"
        status = client.get("/api/demo/status").json()
        assert status["dataset_seeded"] is False


def test_there_is_no_reset_endpoint(api: TestClient) -> None:
    assert not any("reset" in path for path in app.openapi()["paths"])
    assert api.post("/api/demo/reset").status_code in (404, 405)
