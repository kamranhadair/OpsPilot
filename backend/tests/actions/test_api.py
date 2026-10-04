"""Action proposal endpoints and service: grounding, state, audit, duplicates, errors."""

import logging

import httpx2
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.integrations.llm.base import (
    ActionLLMResult,
    LLMMalformedOutputError,
    LLMNotConfiguredError,
    LLMProviderError,
)
from app.main import app
from app.models import (
    ActionExecution,
    Approval,
    AuditLog,
    BriefClaim,
    LLMTrace,
    ProposedAction,
)
from app.models.enums import ActionStatus, ActorType, BriefStatus
from app.schemas.actions import (
    ActionConflictResponse,
    ActionListOut,
    ActionOut,
    ActionProposalContext,
    ActionProposalRejectedResponse,
)
from app.services.actions.proposer import ActionProposalService
from tests.actions.conftest import (
    CAUSAL_FREE,
    FakeActionClient,
    add_event,
    generate_brief,
    install_action_client,
    make_settings,
    metric_id_for,
    observation,
    proposal,
)
from tests.db import factories
from tests.evidence.conftest import detect_billing_volume
from tests.metrics.conftest import World

pytestmark = pytest.mark.db


def _propose(api: TestClient, brief_id: object) -> httpx2.Response:
    return api.post(f"/api/briefs/{brief_id}/actions/propose")


def _count(session: Session, model: type) -> int:
    return session.execute(select(func.count()).select_from(model)).scalar_one()


# --- happy path ------------------------------------------------------------------------


def test_valid_brief_creates_a_grounded_pending_proposal(
    valid_brief: tuple[dict[str, object], list[str]],
    api: TestClient,
    volume_world: World,
) -> None:
    brief, (anomaly_id, metric_id) = valid_brief
    fake = FakeActionClient(proposal([anomaly_id, metric_id]))
    install_action_client(fake)

    response = _propose(api, brief["id"])

    assert response.status_code == 201, response.text
    body = ActionOut.model_validate(response.json())
    assert body.status is ActionStatus.PENDING_APPROVAL
    assert body.action_type == "open_investigation"
    assert body.evidence_ids == [anomaly_id, metric_id]  # persisted unchanged
    assert body.investigation_steps == [
        "Review the top contributing segment",
        "Check recent changes",
    ]
    assert body.source_brief.id == brief["id"]
    assert body.source_brief.status is BriefStatus.VALID

    # The model saw only the validated brief and its resolved, citable evidence.
    (context,) = fake.contexts
    assert context.brief_id == brief["id"]
    assert context.allowed_evidence_ids == sorted([anomaly_id, metric_id])
    assert [e.evidence_id for e in context.evidence] == sorted([anomaly_id, metric_id])
    assert context.allowed_action_types == ["open_investigation"]


def test_proposal_is_never_approved_or_executed(
    valid_brief: tuple[dict[str, object], list[str]],
    api: TestClient,
    volume_world: World,
) -> None:
    brief, ids = valid_brief
    install_action_client(FakeActionClient(proposal(ids)))
    action_id = _propose(api, brief["id"]).json()["id"]

    session = volume_world.session
    stored = session.get(ProposedAction, action_id)
    assert stored is not None and stored.status is ActionStatus.PENDING_APPROVAL
    assert _count(session, Approval) == 0
    assert _count(session, ActionExecution) == 0


def test_creation_and_transition_are_audited(
    valid_brief: tuple[dict[str, object], list[str]],
    api: TestClient,
    volume_world: World,
) -> None:
    brief, ids = valid_brief
    install_action_client(FakeActionClient(proposal(ids)))
    action_id = _propose(api, brief["id"]).json()["id"]

    entries = (
        volume_world.session.execute(
            select(AuditLog)
            .where(AuditLog.entity_type == "proposed_action", AuditLog.entity_id == str(action_id))
            .order_by(AuditLog.id)
        )
        .scalars()
        .all()
    )
    assert [(e.event_type, e.actor_type) for e in entries] == [
        ("action.proposed", ActorType.AI),
        ("action.status_changed", ActorType.SYSTEM),
    ]
    assert entries[0].payload_json["evidence_ids"] == ids
    assert entries[1].payload_json == {"from": "proposed", "to": "pending_approval"}


