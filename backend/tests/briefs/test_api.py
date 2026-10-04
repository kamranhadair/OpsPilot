"""Brief endpoints: typed bodies, stable error codes, no fabricated output."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.routes.briefs import get_client_factory
from app.core.config import get_settings
from app.integrations.llm.base import (
    LLMMalformedOutputError,
    LLMProviderError,
    LLMRateLimitedError,
    LLMTimeoutError,
)
from app.main import app
from app.models import Brief, LLMTrace
from app.models.enums import BriefStatus, ClaimType, ClaimValidationStatus
from app.schemas.briefs import BriefGenerateResponse, BriefOut, DraftClaim
from tests.briefs.conftest import FakeBriefClient, draft_output, install_client, make_settings
from tests.evidence.conftest import detect_billing_volume
from tests.metrics.conftest import World

pytestmark = pytest.mark.db

GENERATE = "/api/briefs/generate"


def _claim(anomaly_id: str) -> DraftClaim:
    return DraftClaim(claim_type=ClaimType.OBSERVATION, text="t", evidence_ids=[anomaly_id])


def test_generate_returns_a_typed_validated_brief(volume_world: World, api: TestClient) -> None:
    anomaly_id = detect_billing_volume(volume_world)
    install_client(FakeBriefClient(draft_output(_claim(anomaly_id))))

    response = api.post(GENERATE)

    assert response.status_code == 201
    body = BriefGenerateResponse.model_validate(response.json())
    assert body.status == BriefStatus.VALID
    assert body.claims[0].validation_status == ClaimValidationStatus.VALID
    assert body.claims[0].evidence_ids == [anomaly_id]
    assert body.attention_items == ["Look at billing"]


def test_get_by_id_and_latest_return_the_brief_without_attention_items(
    volume_world: World, api: TestClient
) -> None:
    anomaly_id = detect_billing_volume(volume_world)
    install_client(FakeBriefClient(draft_output(_claim(anomaly_id))))
    brief_id = api.post(GENERATE).json()["id"]

    by_id = api.get(f"/api/briefs/{brief_id}")
    latest = api.get("/api/briefs/latest")

    for response in (by_id, latest):
        assert response.status_code == 200
        body = BriefOut.model_validate(response.json())
        assert body.id == brief_id and body.status == BriefStatus.VALID
        assert "attention_items" not in response.json()


def test_not_found_and_invalid_id(api: TestClient) -> None:
    missing = api.get("/api/briefs/999999")
    assert missing.status_code == 404 and missing.json()["code"] == "BRIEF_NOT_FOUND"
    none_yet = api.get("/api/briefs/latest")
    assert none_yet.status_code == 404 and none_yet.json()["code"] == "NO_VALIDATED_BRIEF"
    assert api.get("/api/briefs/0").status_code == 422


@pytest.mark.parametrize(
    ("error", "status", "code"),
    [
        (LLMTimeoutError("t"), 504, "LLM_TIMEOUT"),
        (LLMRateLimitedError("r"), 429, "LLM_RATE_LIMITED"),
        (LLMMalformedOutputError("m"), 502, "LLM_MALFORMED_OUTPUT"),
        (LLMProviderError("p"), 502, "LLM_PROVIDER_ERROR"),
    ],
)
def test_provider_failures_are_typed_errors(
    volume_world: World,
    api: TestClient,
    clean_briefs: Session,
    error: Exception,
    status: int,
    code: str,
) -> None:
    detect_billing_volume(volume_world)
    install_client(FakeBriefClient(error=error))  # type: ignore[arg-type]

    response = api.post(GENERATE)

    assert response.status_code == status
    assert response.json()["code"] == code
    assert clean_briefs.execute(select(func.count()).select_from(Brief)).scalar_one() == 0
    assert clean_briefs.execute(select(func.count()).select_from(LLMTrace)).scalar_one() == 1


def test_missing_key_is_an_explicit_not_configured_error(
    volume_world: World, api: TestClient, clean_briefs: Session
) -> None:
    detect_billing_volume(volume_world)
    client = FakeBriefClient(draft_output())
    install_client(client)
    app.dependency_overrides[get_settings] = lambda: make_settings(openai_api_key=None)

    response = api.post(GENERATE)

    assert response.status_code == 503
    assert response.json()["code"] == "LLM_NOT_CONFIGURED"
    assert client.bundles == []
    assert clean_briefs.execute(select(func.count()).select_from(Brief)).scalar_one() == 0


def test_real_factory_without_key_never_reaches_the_network(
    volume_world: World, api: TestClient
) -> None:
    """With the default (real) client factory and no key, the answer is the same error."""
    detect_briefs_world = detect_billing_volume(volume_world)
    assert detect_briefs_world
    app.dependency_overrides.pop(get_client_factory, None)
    app.dependency_overrides[get_settings] = lambda: make_settings(openai_api_key=None)

    response = api.post(GENERATE)

    assert response.status_code == 503
    assert response.json()["code"] == "LLM_NOT_CONFIGURED"


def test_empty_evidence_is_a_conflict(api: TestClient) -> None:
    client = FakeBriefClient(draft_output())
    install_client(client)

    response = api.post(GENERATE)

    assert response.status_code == 409
    assert response.json()["code"] == "EVIDENCE_BUNDLE_EMPTY"
    assert client.bundles == []


def test_fabricated_id_returns_a_typed_invalid_brief(volume_world: World, api: TestClient) -> None:
    anomaly_id = detect_billing_volume(volume_world)
    install_client(FakeBriefClient(draft_output(_claim(anomaly_id), _claim("ANOM-999999"))))

    response = api.post(GENERATE)

    assert response.status_code == 201
    body = BriefGenerateResponse.model_validate(response.json())
    assert body.status == BriefStatus.INVALID
    assert [c.validation_status for c in body.claims] == [
        ClaimValidationStatus.VALID,
        ClaimValidationStatus.INVALID,
    ]
    assert body.claims[1].evidence_ids == ["ANOM-999999"]
    (issue,) = body.validation_errors
    assert (issue.code, issue.evidence_id, issue.claim_ordinal) == (
        "EVIDENCE_NOT_IN_BUNDLE",
        "ANOM-999999",
        1,
    )
    stored = api.get(f"/api/briefs/{body.id}")
    assert stored.status_code == 200 and stored.json()["status"] == "invalid"
    assert stored.json()["claims"][1]["validation_errors"][0]["code"] == "EVIDENCE_NOT_IN_BUNDLE"


def test_latest_skips_a_newer_invalid_brief(volume_world: World, api: TestClient) -> None:
    anomaly_id = detect_billing_volume(volume_world)
    install_client(FakeBriefClient(draft_output(_claim(anomaly_id))))
    valid_id = api.post(GENERATE).json()["id"]
    install_client(FakeBriefClient(draft_output(_claim("MTR-999999"))))
    invalid_id = api.post(GENERATE).json()["id"]
    assert invalid_id > valid_id

    latest = api.get("/api/briefs/latest")

    assert latest.status_code == 200
    assert latest.json()["id"] == valid_id and latest.json()["status"] == "valid"


def test_latest_with_only_invalid_briefs_is_not_found(volume_world: World, api: TestClient) -> None:
    detect_billing_volume(volume_world)
    install_client(FakeBriefClient(draft_output(_claim("MTR-999999"))))
    assert api.post(GENERATE).json()["status"] == "invalid"

    latest = api.get("/api/briefs/latest")

    assert latest.status_code == 404 and latest.json()["code"] == "NO_VALIDATED_BRIEF"
