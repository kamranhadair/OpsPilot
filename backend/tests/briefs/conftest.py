"""Fixtures for brief tests: a fake model client and offline-safe settings."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.routes.briefs import get_client_factory
from app.core.config import Settings, get_settings
from app.integrations.llm.base import BriefLLMResult, LLMError
from app.main import app
from app.models import Brief, BriefClaim, LLMTrace
from app.schemas.briefs import BriefDraftOutput, DraftClaim
from app.schemas.evidence import EvidenceBundle
from tests.evidence.conftest import (  # noqa: F401  (re-exported fixtures)
    END,
    breach_world,
    clean_db,
    db_client,
    db_session,
    demo_session,
    detect_billing_volume,
    engine,
    no_incidents,
    test_db_url,
    volume_world,
    world,
)


def make_settings(**overrides: object) -> Settings:
    """Settings that ignore any local .env so tests never see a real key."""
    values: dict[str, object] = {
        "openai_api_key": "test-key-not-real",
        "openai_model": "test-model",
        **overrides,
    }
    return Settings(_env_file=None, **values)  # type: ignore[arg-type]


def draft_output(*claims: DraftClaim, attention: list[str] | None = None) -> BriefDraftOutput:
    return BriefDraftOutput(
        headline="Billing volume is elevated",
        summary="Billing ticket volume rose against baseline.",
        claims=list(claims),
        attention_items=attention if attention is not None else ["Look at billing"],
    )


class FakeBriefClient:
    """Records every bundle it is handed; returns a canned result or raises."""

    def __init__(self, output: BriefDraftOutput | None = None, error: LLMError | None = None):
        self.output = output
        self.error = error
        self.bundles: list[EvidenceBundle] = []

    def generate_brief(self, bundle: EvidenceBundle) -> BriefLLMResult:
        self.bundles.append(bundle)
        if self.error is not None:
            raise self.error
        assert self.output is not None
        return BriefLLMResult(
            output=self.output,
            model_name="test-model",
            input_tokens=123,
            output_tokens=45,
            latency_ms=7,
        )


@pytest.fixture
def clean_briefs(no_incidents: Session) -> Session:  # noqa: F811
    for model in (LLMTrace, BriefClaim, Brief):
        no_incidents.execute(model.__table__.delete())  # type: ignore[attr-defined]
    no_incidents.flush()
    return no_incidents


@pytest.fixture
def api(clean_briefs: Session, db_client: TestClient) -> Iterator[TestClient]:  # noqa: F811
    """API client with configured settings; tests install their own fake client."""
    app.dependency_overrides[get_settings] = lambda: make_settings()
    yield db_client
    app.dependency_overrides.pop(get_settings, None)
    app.dependency_overrides.pop(get_client_factory, None)


def install_client(client: FakeBriefClient) -> None:
    app.dependency_overrides[get_client_factory] = lambda: lambda: client


@pytest.fixture(autouse=True)
def _no_external_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Brief tests must run offline: only loopback (the test database) may be reached."""
    import socket  # noqa: PLC0415

    real_connect = socket.socket.connect

    def guarded(self: socket.socket, address: object) -> None:
        host = address[0] if isinstance(address, tuple) else None
        if host not in (None, "localhost", "127.0.0.1", "::1"):
            raise AssertionError(f"Unexpected external network access to {host!r}")
        real_connect(self, address)  # type: ignore[arg-type]

    monkeypatch.setattr(socket.socket, "connect", guarded)
