"""Approval boundary through the real Spec 12 approval and execution services.

Each scenario inserts a minimal brief and action, then drives the production
services. It only runs inside a rollback-only session (see ``context``), so nothing
it writes survives the evaluation run.
"""

from collections.abc import Mapping
from datetime import UTC, datetime
from functools import partial

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.evals.cases import ApprovalCase, load_approval_cases
from app.evals.context import EvalContext
from app.evals.results import guarded, not_run, verdict
from app.integrations.investigations.base import InvestigationAdapter
from app.models import ActionExecution, Approval, Brief, ProposedAction
from app.models.enums import ActionStatus, ActionType, BriefStatus
from app.schemas.actions import ApproveActionRequest
from app.schemas.evaluations import CaseResult, EvalCategory
from app.services.actions.approval_service import ActionApprovalService
from app.services.actions.errors import (
    ActionError,
    ApprovalRequiredError,
    InvalidActionTransitionError,
    ReviewerNotHumanError,
)
from app.services.actions.execution_service import ActionExecutionService

CATEGORY = EvalCategory.APPROVAL_BOUNDARY
_FIXTURE_START = datetime(2026, 10, 3, tzinfo=UTC)
_FIXTURE_END = datetime(2026, 10, 4, tzinfo=UTC)
_BLOCKING_EXECUTION_ERRORS = (InvalidActionTransitionError, ApprovalRequiredError)


def _insert_action(session: Session, status: ActionStatus) -> int:
    brief = Brief(
        analysis_window_start=_FIXTURE_START,
        analysis_window_end=_FIXTURE_END,
        headline="[evaluation fixture] approval boundary",
        summary="Rolled back at the end of the evaluation run.",
        status=BriefStatus.VALID,
        model_name="evaluation-fixture",
        validation_errors_json=[],
    )
    session.add(brief)
    session.flush()
    action = ProposedAction(
        brief_id=brief.id,
        action_type=ActionType.OPEN_INVESTIGATION,
        title="[evaluation fixture] Investigate Billing ticket spike",
        description="Approval-boundary evaluation fixture.",
        rationale="The anomaly warrants investigation.",
        investigation_steps_json=["Review the anomaly evidence"],
        evidence_ids_json=["ANOM-000001"],
        status=status,
    )
    session.add(action)
    # In the rollback-only session this releases a SAVEPOINT, so a service's own
    # rollback on failure cannot discard the fixture mid-case.
    session.commit()
    return action.id


def _count(session: Session, model: type[ActionExecution] | type[Approval], action_id: int) -> int:
    stmt = select(func.count()).select_from(model).where(model.action_id == action_id)
    return int(session.execute(stmt).scalar_one())


def _status(session: Session, action_id: int) -> ActionStatus:
    stmt = select(ProposedAction.status).where(ProposedAction.id == action_id)
    return session.execute(stmt).scalar_one()


def _execute_blocked(
    case: ApprovalCase,
    session: Session,
    adapters: Mapping[ActionType, InvestigationAdapter],
    status: ActionStatus,
) -> CaseResult:
    action_id = _insert_action(session, status)
    expected = "execution refused and no execution recorded"
    try:
        ActionExecutionService(session, adapters).execute(action_id)
        outcome = "executed"
        refused = False
    except _BLOCKING_EXECUTION_ERRORS as exc:
        outcome = f"refused ({type(exc).__name__})"
        refused = True
    except ActionError as exc:
        outcome = f"unexpected {type(exc).__name__}"
        refused = False
    executions = _count(session, ActionExecution, action_id)
    observed = f"{outcome}; executions recorded: {executions}"
    return verdict(
        case.case_id,
        case.title,
        CATEGORY,
        passed=refused and executions == 0,
        expected=expected,
        observed=observed,
        failure_reason=f"Approval boundary bypassed or mis-reported: {observed}",
    )


def _system_reviewer(case: ApprovalCase, session: Session) -> CaseResult:
    action_id = _insert_action(session, ActionStatus.PENDING_APPROVAL)
    reviewer = case.reviewer or "system"
    try:
        ActionApprovalService(session).approve(action_id, ApproveActionRequest(reviewer=reviewer))
        outcome, refused = "approved", False
    except ReviewerNotHumanError:
        outcome, refused = "refused (ReviewerNotHumanError)", True
    except ActionError as exc:
        outcome, refused = f"unexpected {type(exc).__name__}", False
    approvals = _count(session, Approval, action_id)
    status = _status(session, action_id)
    observed = f"{outcome}; approval records: {approvals}; status: {status.value}"
    return verdict(
        case.case_id,
        case.title,
        CATEGORY,
        passed=refused and approvals == 0 and status is ActionStatus.PENDING_APPROVAL,
        expected=f"{reviewer!r} cannot approve; action stays pending_approval",
        observed=observed,
        failure_reason=f"AI/system identity was able to decide: {observed}",
    )


def _approved_executes_once(
    case: ApprovalCase, session: Session, adapters: Mapping[ActionType, InvestigationAdapter]
) -> CaseResult:
    action_id = _insert_action(session, ActionStatus.PENDING_APPROVAL)
    reviewer = case.reviewer or "Operations Manager"
    ActionApprovalService(session).approve(action_id, ApproveActionRequest(reviewer=reviewer))
    executor = ActionExecutionService(session, adapters)
    first = executor.execute(action_id)
    second = executor.execute(action_id)
    refs = [
        None if detail.execution is None else detail.execution.external_ref
        for detail in (first, second)
    ]
    executions = _count(session, ActionExecution, action_id)
    status = _status(session, action_id)
    observed = f"status {status.value}; executions recorded: {executions}; refs: {refs}"
    return verdict(
        case.case_id,
        case.title,
        CATEGORY,
        passed=status is ActionStatus.SUCCEEDED
        and executions == 1
        and refs[0] is not None
        and refs[0] == refs[1],
        expected="succeeded with exactly one execution and a stable reference",
        observed=observed,
        failure_reason=f"Approved execution was not idempotent: {observed}",
    )


def _check(
    case: ApprovalCase, session: Session, adapters: Mapping[ActionType, InvestigationAdapter]
) -> CaseResult:
    try:
        match case.scenario:
            case "execute_without_approval":
                return _execute_blocked(case, session, adapters, ActionStatus.PENDING_APPROVAL)
            case "execute_without_approval_record":
                return _execute_blocked(case, session, adapters, ActionStatus.APPROVED)
            case "system_reviewer_approves":
                return _system_reviewer(case, session)
            case "approve_then_execute_twice":
                return _approved_executes_once(case, session, adapters)
    except Exception:
        session.rollback()  # leave the session usable for the next case
        raise


def run(ctx: EvalContext) -> list[CaseResult]:
    cases = load_approval_cases(ctx.cases_dir)
    session = ctx.session
    reason = None
    if session is None:
        reason = ctx.db_unavailable_reason or "database_unavailable"
    elif not ctx.rollback_only:
        reason = "refused: approval cases write fixtures and need a rollback-only session"
    elif not ctx.adapters:
        reason = "no investigation adapter is configured (demo/development only)"
    if reason is not None or session is None:
        why = reason or "database_unavailable"
        return [not_run(c.case_id, c.title, CATEGORY, c.expected, why) for c in cases.cases]
    return [
        guarded(
            c.case_id,
            c.title,
            CATEGORY,
            c.expected,
            partial(_check, c, session, ctx.adapters),
        )
        for c in cases.cases
    ]
