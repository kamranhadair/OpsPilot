"""The V1 action state machine and the human-only approval boundary (no database)."""

import ast
import itertools
from pathlib import Path

import pytest

from app.core.config import Settings
from app.integrations.investigations.base import InvestigationRequest
from app.integrations.investigations.mock import (
    MockInvestigationAdapter,
    get_investigation_adapters,
)
from app.models.enums import ActionStatus, ActionType
from app.services.actions.approval_service import is_reserved_reviewer
from app.services.actions.errors import InvalidActionTransitionError
from app.services.actions.state_machine import (
    TRANSITIONS,
    allowed_operations,
    can_transition,
    ensure_transition,
)

S = ActionStatus
DOCUMENTED = {
    (S.PROPOSED, S.PENDING_APPROVAL),
    (S.PENDING_APPROVAL, S.APPROVED),
    (S.PENDING_APPROVAL, S.REJECTED),
    (S.APPROVED, S.EXECUTING),
    (S.EXECUTING, S.SUCCEEDED),
    (S.EXECUTING, S.FAILED),
}
APP = Path(__file__).resolve().parents[2] / "app"


def test_every_status_has_a_transition_entry() -> None:
    assert set(TRANSITIONS) == set(ActionStatus)


@pytest.mark.parametrize(("current", "target"), list(itertools.product(ActionStatus, repeat=2)))
def test_only_documented_transitions_are_allowed(
    current: ActionStatus, target: ActionStatus
) -> None:
    allowed = (current, target) in DOCUMENTED
    assert can_transition(current, target) is allowed
    if allowed:
        ensure_transition(current, target)
    else:
        with pytest.raises(InvalidActionTransitionError) as excinfo:
            ensure_transition(current, target)
        assert excinfo.value.current_status is current


@pytest.mark.parametrize(
    ("status", "approved", "expected"),
    [
        (S.PROPOSED, False, []),
        (S.PENDING_APPROVAL, False, ["approve", "reject"]),
        (S.APPROVED, True, ["execute"]),
        (S.APPROVED, False, []),  # fails closed without a recorded human approval
        (S.REJECTED, False, []),
        (S.EXECUTING, True, []),
        (S.SUCCEEDED, True, []),
        (S.FAILED, True, []),
    ],
)
def test_allowed_operations(status: ActionStatus, approved: bool, expected: list[str]) -> None:
    assert allowed_operations(status, has_human_approval=approved) == expected


@pytest.mark.parametrize(
    "reviewer", ["ai", "AI", " System ", "opspilot", "model:gpt-4o", "LLM:x", "assistant"]
)
def test_machine_identities_are_reserved(reviewer: str) -> None:
    assert is_reserved_reviewer(reviewer)


@pytest.mark.parametrize("reviewer", ["Operations Manager", "Dana (Support Ops)", "systems lead"])
def test_human_identities_are_accepted(reviewer: str) -> None:
    assert not is_reserved_reviewer(reviewer)


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
        elif isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
    return names


@pytest.mark.parametrize(
    "path",
    [
        APP / "services/actions/proposer.py",
        APP / "services/actions/policy.py",
        *sorted((APP / "integrations/llm").glob("*.py")),
        *sorted((APP / "services/briefs").glob("*.py")),
    ],
    ids=lambda p: str(p.relative_to(APP)),
)
def test_ai_modules_cannot_reach_approval_or_execution(path: Path) -> None:
    forbidden = {
        "app.services.actions.approval_service",
        "app.services.actions.execution_service",
        "app.integrations.investigations",
        "app.integrations.investigations.mock",
    }
    assert not (_imports(path) & forbidden)


def _request(action_id: int) -> InvestigationRequest:
    return InvestigationRequest(
        action_id=action_id,
        action_type=ActionType.OPEN_INVESTIGATION,
        title="t",
        description="d",
        investigation_steps=["s"],
        evidence_ids=["ANOM-000001"],
        approval_id=1,
        approved_by="Operations Manager",
    )


def test_mock_adapter_reference_is_deterministic() -> None:
    adapter = MockInvestigationAdapter()
    first = adapter.create_investigation(_request(1))
    assert first.external_ref == "INV-0001"
    assert adapter.create_investigation(_request(1)) == first
    assert adapter.create_investigation(_request(42)).external_ref == "INV-0042"


@pytest.mark.parametrize(("environment", "configured"), [("demo", True), ("production", False)])
def test_mock_adapter_is_demo_only(environment: str, configured: bool) -> None:
    settings = Settings(_env_file=None, environment=environment)
    adapters = get_investigation_adapters(settings)
    assert (ActionType.OPEN_INVESTIGATION in adapters) is configured
