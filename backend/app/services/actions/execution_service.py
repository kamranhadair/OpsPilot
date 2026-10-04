"""Execution of human-approved actions through an investigation adapter (Spec 12).

Fails closed. Before any adapter call the backend checks, in order:

1. the action exists;
2. it is ``approved`` (a ``succeeded`` action replays its existing execution instead);
3. a recorded human approval exists;
4. the action type is allow-listed;
5. an adapter is configured for that type.

``approved -> executing`` is committed before the adapter runs, so a concurrent request
sees ``executing`` and cannot start a second investigation; the unique
``action_executions.action_id`` constraint backstops this. Adapter failures are stored
as a ``failed`` execution with a safe message only.
"""

import logging
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.integrations.investigations.base import (
    InvestigationAdapter,
    InvestigationAdapterError,
    InvestigationRequest,
    InvestigationResult,
)
from app.models.action import ActionExecution, Approval, ProposedAction
from app.models.enums import ActionStatus, ActionType, ActorType, ExecutionStatus
from app.repositories.action import (
    ActionExecutionRepository,
    ActionRepository,
    ApprovalRepository,
)
from app.repositories.audit_log import AuditLogRepository
from app.schemas.actions import ActionDetailOut
from app.services.actions.detail import execution_out, is_human_approval, load_action_detail
from app.services.actions.errors import (
    ActionError,
    ActionExecutionFailedError,
    ActionNotFoundError,
    AdapterNotConfiguredError,
    ApprovalRequiredError,
    InvalidActionTransitionError,
    UnsupportedActionTypeError,
)
from app.services.actions.policy import is_allowed_action_type
from app.services.actions.proposer import ENTITY
from app.services.actions.state_machine import ensure_transition

GENERIC_FAILURE = "The investigation adapter failed unexpectedly. No investigation was created."

logger = logging.getLogger(__name__)


