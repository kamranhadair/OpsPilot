"""The V1 action state machine (Spec 12). No other transition is valid.

```text
proposed -> pending_approval
pending_approval -> approved | rejected
approved -> executing
executing -> succeeded | failed
```

``rejected``, ``succeeded`` and ``failed`` are terminal.
"""

from collections.abc import Mapping

from app.models.enums import ActionStatus
from app.schemas.actions import ActionOperation
from app.services.actions.errors import InvalidActionTransitionError

S = ActionStatus

TRANSITIONS: Mapping[ActionStatus, frozenset[ActionStatus]] = {
    S.PROPOSED: frozenset({S.PENDING_APPROVAL}),
    S.PENDING_APPROVAL: frozenset({S.APPROVED, S.REJECTED}),
    S.APPROVED: frozenset({S.EXECUTING}),
    S.EXECUTING: frozenset({S.SUCCEEDED, S.FAILED}),
    S.REJECTED: frozenset(),
    S.SUCCEEDED: frozenset(),
    S.FAILED: frozenset(),
}


def can_transition(current: ActionStatus, target: ActionStatus) -> bool:
    return target in TRANSITIONS[current]


def ensure_transition(current: ActionStatus, target: ActionStatus) -> None:
    if not can_transition(current, target):
        raise InvalidActionTransitionError(
            f"Action is '{current.value}'; it cannot move to '{target.value}'.", current
        )


def allowed_operations(status: ActionStatus, *, has_human_approval: bool) -> list[ActionOperation]:
    """What the backend would currently accept, for the UI to render controls from."""
    operations: list[ActionOperation] = []
    if can_transition(status, S.APPROVED):
        operations.append("approve")
    if can_transition(status, S.REJECTED):
        operations.append("reject")
    if can_transition(status, S.EXECUTING) and has_human_approval:
        operations.append("execute")
    return operations
