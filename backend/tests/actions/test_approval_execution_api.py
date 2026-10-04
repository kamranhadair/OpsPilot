"""Spec 12: human approval, rejection and execution through the API.

Covers the approval boundary (no execution without a recorded human approval), the
state machine over HTTP, idempotent execution, adapter failures and the audit order.
"""

from collections.abc import Callable
from datetime import UTC, datetime

import httpx2
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.routes.actions import get_adapters
from app.core.config import get_settings
from app.integrations.investigations.base import (
    InvestigationAdapterError,
    InvestigationRequest,
    InvestigationResult,
)
from app.integrations.investigations.mock import MockInvestigationAdapter
from app.main import app
from app.models import ActionExecution, Approval, AuditLog, ProposedAction
from app.models.enums import (
    ActionStatus,
    ActionType,
    ActorType,
    ApprovalDecision,
    ExecutionStatus,
)
from app.schemas.actions import ActionDetailOut
from tests.actions.conftest import (
    FakeActionClient,
    install_action_client,
    make_settings,
    proposal,
)
from tests.db import factories
from tests.metrics.conftest import World

pytestmark = pytest.mark.db

REVIEWER = "Operations Manager"


class CountingAdapter(MockInvestigationAdapter):
    def __init__(self) -> None:
        self.requests: list[InvestigationRequest] = []

    def create_investigation(self, request: InvestigationRequest) -> InvestigationResult:
        self.requests.append(request)
        return super().create_investigation(request)


class FailingAdapter(CountingAdapter):
    def create_investigation(self, request: InvestigationRequest) -> InvestigationResult:
        self.requests.append(request)
        raise InvestigationAdapterError("TRACKER_UNAVAILABLE", "The tracker is unavailable.")


class CrashingAdapter(CountingAdapter):
    def create_investigation(self, request: InvestigationRequest) -> InvestigationResult:
        self.requests.append(request)
        raise RuntimeError("Authorization: Bearer sk-secret-should-not-leak")


def install_adapter(adapter: CountingAdapter) -> CountingAdapter:
    app.dependency_overrides[get_adapters] = lambda: {ActionType.OPEN_INVESTIGATION: adapter}
    return adapter


@pytest.fixture
def adapter() -> CountingAdapter:
    return install_adapter(CountingAdapter())


@pytest.fixture
def action_id(valid_brief: tuple[dict[str, object], list[str]], api: TestClient) -> int:
    """A real AI proposal in ``pending_approval``, created through the proposal endpoint."""
    brief, ids = valid_brief
    install_action_client(FakeActionClient(proposal(ids)))
    response = api.post(f"/api/briefs/{brief['id']}/actions/propose")
    assert response.status_code == 201, response.text
    assert response.json()["status"] == "pending_approval"
    value: int = response.json()["id"]
    return value


def _approve(api: TestClient, action_id: int, **body: object) -> httpx2.Response:
    return api.post(f"/api/actions/{action_id}/approve", json={"reviewer": REVIEWER, **body})


def _reject(api: TestClient, action_id: int, **body: object) -> httpx2.Response:
    return api.post(f"/api/actions/{action_id}/reject", json={"reviewer": REVIEWER, **body})


def _execute(api: TestClient, action_id: int) -> httpx2.Response:
    return api.post(f"/api/actions/{action_id}/execute")


def _count(session: Session, model: type, action_id: int) -> int:
    stmt = select(func.count()).select_from(model).where(model.action_id == action_id)  # type: ignore[attr-defined]
    return session.execute(stmt).scalar_one()


def _audit(session: Session, action_id: int) -> list[AuditLog]:
    stmt = (
        select(AuditLog)
        .where(AuditLog.entity_type == "proposed_action", AuditLog.entity_id == str(action_id))
        .order_by(AuditLog.id)
    )
    return list(session.execute(stmt).scalars())


def _set_status(session: Session, action_id: int, status: ActionStatus) -> None:
    action = session.get(ProposedAction, action_id)
    assert action is not None
    action.status = status
    session.commit()


# --- approval ---------------------------------------------------------------------------


def test_approval_creates_a_human_decision_record(
    action_id: int, api: TestClient, volume_world: World
) -> None:
    response = _approve(api, action_id, comment="Looks grounded.")
    assert response.status_code == 200, response.text
    detail = ActionDetailOut.model_validate(response.json())
    assert detail.status is ActionStatus.APPROVED
    assert detail.approval is not None
    assert detail.approval.decision is ApprovalDecision.APPROVED
    assert detail.approval.reviewer == REVIEWER
    assert detail.approval.comment == "Looks grounded."
    assert detail.approval.edited_fields == []
    assert detail.allowed_operations == ["execute"]
    assert detail.execution is None

    approvals = (
        volume_world.session.execute(select(Approval).where(Approval.action_id == action_id))
        .scalars()
        .all()
    )
    assert len(approvals) == 1 and approvals[0].edited_payload_json is None
    event = _audit(volume_world.session, action_id)[-1]
    assert (event.event_type, event.actor_type, event.actor_id) == (
        "action.approved",
        ActorType.HUMAN,
        REVIEWER,
    )
    assert event.payload_json["from"] == "pending_approval"
    assert event.payload_json["to"] == "approved"


