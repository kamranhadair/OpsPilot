"""Human approval and rejection of proposed actions (Spec 12).

Only a human decides. Every decision written here is recorded with
``ActorType.HUMAN`` and the reviewer's demo identity; there is no parameter that lets a
caller record an AI or system decision, and no AI/LLM module imports this service. V1
has no authentication, so the reviewer string is recorded, not verified.

Edits are applied to the action row, and the before/after values are kept on the
approval record and in the ``action.edited`` audit event. Edited text is held to the
same causal-language and completion-claim policy as AI drafts. Evidence IDs, the action
type and the rationale cannot be edited.
"""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.action import Approval, ProposedAction
from app.models.enums import ActionStatus, ActorType, ApprovalDecision
from app.repositories.action import ActionRepository, ApprovalRepository
from app.repositories.audit_log import AuditLogRepository
from app.schemas.actions import (
    ActionDetailOut,
    ActionEditIssue,
    ActionEdits,
    ApproveActionRequest,
    EditableField,
    RejectActionRequest,
)
from app.services.actions.detail import load_action_detail
from app.services.actions.errors import (
    ActionEditRejectedError,
    ActionError,
    ActionNotFoundError,
    InvalidActionTransitionError,
    ReviewerNotHumanError,
)
from app.services.actions.policy import find_completion_claims
from app.services.actions.proposer import ENTITY
from app.services.actions.state_machine import ensure_transition
from app.services.briefs.validator import find_causal_phrases

# Identities that name the machine side of the system. A human reviewer must not use them.
RESERVED_REVIEWERS = frozenset(
    {"ai", "system", "opspilot", "llm", "model", "assistant", "bot", "automation"}
)
RESERVED_REVIEWER_PREFIXES = ("ai:", "system:", "model:", "llm:", "opspilot:")


def is_reserved_reviewer(reviewer: str) -> bool:
    normalized = " ".join(reviewer.split()).lower()
    return normalized in RESERVED_REVIEWERS or normalized.startswith(RESERVED_REVIEWER_PREFIXES)


def _current(action: ProposedAction, field: EditableField) -> Any:
    if field == "investigation_steps":
        return list(action.investigation_steps_json)
    return getattr(action, field)


def _changes(action: ProposedAction, edits: ActionEdits | None) -> dict[EditableField, Any]:
    """Only the fields whose value actually differs from the current proposal."""
    if edits is None:
        return {}
    requested: dict[EditableField, Any] = {
        "title": edits.title,
        "description": edits.description,
        "investigation_steps": edits.investigation_steps,
    }
    return {
        field: value
        for field, value in requested.items()
        if value is not None and value != _current(action, field)
    }


def _edit_issues(changes: dict[EditableField, Any]) -> list[ActionEditIssue]:
    issues: list[ActionEditIssue] = []
    for field, value in changes.items():
        texts = value if isinstance(value, list) else [value]
        for text in texts:
            for phrase in find_causal_phrases(text):
                issues.append(
                    ActionEditIssue(
                        code="CAUSAL_LANGUAGE",
                        message=f"The edited {field} asserts causation ({phrase!r}); V1 "
                        "evidence supports association or temporal proximity only.",
                        phrase=phrase,
                        field=field,
                    )
                )
            for phrase in find_completion_claims(text):
                issues.append(
                    ActionEditIssue(
                        code="ACTION_CLAIMED_COMPLETE",
                        message=f"The edited {field} claims the action already occurred "
                        f"({phrase!r}).",
                        phrase=phrase,
                        field=field,
                    )
                )
    return issues


class ActionApprovalService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.actions = ActionRepository(session)
        self.approvals = ApprovalRepository(session)
        self.audit = AuditLogRepository(session)

    def get_detail(self, action_id: int) -> ActionDetailOut:
        return load_action_detail(self.session, action_id)

    def approve(self, action_id: int, request: ApproveActionRequest) -> ActionDetailOut:
        """Record the human approval (with optional edits) and move to ``approved``."""
        try:
            action = self._lock(action_id, request.reviewer, ActionStatus.APPROVED)
            changes = _changes(action, request.edits)
            issues = _edit_issues(changes)
            if issues:
                raise ActionEditRejectedError(
                    "The edits were not applied: edited text must not assert causation or "
                    "claim the investigation already happened.",
                    issues,
                )
            edited_payload: dict[str, Any] | None = None
            if changes:
                before = {field: _current(action, field) for field in changes}
                edited_payload = {"before": before, "after": dict(changes)}
                for field, value in changes.items():
                    if field == "investigation_steps":
                        action.investigation_steps_json = list(value)
                    else:
                        setattr(action, field, value)
            self._decide(
                action,
                decision=ApprovalDecision.APPROVED,
                reviewer=request.reviewer,
                comment=request.comment,
                edited_payload=edited_payload,
            )
        except ActionError:
            self.session.rollback()
            raise
        return load_action_detail(self.session, action_id)

    def reject(self, action_id: int, request: RejectActionRequest) -> ActionDetailOut:
        """Record the human rejection and move to ``rejected`` (terminal)."""
        try:
            action = self._lock(action_id, request.reviewer, ActionStatus.REJECTED)
            self._decide(
                action,
                decision=ApprovalDecision.REJECTED,
                reviewer=request.reviewer,
                comment=request.comment,
                edited_payload=None,
            )
        except ActionError:
            self.session.rollback()
            raise
        return load_action_detail(self.session, action_id)

    def _lock(self, action_id: int, reviewer: str, target: ActionStatus) -> ProposedAction:
        if is_reserved_reviewer(reviewer):
            raise ReviewerNotHumanError(
                f"{reviewer!r} names the AI/system. Only a human reviewer can decide on an action."
            )
        action = self.actions.get_for_update(action_id)
        if action is None:
            raise ActionNotFoundError(f"Action {action_id} does not exist.")
        ensure_transition(action.status, target)
        return action

    def _decide(
        self,
        action: ProposedAction,
        *,
        decision: ApprovalDecision,
        reviewer: str,
        comment: str | None,
        edited_payload: dict[str, Any] | None,
    ) -> None:
        previous = action.status
        approved = decision is ApprovalDecision.APPROVED
        target = ActionStatus.APPROVED if approved else ActionStatus.REJECTED
        approval = Approval(
            action_id=action.id,
            decision=decision,
            reviewer=reviewer,
            comment=comment,
            edited_payload_json=edited_payload,
            decided_at=datetime.now(UTC),
        )
        try:
            with self.session.begin_nested():
                self.approvals.add(approval)
        except IntegrityError as exc:
            # A concurrent request recorded the (single) decision first.
            raise InvalidActionTransitionError(
                f"Action {action.id} already has a recorded decision.", None
            ) from exc
        if edited_payload is not None:
            self.audit.append(
                actor_type=ActorType.HUMAN,
                actor_id=reviewer,
                event_type="action.edited",
                entity_type=ENTITY,
                entity_id=str(action.id),
                payload={"approval_id": approval.id, **edited_payload},
            )
        action.status = target
        self.session.flush()
        self.audit.append(
            actor_type=ActorType.HUMAN,
            actor_id=reviewer,
            event_type=f"action.{decision.value}",
            entity_type=ENTITY,
            entity_id=str(action.id),
            payload={
                "approval_id": approval.id,
                "comment": comment,
                "edited_fields": sorted(edited_payload["after"]) if edited_payload else [],
                "from": previous.value,
                "to": target.value,
            },
        )
        self.session.commit()