def test_success_trace_is_recorded_for_the_brief(
    valid_brief: tuple[dict[str, object], list[str]],
    api: TestClient,
    volume_world: World,
) -> None:
    brief, ids = valid_brief
    install_action_client(FakeActionClient(proposal(ids)))
    _propose(api, brief["id"])

    trace = volume_world.session.execute(
        select(LLMTrace).where(LLMTrace.operation == "action_proposal")
    ).scalar_one()
    assert trace.brief_id == brief["id"]
    assert (trace.input_tokens, trace.output_tokens, trace.latency_ms) == (200, 60, 9)


def test_cautious_event_wording_is_accepted(volume_world: World, api: TestClient) -> None:
    anomaly_id = detect_billing_volume(volume_world)
    event_id = add_event(volume_world)
    brief = generate_brief(api, observation(anomaly_id), observation(event_id, text=CAUSAL_FREE))
    assert brief["status"] == "valid", brief
    install_action_client(FakeActionClient(proposal([anomaly_id, event_id], rationale=CAUSAL_FREE)))

    response = _propose(api, brief["id"])

    assert response.status_code == 201, response.text


# --- source brief gate -------------------------------------------------------------------


def test_invalid_brief_cannot_create_a_proposal(volume_world: World, api: TestClient) -> None:
    anomaly_id = detect_billing_volume(volume_world)
    brief = generate_brief(api, observation(anomaly_id, "ANOM-999999"))
    assert brief["status"] == BriefStatus.INVALID.value
    fake = FakeActionClient(proposal([anomaly_id]))
    install_action_client(fake)

    response = _propose(api, brief["id"])

    assert response.status_code == 409
    assert response.json()["code"] == "BRIEF_NOT_VALID"
    assert fake.contexts == []  # the model is never asked
    assert _count(volume_world.session, ProposedAction) == 0


def test_draft_brief_cannot_create_a_proposal(clean_actions: Session, api: TestClient) -> None:
    brief = factories.brief(status=BriefStatus.DRAFT)
    clean_actions.add(brief)
    clean_actions.flush()
    fake = FakeActionClient(proposal(["ANOM-000001"]))
    install_action_client(fake)

    response = _propose(api, brief.id)

    assert response.status_code == 409
    assert response.json()["code"] == "BRIEF_NOT_VALID"
    assert fake.contexts == []


def test_missing_brief_is_not_found(api: TestClient) -> None:
    install_action_client(FakeActionClient(proposal(["ANOM-000001"])))
    response = _propose(api, 999_999)
    assert response.status_code == 404
    assert response.json()["code"] == "BRIEF_NOT_FOUND"
    assert _propose(api, 0).status_code == 422


def test_brief_without_an_anomaly_has_nothing_to_investigate(
    volume_world: World, api: TestClient
) -> None:
    anomaly_id = detect_billing_volume(volume_world)
    metric_id = metric_id_for(volume_world.session, anomaly_id)
    brief = generate_brief(api, observation(metric_id))
    assert brief["status"] == "valid"
    fake = FakeActionClient(proposal([metric_id]))
    install_action_client(fake)

    response = _propose(api, brief["id"])

    assert response.status_code == 409
    assert response.json()["code"] == "NO_ACTIONABLE_ANOMALY"
    assert fake.contexts == []


# --- model output rejected by policy -----------------------------------------------------