def test_human_edits_are_applied_and_recorded_with_before_and_after(
    action_id: int, api: TestClient, volume_world: World
) -> None:
    session = volume_world.session
    original = session.get(ProposedAction, action_id)
    assert original is not None
    before_title, before_steps = original.title, list(original.investigation_steps_json)
    before_description = original.description

    edits = {
        "title": "Investigate EMEA billing volume",
        "investigation_steps": ["Review billing segment tickets"],
        "description": before_description,  # unchanged: not recorded as an edit
    }
    response = _approve(api, action_id, edits=edits)
    assert response.status_code == 200, response.text
    detail = ActionDetailOut.model_validate(response.json())
    assert detail.title == edits["title"]
    assert detail.investigation_steps == edits["investigation_steps"]
    assert detail.approval is not None
    assert detail.approval.edited_fields == ["investigation_steps", "title"]

    approval = session.execute(select(Approval).where(Approval.action_id == action_id)).scalar_one()
    assert approval.edited_payload_json == {
        "before": {"title": before_title, "investigation_steps": before_steps},
        "after": {"title": edits["title"], "investigation_steps": edits["investigation_steps"]},
    }
    edited = [e for e in _audit(session, action_id) if e.event_type == "action.edited"]
    assert len(edited) == 1
    assert edited[0].actor_type is ActorType.HUMAN
    assert edited[0].payload_json["before"]["title"] == before_title


@pytest.mark.parametrize(
    ("edits", "code"),
    [
        ({"description": "The spike was caused by the deployment."}, "CAUSAL_LANGUAGE"),
        (
            {"investigation_steps": ["The investigation has been opened."]},
            "ACTION_CLAIMED_COMPLETE",
        ),
    ],
)
def test_edits_are_held_to_the_proposal_wording_policy(
    action_id: int, api: TestClient, volume_world: World, edits: dict[str, object], code: str
) -> None:
    response = _approve(api, action_id, edits=edits)
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "ACTION_EDIT_REJECTED"
    assert code in {issue["code"] for issue in body["issues"]}
    stored = volume_world.session.get(ProposedAction, action_id)
    assert stored is not None and stored.status is ActionStatus.PENDING_APPROVAL
    assert _count(volume_world.session, Approval, action_id) == 0


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"reviewer": ""},
        {"reviewer": "   "},
        {"reviewer": REVIEWER, "edits": {}},
        {"reviewer": REVIEWER, "edits": {"evidence_ids": ["ANOM-000001"]}},
        {"reviewer": REVIEWER, "actor_type": "ai"},
    ],
)
def test_malformed_approval_requests_are_rejected(
    action_id: int, api: TestClient, volume_world: World, body: dict[str, object]
) -> None:
    assert api.post(f"/api/actions/{action_id}/approve", json=body).status_code == 422
    assert _count(volume_world.session, Approval, action_id) == 0


@pytest.mark.parametrize("reviewer", ["system", "AI", "model:test-model", "OpsPilot"])
def test_ai_or_system_cannot_approve(
    action_id: int, api: TestClient, volume_world: World, reviewer: str
) -> None:
    response = api.post(f"/api/actions/{action_id}/approve", json={"reviewer": reviewer})
    assert response.status_code == 422
    assert response.json()["code"] == "REVIEWER_NOT_HUMAN"
    assert _count(volume_world.session, Approval, action_id) == 0
    stored = volume_world.session.get(ProposedAction, action_id)
    assert stored is not None and stored.status is ActionStatus.PENDING_APPROVAL


def test_double_approval_creates_one_decision(
    action_id: int, api: TestClient, volume_world: World
) -> None:
    assert _approve(api, action_id).status_code == 200
    second = _approve(api, action_id)
    assert second.status_code == 409
    assert second.json() == {
        "code": "ACTION_INVALID_TRANSITION",
        "message": second.json()["message"],
        "current_status": "approved",
    }
    assert _count(volume_world.session, Approval, action_id) == 1


def test_database_allows_one_decision_and_one_execution_per_action(
    clean_actions: Session,
) -> None:
    brief = factories.brief()
    clean_actions.add(brief)
    clean_actions.flush()
    action = factories.action(brief.id, status=ActionStatus.APPROVED)
    clean_actions.add(action)
    clean_actions.flush()
    for make in (lambda: _approval_row(action.id), lambda: _execution_row(action.id)):
        clean_actions.add(make())
        clean_actions.flush()
        with pytest.raises(IntegrityError), clean_actions.begin_nested():
            clean_actions.add(make())
            clean_actions.flush()


