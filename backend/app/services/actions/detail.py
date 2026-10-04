"""Read model for one action: proposal, human decision, execution and audit timeline."""

from typing import cast

from pydantic import JsonValue
from sqlalchemy.orm import Session

from app.models.action import ActionExecution, Approval
from app.models.enums import ApprovalDecision
from app.models.observability import AuditLog
from app.repositories.action import (
    ActionExecutionRepository,
    ActionRepository,
    ApprovalRepository,
)
from app.repositories.audit_log import AuditLogRepository
from app.schemas.actions import (
    ActionDetailOut,
    ApprovalOut,
    AuditEventOut,
    EditableField,
    ExecutionOut,
)
from app.services.actions.errors import ActionNotFoundError
from app.services.actions.proposer import ENTITY, action_out
from app.services.actions.state_machine import allowed_operations


def approval_out(approval: Approval) -> ApprovalOut:
    edits = approval.edited_payload_json or {}
    after = edits.get("after", {})
    return ApprovalOut(
        id=approval.id,
        decision=approval.decision,
        reviewer=approval.reviewer,
        comment=approval.comment,
        edited_fields=cast(list[EditableField], sorted(after)),
        decided_at=approval.decided_at,
    )


def execution_out(execution: ActionExecution) -> ExecutionOut:
    return ExecutionOut(
        id=execution.id,
        status=execution.status,
        adapter_key=execution.adapter_key,
        external_ref=execution.external_ref,
        error_message=execution.error_message,
        started_at=execution.started_at,
        finished_at=execution.finished_at,
    )


def _audit_out(entry: AuditLog) -> AuditEventOut:
    return AuditEventOut(
        id=entry.id,
        actor_type=entry.actor_type,
        actor_id=entry.actor_id,
        event_type=entry.event_type,
        payload=cast(dict[str, JsonValue], entry.payload_json),
        created_at=entry.created_at,
    )


def is_human_approval(approval: Approval | None) -> bool:
    return approval is not None and approval.decision is ApprovalDecision.APPROVED


def load_action_detail(session: Session, action_id: int) -> ActionDetailOut:
    found = ActionRepository(session).get_with_brief(action_id)
    if found is None:
        raise ActionNotFoundError(f"Action {action_id} does not exist.")
    action, brief = found
    approval = ApprovalRepository(session).get_for_action(action_id)
    execution = ActionExecutionRepository(session).get_for_action(action_id)
    events = AuditLogRepository(session).list_for_entity(ENTITY, str(action_id))
    return ActionDetailOut(
        **action_out(action, brief).model_dump(),
        approval=None if approval is None else approval_out(approval),
        execution=None if execution is None else execution_out(execution),
        audit_events=[_audit_out(e) for e in events],
        allowed_operations=allowed_operations(
            action.status, has_human_approval=is_human_approval(approval)
        ),
    )
