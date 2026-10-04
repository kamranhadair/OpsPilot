"""Action routes: delegate to the proposal, approval and execution services; map failures.

Approval and execution are separate endpoints and separate backend transitions. The
backend enforces the state machine on every request; frontend controls are only hints.
"""

from collections.abc import Callable, Mapping
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.integrations.investigations.base import InvestigationAdapter
from app.integrations.investigations.mock import get_investigation_adapters
from app.integrations.llm.base import ActionLLMClient, LLMError
from app.integrations.llm.openai_client import get_action_llm_client
from app.models.enums import ActionStatus, ActionType
from app.schemas.actions import (
    ActionConflictResponse,
    ActionDetailOut,
    ActionEditRejectedResponse,
    ActionExecutionFailedResponse,
    ActionListOut,
    ActionOut,
    ActionProposalRejectedResponse,
    ActionTransitionConflictResponse,
    ApproveActionRequest,
    RejectActionRequest,
)
from app.schemas.health import ErrorResponse
from app.services.actions.approval_service import ActionApprovalService
from app.services.actions.errors import (
    ActionAlreadyProposedError,
    ActionEditRejectedError,
    ActionError,
    ActionExecutionFailedError,
    ActionProposalRejectedError,
    InvalidActionTransitionError,
)
from app.services.actions.execution_service import ActionExecutionService
from app.services.actions.proposer import ActionProposalService

router = APIRouter(tags=["actions"])

DbSession = Annotated[Session, Depends(get_db)]
AppSettings = Annotated[Settings, Depends(get_settings)]

LIST_DEFAULT_LIMIT = 50
LIST_MAX_LIMIT = 100


def get_action_client_factory(settings: AppSettings) -> Callable[[], ActionLLMClient]:
    """Dependency seam: tests override this with a fake client."""
    return lambda: get_action_llm_client(settings)


ClientFactory = Annotated[Callable[[], ActionLLMClient], Depends(get_action_client_factory)]


def get_adapters(settings: AppSettings) -> Mapping[ActionType, InvestigationAdapter]:
    """Dependency seam: tests override this with counting/failing adapters."""
    return get_investigation_adapters(settings)


Adapters = Annotated[Mapping[ActionType, InvestigationAdapter], Depends(get_adapters)]

_ERRORS: dict[int | str, dict[str, object]] = {
    status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
    status.HTTP_409_CONFLICT: {"model": ActionConflictResponse},
    status.HTTP_422_UNPROCESSABLE_CONTENT: {"model": ActionProposalRejectedResponse},
    status.HTTP_429_TOO_MANY_REQUESTS: {"model": ErrorResponse},
    status.HTTP_502_BAD_GATEWAY: {"model": ErrorResponse},
    status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ErrorResponse},
    status.HTTP_504_GATEWAY_TIMEOUT: {"model": ErrorResponse},
}


def _error(exc: ActionError | LLMError) -> JSONResponse:
    body: ErrorResponse
    if isinstance(exc, ActionAlreadyProposedError):
        body = ActionConflictResponse(
            code=exc.code, message=exc.message, existing_action_id=exc.existing_action_id
        )
    elif isinstance(exc, ActionProposalRejectedError):
        body = ActionProposalRejectedResponse(code=exc.code, message=exc.message, issues=exc.issues)
    elif isinstance(exc, InvalidActionTransitionError):
        body = ActionTransitionConflictResponse(
            code=exc.code, message=exc.message, current_status=exc.current_status
        )
    elif isinstance(exc, ActionEditRejectedError):
        body = ActionEditRejectedResponse(code=exc.code, message=exc.message, issues=exc.issues)
    elif isinstance(exc, ActionExecutionFailedError):
        body = ActionExecutionFailedResponse(
            code=exc.code, message=exc.message, execution=exc.execution
        )
    else:
        body = ErrorResponse(code=exc.code, message=exc.message)
    return JSONResponse(status_code=exc.http_status, content=body.model_dump(mode="json"))


@router.post(
    "/briefs/{brief_id}/actions/propose",
    response_model=ActionOut,
    status_code=status.HTTP_201_CREATED,
    responses=_ERRORS,
    summary="Draft one evidence-grounded investigation from a validated brief "
    "(ends in pending_approval)",
)
def propose_action(
    session: DbSession,
    settings: AppSettings,
    factory: ClientFactory,
    brief_id: Annotated[int, Path(gt=0)],
) -> ActionOut | JSONResponse:
    try:
        return ActionProposalService(session, settings, factory).propose(brief_id)
    except (ActionError, LLMError) as exc:
        return _error(exc)


@router.get(
    "/actions",
    response_model=ActionListOut,
    summary="Proposed actions; pending approvals first, then newest first",
)
def list_actions(
    session: DbSession,
    settings: AppSettings,
    action_status: Annotated[ActionStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=LIST_MAX_LIMIT)] = LIST_DEFAULT_LIMIT,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ActionListOut:
    return ActionProposalService(session, settings).list_actions(
        status=action_status, limit=limit, offset=offset
    )


ActionId = Annotated[int, Path(gt=0)]

_TRANSITION_ERRORS: dict[int | str, dict[str, object]] = {
    status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
    status.HTTP_409_CONFLICT: {"model": ActionTransitionConflictResponse},
}


@router.get(
    "/actions/{action_id}",
    response_model=ActionDetailOut,
    responses={status.HTTP_404_NOT_FOUND: {"model": ErrorResponse}},
    summary="One action with evidence, source brief, human decision, execution and audit trail",
)
def read_action(session: DbSession, action_id: ActionId) -> ActionDetailOut | JSONResponse:
    try:
        return ActionApprovalService(session).get_detail(action_id)
    except ActionError as exc:
        return _error(exc)


@router.post(
    "/actions/{action_id}/approve",
    response_model=ActionDetailOut,
    responses={
        **_TRANSITION_ERRORS,
        status.HTTP_422_UNPROCESSABLE_CONTENT: {"model": ActionEditRejectedResponse},
    },
    summary="Record a human approval (optionally with edits): pending_approval -> approved",
)
def approve_action(
    session: DbSession, action_id: ActionId, body: ApproveActionRequest
) -> ActionDetailOut | JSONResponse:
    try:
        return ActionApprovalService(session).approve(action_id, body)
    except ActionError as exc:
        return _error(exc)


@router.post(
    "/actions/{action_id}/reject",
    response_model=ActionDetailOut,
    responses={
        **_TRANSITION_ERRORS,
        status.HTTP_422_UNPROCESSABLE_CONTENT: {"model": ErrorResponse},
    },
    summary="Record a human rejection: pending_approval -> rejected",
)
def reject_action(
    session: DbSession, action_id: ActionId, body: RejectActionRequest
) -> ActionDetailOut | JSONResponse:
    try:
        return ActionApprovalService(session).reject(action_id, body)
    except ActionError as exc:
        return _error(exc)


@router.post(
    "/actions/{action_id}/execute",
    response_model=ActionDetailOut,
    responses={
        **_TRANSITION_ERRORS,
        status.HTTP_502_BAD_GATEWAY: {"model": ActionExecutionFailedResponse},
        status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ErrorResponse},
    },
    summary="Execute a human-approved action via its adapter (idempotent once succeeded)",
)
def execute_action(
    session: DbSession, adapters: Adapters, action_id: ActionId
) -> ActionDetailOut | JSONResponse:
    try:
        return ActionExecutionService(session, adapters).execute(action_id)
    except ActionError as exc:
        return _error(exc)