def _approval_row(action_id: int) -> Approval:
    return Approval(
        action_id=action_id,
        decision=ApprovalDecision.APPROVED,
        reviewer=REVIEWER,
        decided_at=datetime.now(UTC),
    )


def _execution_row(action_id: int) -> ActionExecution:
    return ActionExecution(
        action_id=action_id,
        adapter_key="mock_investigation",
        status=ExecutionStatus.SUCCEEDED,
        request_json={},
        response_json={},
        started_at=datetime.now(UTC),
    )


# --- rejection --------------------------------------------------------------------------


def test_rejection_is_recorded_and_blocks_execution(
    action_id: int, api: TestClient, volume_world: World, adapter: CountingAdapter
) -> None:
    response = _reject(api, action_id, comment="Not actionable.")
    assert response.status_code == 200, response.text
    detail = ActionDetailOut.model_validate(response.json())
    assert detail.status is ActionStatus.REJECTED
    assert detail.approval is not None and detail.approval.decision is ApprovalDecision.REJECTED
    assert detail.allowed_operations == []
    event = _audit(volume_world.session, action_id)[-1]
    assert (event.event_type, event.actor_type) == ("action.rejected", ActorType.HUMAN)

    blocked = _execute(api, action_id)
    assert blocked.status_code == 409
    assert blocked.json()["current_status"] == "rejected"
    assert adapter.requests == []
    assert _count(volume_world.session, ActionExecution, action_id) == 0


@pytest.mark.parametrize(
    ("first", "second"),
    [(_reject, _approve), (_approve, _reject), (_reject, _reject)],
    ids=["approve-rejected", "reject-approved", "reject-twice"],
)
def test_terminal_decisions_cannot_be_reversed(
    action_id: int,
    api: TestClient,
    first: Callable[[TestClient, int], httpx2.Response],
    second: Callable[[TestClient, int], httpx2.Response],
) -> None:
    assert first(api, action_id).status_code == 200
    response = second(api, action_id)
    assert response.status_code == 409
    assert response.json()["code"] == "ACTION_INVALID_TRANSITION"


def test_stale_ui_transition_is_a_typed_conflict(
    action_id: int, api: TestClient, volume_world: World
) -> None:
    """Another user/process changed the state after this UI loaded it."""
    _set_status(volume_world.session, action_id, ActionStatus.REJECTED)
    response = _approve(api, action_id)
    assert response.status_code == 409
    assert response.json()["current_status"] == "rejected"
    assert _count(volume_world.session, Approval, action_id) == 0


def test_transitions_on_a_missing_action_are_not_found(api: TestClient) -> None:
    for response in (_approve(api, 999999), _reject(api, 999999), _execute(api, 999999)):
        assert response.status_code == 404
        assert response.json()["code"] == "ACTION_NOT_FOUND"


# --- execution --------------------------------------------------------------------------


def test_pending_action_cannot_execute(
    action_id: int, api: TestClient, volume_world: World, adapter: CountingAdapter
) -> None:
    response = _execute(api, action_id)
    assert response.status_code == 409
    assert response.json()["code"] == "ACTION_INVALID_TRANSITION"
    assert response.json()["current_status"] == "pending_approval"
    assert adapter.requests == []
    assert _count(volume_world.session, ActionExecution, action_id) == 0


def test_approved_status_without_a_human_approval_record_fails_closed(
    action_id: int, api: TestClient, volume_world: World, adapter: CountingAdapter
) -> None:
    _set_status(volume_world.session, action_id, ActionStatus.APPROVED)
    detail = api.get(f"/api/actions/{action_id}").json()
    assert detail["allowed_operations"] == []
    response = _execute(api, action_id)
    assert response.status_code == 409
    assert response.json()["code"] == "APPROVAL_REQUIRED"
    assert adapter.requests == []
    stored = volume_world.session.get(ProposedAction, action_id)
    assert stored is not None and stored.status is ActionStatus.APPROVED


def test_approved_action_executes_once_with_a_visible_reference(
    action_id: int, api: TestClient, volume_world: World, adapter: CountingAdapter
) -> None:
    assert _approve(api, action_id, edits={"title": "Edited by human"}).status_code == 200
    response = _execute(api, action_id)
    assert response.status_code == 200, response.text
    detail = ActionDetailOut.model_validate(response.json())
    assert detail.status is ActionStatus.SUCCEEDED
    assert detail.execution is not None
    assert detail.execution.external_ref == f"INV-{action_id:04d}"
    assert detail.execution.adapter_key == "mock_investigation"
    assert detail.execution.finished_at is not None
    assert detail.allowed_operations == []

    (request,) = adapter.requests
    assert request.title == "Edited by human"  # the human-approved content is executed
    assert request.approved_by == REVIEWER
    assert request.evidence_ids == detail.evidence_ids