@pytest.mark.parametrize(
    ("overrides", "extra_ids", "code"),
    [
        ({"action_type": "open_jira_ticket"}, [], "UNSUPPORTED_ACTION_TYPE"),
        ({}, ["ANOM-999999"], "EVIDENCE_NOT_IN_BRIEF"),
        ({"description": "The investigation has been opened."}, [], "ACTION_CLAIMED_COMPLETE"),
    ],
)
def test_ungrounded_or_unsupported_proposals_are_rejected_and_not_saved(
    valid_brief: tuple[dict[str, object], list[str]],
    api: TestClient,
    volume_world: World,
    overrides: dict[str, object],
    extra_ids: list[str],
    code: str,
) -> None:
    brief, ids = valid_brief
    install_action_client(FakeActionClient(proposal([*ids, *extra_ids], **overrides)))

    response = _propose(api, brief["id"])

    assert response.status_code == 422
    body = ActionProposalRejectedResponse.model_validate(response.json())
    assert body.code == "ACTION_PROPOSAL_REJECTED"
    assert [i.code for i in body.issues] == [code]
    session = volume_world.session
    assert _count(session, ProposedAction) == 0
    audit = session.execute(
        select(AuditLog).where(AuditLog.event_type == "action.proposal_rejected")
    ).scalar_one()
    assert audit.entity_type == "brief" and audit.entity_id == str(brief["id"])
    assert audit.payload_json["issues"][0]["code"] == code
    assert "investigation has been opened" not in str(audit.payload_json).lower()


def test_unresolved_evidence_after_brief_generation_is_rejected(
    valid_brief: tuple[dict[str, object], list[str]],
    api: TestClient,
    volume_world: World,
) -> None:
    brief, ids = valid_brief
    session = volume_world.session
    # Simulate evidence that was valid at brief time but has since disappeared.
    claim = session.execute(
        select(BriefClaim).where(BriefClaim.brief_id == brief["id"])
    ).scalar_one()
    claim.evidence_ids_json = [*ids, "SEG-999999"]
    session.flush()
    install_action_client(FakeActionClient(proposal([*ids, "SEG-999999"])))

    response = _propose(api, brief["id"])

    assert response.status_code == 422
    assert [i["code"] for i in response.json()["issues"]] == ["EVIDENCE_UNRESOLVED"]


def test_malformed_output_is_a_typed_error_with_trace(
    valid_brief: tuple[dict[str, object], list[str]],
    api: TestClient,
    volume_world: World,
) -> None:
    brief, _ = valid_brief
    install_action_client(FakeActionClient(error=LLMMalformedOutputError("bad output")))

    response = _propose(api, brief["id"])

    assert response.status_code == 502
    assert response.json()["code"] == "LLM_MALFORMED_OUTPUT"
    trace = volume_world.session.execute(
        select(LLMTrace).where(LLMTrace.operation == "action_proposal")
    ).scalar_one()
    assert trace.error_code == "LLM_MALFORMED_OUTPUT"
    assert _count(volume_world.session, ProposedAction) == 0


def test_provider_failure_is_typed(
    valid_brief: tuple[dict[str, object], list[str]], api: TestClient
) -> None:
    brief, _ = valid_brief
    install_action_client(FakeActionClient(error=LLMProviderError("down")))
    assert _propose(api, brief["id"]).json()["code"] == "LLM_PROVIDER_ERROR"


def test_missing_key_is_not_configured_and_never_calls_the_model(
    valid_brief: tuple[dict[str, object], list[str]], api: TestClient
) -> None:
    brief, ids = valid_brief
    fake = FakeActionClient(proposal(ids))
    install_action_client(fake)
    app.dependency_overrides[get_settings] = lambda: make_settings(openai_api_key=None)

    response = _propose(api, brief["id"])

    assert response.status_code == 503
    assert response.json()["code"] == "LLM_NOT_CONFIGURED"
    assert fake.contexts == []


# --- duplicate policy --------------------------------------------------------------------