class ActionExecutionService:
    def __init__(
        self, session: Session, adapters: Mapping[ActionType, InvestigationAdapter]
    ) -> None:
        self.session = session
        self.adapters = adapters
        self.actions = ActionRepository(session)
        self.approvals = ApprovalRepository(session)
        self.executions = ActionExecutionRepository(session)
        self.audit = AuditLogRepository(session)

    def execute(self, action_id: int) -> ActionDetailOut:
        """Execute once; replaying a succeeded action returns the existing execution.

        Raises:
            ActionNotFoundError, InvalidActionTransitionError, ApprovalRequiredError,
            UnsupportedActionTypeError, AdapterNotConfiguredError: nothing was executed.
            ActionExecutionFailedError: the adapter failed; the failure is persisted.
        """
        try:
            started = self._start(action_id)
        except ActionError:
            self.session.rollback()
            raise
        if started is not None:
            action, execution, request, adapter = started
            self._finish(action, execution, request, adapter)
        return load_action_detail(self.session, action_id)

    def _start(
        self, action_id: int
    ) -> tuple[ProposedAction, ActionExecution, InvestigationRequest, InvestigationAdapter] | None:
        """Check the gates and commit ``executing``; ``None`` means an idempotent replay."""
        action = self.actions.get_for_update(action_id)
        if action is None:
            raise ActionNotFoundError(f"Action {action_id} does not exist.")
        if (
            action.status is ActionStatus.SUCCEEDED
            and self.executions.get_for_action(action_id) is not None
        ):
            self.session.rollback()  # release the row lock; nothing to write
            return None
        if action.status is not ActionStatus.APPROVED:
            raise InvalidActionTransitionError(
                f"Action {action_id} is '{action.status.value}'; only an approved action "
                "can be executed.",
                action.status,
            )
        approval = self.approvals.get_for_action(action_id)
        if not is_human_approval(approval):
            raise ApprovalRequiredError(
                f"Action {action_id} has no recorded human approval; execution is refused."
            )
        assert approval is not None
        if not is_allowed_action_type(action.action_type):
            raise UnsupportedActionTypeError(
                f"{action.action_type!r} is not an allowed V1 action type."
            )
        adapter = self.adapters.get(action.action_type)
        if adapter is None:
            raise AdapterNotConfiguredError(
                f"No investigation adapter is configured for '{action.action_type.value}'."
            )

        request = self._request(action, approval)
        ensure_transition(action.status, ActionStatus.EXECUTING)
        execution = ActionExecution(
            action_id=action_id,
            adapter_key=adapter.adapter_key,
            status=ExecutionStatus.EXECUTING,
            request_json=request.model_dump(mode="json"),
            response_json={},
            started_at=datetime.now(UTC),
        )
        try:
            with self.session.begin_nested():
                self.executions.add(execution)
        except IntegrityError as exc:
            raise InvalidActionTransitionError(
                f"Action {action_id} already has an execution.", None
            ) from exc
        action.status = ActionStatus.EXECUTING
        self.session.flush()
        self.audit.append(
            actor_type=ActorType.SYSTEM,
            event_type="action.execution_started",
            entity_type=ENTITY,
            entity_id=str(action_id),
            payload={
                "approval_id": approval.id,
                "execution_id": execution.id,
                "adapter_key": adapter.adapter_key,
                "from": ActionStatus.APPROVED.value,
                "to": ActionStatus.EXECUTING.value,
            },
        )
        self.session.commit()
        return action, execution, request, adapter

    def _finish(
        self,
        action: ProposedAction,
        execution: ActionExecution,
        request: InvestigationRequest,
        adapter: InvestigationAdapter,
    ) -> None:
        result: InvestigationResult | None = None
        error: str | None = None
        error_code: str | None = None
        try:
            result = adapter.create_investigation(request)
        except InvestigationAdapterError as exc:
            error, error_code = exc.safe_message, exc.code
        except Exception as exc:  # noqa: BLE001 - any adapter fault becomes a recorded failure
            # Class name only: exception text may carry request content or secrets.
            logger.error(
                "Investigation adapter %s raised %s for action %s",
                adapter.adapter_key,
                type(exc).__name__,
                action.id,
            )
            error, error_code = GENERIC_FAILURE, "ADAPTER_UNEXPECTED_ERROR"

        target = ActionStatus.SUCCEEDED if result is not None else ActionStatus.FAILED
        ensure_transition(action.status, target)
        execution.finished_at = datetime.now(UTC)
        if result is not None:
            execution.status = ExecutionStatus.SUCCEEDED
            execution.external_ref = result.external_ref
            execution.response_json = dict(result.response)
        else:
            execution.status = ExecutionStatus.FAILED
            execution.error_message = error
            execution.response_json = {"error_code": error_code}
        action.status = target
        self.session.flush()
        payload: dict[str, Any] = {
            "execution_id": execution.id,
            "adapter_key": adapter.adapter_key,
            "from": ActionStatus.EXECUTING.value,
            "to": target.value,
        }
        if result is not None:
            payload["external_ref"] = result.external_ref
        else:
            payload["error_code"] = error_code
        self.audit.append(
            actor_type=ActorType.SYSTEM,
            event_type=f"action.execution_{target.value}",
            entity_type=ENTITY,
            entity_id=str(action.id),
            payload=payload,
        )
        self.session.commit()
        if result is None:
            raise ActionExecutionFailedError(
                f"Executing action {action.id} failed: {error}", execution_out(execution)
            )

    @staticmethod
    def _request(action: ProposedAction, approval: Approval) -> InvestigationRequest:
        return InvestigationRequest(
            action_id=action.id,
            action_type=action.action_type,
            title=action.title,
            description=action.description,
            investigation_steps=list(action.investigation_steps_json),
            evidence_ids=list(action.evidence_ids_json),
            approval_id=approval.id,
            approved_by=approval.reviewer,
        )