def test_second_execution_is_idempotent(
    action_id: int, api: TestClient, volume_world: World, adapter: CountingAdapter
) -> None:
    _approve(api, action_id)
    first = _execute(api, action_id).json()
    second = _execute(api, action_id)
    assert second.status_code == 200
    assert second.json()["execution"] == first["execution"]
    assert len(adapter.requests) == 1
    assert _count(volume_world.session, ActionExecution, action_id) == 1


def test_audit_events_are_in_transition_order(
    action_id: int, api: TestClient, volume_world: World, adapter: CountingAdapter
) -> None:
    _approve(api, action_id, edits={"title": "Edited by human"})
    _execute(api, action_id)
    _execute(api, action_id)  # replay writes nothing
    entries = _audit(volume_world.session, action_id)
    assert [(e.event_type, e.actor_type) for e in entries] == [
        ("action.proposed", ActorType.AI),
        ("action.status_changed", ActorType.SYSTEM),
        ("action.edited", ActorType.HUMAN),
        ("action.approved", ActorType.HUMAN),
        ("action.execution_started", ActorType.SYSTEM),
        ("action.execution_succeeded", ActorType.SYSTEM),
    ]
    transitions = [(e.payload_json.get("from"), e.payload_json.get("to")) for e in entries]
    assert [t for t in transitions if t != (None, None)] == [
        ("proposed", "pending_approval"),
        ("pending_approval", "approved"),
        ("approved", "executing"),
        ("executing", "succeeded"),
    ]
    assert entries[-1].payload_json["external_ref"] == f"INV-{action_id:04d}"
    detail = api.get(f"/api/actions/{action_id}").json()
    assert [e["event_type"] for e in detail["audit_events"]] == [e.event_type for e in entries]


@pytest.mark.parametrize(
    ("adapter_type", "message"),
    [
        (FailingAdapter, "The tracker is unavailable."),
        (CrashingAdapter, "The investigation adapter failed unexpectedly."),
    ],
)
def test_adapter_failure_is_recorded_safely_and_is_terminal(
    action_id: int,
    api: TestClient,
    volume_world: World,
    adapter_type: type[CountingAdapter],
    message: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    failing = install_adapter(adapter_type())
    _approve(api, action_id)
    response = _execute(api, action_id)
    assert response.status_code == 502
    body = response.json()
    assert body["code"] == "ACTION_EXECUTION_FAILED"
    assert body["execution"]["status"] == "failed"
    assert body["execution"]["external_ref"] is None
    assert body["execution"]["error_message"].startswith(message)
    assert "sk-secret" not in response.text and "sk-secret" not in caplog.text

    session = volume_world.session
    stored = session.get(ProposedAction, action_id)
    assert stored is not None and stored.status is ActionStatus.FAILED
    execution = session.execute(
        select(ActionExecution).where(ActionExecution.action_id == action_id)
    ).scalar_one()
    assert "sk-secret" not in str(execution.response_json) + str(execution.error_message)
    last = _audit(session, action_id)[-1]
    assert last.event_type == "action.execution_failed"
    assert "sk-secret" not in str(last.payload_json)

    retry = _execute(api, action_id)
    assert retry.status_code == 409 and retry.json()["current_status"] == "failed"
    assert len(failing.requests) == 1


def test_execution_fails_closed_outside_demo_environments(
    action_id: int, api: TestClient, volume_world: World
) -> None:
    _approve(api, action_id)
    app.dependency_overrides.pop(get_adapters, None)
    app.dependency_overrides[get_settings] = lambda: make_settings(environment="production")
    response = _execute(api, action_id)
    assert response.status_code == 503
    assert response.json()["code"] == "ADAPTER_NOT_CONFIGURED"
    stored = volume_world.session.get(ProposedAction, action_id)
    assert stored is not None and stored.status is ActionStatus.APPROVED
    assert _count(volume_world.session, ActionExecution, action_id) == 0


def test_default_demo_adapter_executes_without_overrides(action_id: int, api: TestClient) -> None:
    _approve(api, action_id)
    response = _execute(api, action_id)
    assert response.status_code == 200, response.text
    assert response.json()["execution"]["external_ref"] == f"INV-{action_id:04d}"


def test_detail_exposes_decision_execution_and_operations(action_id: int, api: TestClient) -> None:
    detail = ActionDetailOut.model_validate(api.get(f"/api/actions/{action_id}").json())
    assert detail.status is ActionStatus.PENDING_APPROVAL
    assert detail.approval is None and detail.execution is None
    assert detail.allowed_operations == ["approve", "reject"]
    assert [e.event_type for e in detail.audit_events] == [
        "action.proposed",
        "action.status_changed",
    ]
