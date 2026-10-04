"""Fixtures for action-proposal tests: a fake model client, valid/invalid source briefs."""

from collections.abc import Iterator
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.routes.actions import get_action_client_factory, get_adapters
from app.api.routes.briefs import get_client_factory
from app.core.config import get_settings
from app.integrations.llm.base import ActionLLMResult, LLMError
from app.main import app
from app.models import (
    ActionExecution,
    Approval,
    AuditLog,
    Brief,
    BriefClaim,
    LLMTrace,
    ProposedAction,
)
from app.models.enums import ActionType, BriefStatus, ClaimType
from app.schemas.actions import ActionProposalContext, ActionProposalOutput
from app.schemas.briefs import DraftClaim
from app.services.evidence.resolver import EvidenceResolver
from tests.briefs.conftest import (  # noqa: F401  (re-exported fixtures)
    END,
    FakeBriefClient,
    _no_external_network,
    breach_world,
    clean_db,
    db_client,
    db_session,
    demo_session,
    detect_billing_volume,
    draft_output,
    engine,
    make_settings,
    no_incidents,
    test_db_url,
    volume_world,
    world,
)
from tests.db import factories
from tests.metrics.conftest import World

CAUSAL_FREE = "Billing volume rose and a deployment coincided with the window; it warrants review."


def proposal(evidence_ids: list[str], **overrides: object) -> ActionProposalOutput:
    values: dict[str, object] = {
        "action_type": ActionType.OPEN_INVESTIGATION.value,
        "title": "Investigate EMEA Billing ticket spike",
        "description": "Review billing ticket volume against baseline for the window.",
        "rationale": "The anomaly and its top segment warrant investigation.",
        "investigation_steps": ["Review the top contributing segment", "Check recent changes"],
        "evidence_ids": evidence_ids,
        **overrides,
    }
    return ActionProposalOutput.model_validate(values)


class FakeActionClient:
    """Records every context it is handed; returns a canned proposal or raises."""

    def __init__(
        self, output: ActionProposalOutput | None = None, error: LLMError | None = None
    ) -> None:
        self.output = output
        self.error = error
        self.contexts: list[ActionProposalContext] = []

    def propose_action(self, context: ActionProposalContext) -> ActionLLMResult:
        self.contexts.append(context)
        if self.error is not None:
            raise self.error
        assert self.output is not None
        return ActionLLMResult(
            output=self.output,
            model_name="test-model",
            input_tokens=200,
            output_tokens=60,
            latency_ms=9,
        )


@pytest.fixture
def clean_actions(no_incidents: Session) -> Session:  # noqa: F811
    for model in (
        ActionExecution,
        Approval,
        ProposedAction,
        LLMTrace,
        BriefClaim,
        Brief,
        AuditLog,
    ):
        no_incidents.execute(model.__table__.delete())  # type: ignore[attr-defined]
    no_incidents.flush()
    return no_incidents


@pytest.fixture
def api(clean_actions: Session, db_client: TestClient) -> Iterator[TestClient]:  # noqa: F811
    """API client with configured settings; tests install their own fake clients."""
    app.dependency_overrides[get_settings] = lambda: make_settings()
    yield db_client
    for dependency in (get_settings, get_client_factory, get_action_client_factory, get_adapters):
        app.dependency_overrides.pop(dependency, None)


def install_action_client(client: FakeActionClient) -> None:
    app.dependency_overrides[get_action_client_factory] = lambda: lambda: client


def generate_brief(api: TestClient, *claims: DraftClaim) -> dict[str, object]:
    """Generate (and validate) a brief through the real brief endpoint."""
    fake = FakeBriefClient(draft_output(*claims))
    app.dependency_overrides[get_client_factory] = lambda: lambda: fake
    response = api.post("/api/briefs/generate")
    assert response.status_code == 201, response.text
    body: dict[str, object] = response.json()
    return body


def observation(*evidence_ids: str, text: str = "Billing volume is elevated.") -> DraftClaim:
    return DraftClaim(claim_type=ClaimType.OBSERVATION, text=text, evidence_ids=list(evidence_ids))


def metric_id_for(session: Session, anomaly_id: str) -> str:
    return EvidenceResolver(session).resolve(anomaly_id).related_evidence_ids[0]


def add_event(target: World) -> str:
    """A contextual timeline event inside the bundle lookback; returns the EVT- ID."""
    row = factories.incident(target.session, occurred_at=END - timedelta(hours=30))
    target.session.add(row)
    target.session.flush()
    return row.evidence_id


@pytest.fixture
def valid_brief(volume_world: World, api: TestClient) -> tuple[dict[str, object], list[str]]:  # noqa: F811
    """A validated brief citing ANOM + MTR; returns (brief body, [anomaly_id, metric_id])."""
    anomaly_id = detect_billing_volume(volume_world)
    metric_id = metric_id_for(volume_world.session, anomaly_id)
    brief = generate_brief(api, observation(anomaly_id, metric_id))
    assert brief["status"] == BriefStatus.VALID.value
    return brief, [anomaly_id, metric_id]