def test_second_proposal_for_the_same_brief_is_a_conflict(
    valid_brief: tuple[dict[str, object], list[str]],
    api: TestClient,
    volume_world: World,
) -> None:
    brief, ids = valid_brief
    fake = FakeActionClient(proposal(ids))
    install_action_client(fake)
    first = _propose(api, brief["id"]).json()

    second = _propose(api, brief["id"])

    assert second.status_code == 409
    body = ActionConflictResponse.model_validate(second.json())
    assert body.code == "ACTION_ALREADY_PROPOSED"
    assert body.existing_action_id == first["id"]
    assert len(fake.contexts) == 1  # no second model call
    assert _count(volume_world.session, ProposedAction) == 1


def test_database_enforces_one_proposal_per_brief(clean_actions: Session) -> None:
    brief = factories.brief()
    clean_actions.add(brief)
    clean_actions.flush()
    clean_actions.add(factories.action(brief.id))
    clean_actions.flush()
    with pytest.raises(IntegrityError), clean_actions.begin_nested():
        clean_actions.add(factories.action(brief.id))
        clean_actions.flush()


# --- list / detail -----------------------------------------------------------------------


def _stored_action(session: Session, status: ActionStatus) -> int:
    brief = factories.brief()
    session.add(brief)
    session.flush()
    action = factories.action(brief.id, status=status)
    session.add(action)
    session.flush()
    return action.id


def test_list_puts_pending_first_and_filters_by_status(
    clean_actions: Session, api: TestClient
) -> None:
    rejected = _stored_action(clean_actions, ActionStatus.REJECTED)
    pending = _stored_action(clean_actions, ActionStatus.PENDING_APPROVAL)
    newer_rejected = _stored_action(clean_actions, ActionStatus.REJECTED)

    everything = ActionListOut.model_validate(api.get("/api/actions").json())
    assert [a.id for a in everything.items] == [pending, newer_rejected, rejected]

    only_pending = ActionListOut.model_validate(
        api.get("/api/actions", params={"status": "pending_approval"}).json()
    )
    assert [a.id for a in only_pending.items] == [pending]

    page = ActionListOut.model_validate(api.get("/api/actions?limit=1&offset=1").json())
    assert [a.id for a in page.items] == [newer_rejected]


@pytest.mark.parametrize("query", ["status=teleported", "limit=0", "limit=101", "offset=-1"])
def test_list_rejects_invalid_filters(api: TestClient, query: str) -> None:
    assert api.get(f"/api/actions?{query}").status_code == 422


def test_empty_list(api: TestClient) -> None:
    assert api.get("/api/actions").json()["items"] == []


def test_detail_returns_proposal_evidence_brief_and_state(
    valid_brief: tuple[dict[str, object], list[str]], api: TestClient
) -> None:
    brief, ids = valid_brief
    install_action_client(FakeActionClient(proposal(ids)))
    action_id = _propose(api, brief["id"]).json()["id"]

    body = ActionOut.model_validate(api.get(f"/api/actions/{action_id}").json())

    assert body.id == action_id
    assert body.evidence_ids == ids
    assert body.source_brief.id == brief["id"]
    assert body.status is ActionStatus.PENDING_APPROVAL


def test_detail_not_found(api: TestClient) -> None:
    response = api.get("/api/actions/999999")
    assert response.status_code == 404
    assert response.json()["code"] == "ACTION_NOT_FOUND"
    assert api.get("/api/actions/0").status_code == 422


def test_action_routes_are_exactly_the_spec_routes() -> None:
    """Approval and execution are separate POST transitions; nothing else mutates an action."""
    paths = app.openapi()["paths"]
    action_paths = {p for p in paths if "action" in p}
    assert action_paths == {
        "/api/briefs/{brief_id}/actions/propose",
        "/api/actions",
        "/api/actions/{action_id}",
        "/api/actions/{action_id}/approve",
        "/api/actions/{action_id}/reject",
        "/api/actions/{action_id}/execute",
    }
    assert set(paths["/api/actions/{action_id}"]) == {"get"}
    for operation in ("approve", "reject", "execute"):
        assert set(paths[f"/api/actions/{{action_id}}/{operation}"]) == {"post"}


# --- review follow-ups ---------------------------------------------------------------------


class RacingClient(FakeActionClient):
    """Simulates a concurrent request that stores a proposal while the model is drafting."""

    def __init__(self, session: Session, brief_id: int, ids: list[str]) -> None:
        super().__init__(proposal(ids))
        self.session = session
        self.brief_id = brief_id
        self.competitor_id: int | None = None

    def propose_action(self, context: ActionProposalContext) -> ActionLLMResult:
        competitor = factories.action(self.brief_id, status=ActionStatus.PENDING_APPROVAL)
        self.session.add(competitor)
        self.session.flush()
        self.competitor_id = competitor.id
        return super().propose_action(context)


def test_losing_a_concurrent_race_is_a_typed_conflict(
    valid_brief: tuple[dict[str, object], list[str]],
    api: TestClient,
    volume_world: World,
) -> None:
    brief, ids = valid_brief
    session = volume_world.session
    racer = RacingClient(session, int(str(brief["id"])), ids)
    install_action_client(racer)

    response = _propose(api, brief["id"])

    assert response.status_code == 409
    body = ActionConflictResponse.model_validate(response.json())
    assert body.code == "ACTION_ALREADY_PROPOSED"
    assert body.existing_action_id == racer.competitor_id
    assert _count(session, ProposedAction) == 1
    # The model call still happened, so its trace is kept; no audit for a row never stored.
    action_traces = select(func.count()).select_from(LLMTrace)
    assert (
        session.execute(action_traces.where(LLMTrace.operation == "action_proposal")).scalar_one()
        == 1
    )
    assert (
        session.execute(
            select(func.count())
            .select_from(AuditLog)
            .where(AuditLog.event_type == "action.proposed")
        ).scalar_one()
        == 0
    )


def test_malformed_model_ids_never_reach_the_audit_trail_or_logs(
    valid_brief: tuple[dict[str, object], list[str]],
    api: TestClient,
    volume_world: World,
    caplog: pytest.LogCaptureFixture,
) -> None:
    brief, ids = valid_brief
    injected = "ANOM-1\nFAKE LOG LINE " + "x" * 500
    install_action_client(FakeActionClient(proposal([*ids, injected, "SEG-999999"])))

    with caplog.at_level(logging.WARNING):
        response = _propose(api, brief["id"])

    assert response.status_code == 422
    audit = volume_world.session.execute(
        select(AuditLog).where(AuditLog.event_type == "action.proposal_rejected")
    ).scalar_one()
    recorded = [i["evidence_id"] for i in audit.payload_json["issues"]]
    assert recorded == ["<malformed>", "SEG-999999"]
    assert "FAKE LOG LINE" not in str(audit.payload_json)
    assert "FAKE LOG LINE" not in caplog.text
    assert "SEG-999999" in caplog.text


def test_no_anomaly_wins_over_missing_configuration(volume_world: World, api: TestClient) -> None:
    anomaly_id = detect_billing_volume(volume_world)
    metric_id = metric_id_for(volume_world.session, anomaly_id)
    brief = generate_brief(api, observation(metric_id))
    app.dependency_overrides[get_settings] = lambda: make_settings(openai_api_key=None)

    response = _propose(api, brief["id"])

    assert response.status_code == 409
    assert response.json()["code"] == "NO_ACTIONABLE_ANOMALY"


def test_missing_client_is_not_configured_and_writes_nothing(
    valid_brief: tuple[dict[str, object], list[str]], volume_world: World
) -> None:
    brief, _ = valid_brief
    service = ActionProposalService(volume_world.session, make_settings(), client_factory=None)

    with pytest.raises(LLMNotConfiguredError):
        service.propose(int(str(brief["id"])))

    traces = volume_world.session.execute(
        select(func.count()).select_from(LLMTrace).where(LLMTrace.operation == "action_proposal")
    ).scalar_one()
    assert traces == 0
