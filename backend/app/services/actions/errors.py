"""Expected, user-facing action failures with stable machine-readable codes."""

from app.models.enums import ActionStatus
from app.schemas.actions import ActionEditIssue, ActionProposalIssue, ExecutionOut


class ActionError(Exception):
    code: str = "ACTION_ERROR"
    http_status: int = 400

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class ActionNotFoundError(ActionError):
    code = "ACTION_NOT_FOUND"
    http_status = 404


class SourceBriefNotFoundError(ActionError):
    code = "BRIEF_NOT_FOUND"
    http_status = 404


class BriefNotValidError(ActionError):
    """Proposals are only drafted from briefs whose claims all passed validation."""

    code = "BRIEF_NOT_VALID"
    http_status = 409


class NoActionableAnomalyError(ActionError):
    code = "NO_ACTIONABLE_ANOMALY"
    http_status = 409


class ActionAlreadyProposedError(ActionError):
    """V1 allows one proposal per brief."""

    code = "ACTION_ALREADY_PROPOSED"
    http_status = 409

    def __init__(self, message: str, existing_action_id: int | None) -> None:
        super().__init__(message)
        self.existing_action_id = existing_action_id


class ActionProposalRejectedError(ActionError):
    """The model's proposal failed the deterministic policy; nothing was persisted."""

    code = "ACTION_PROPOSAL_REJECTED"
    http_status = 422

    def __init__(self, message: str, issues: list[ActionProposalIssue]) -> None:
        super().__init__(message)
        self.issues = issues


# --- Spec 12: approval and execution ------------------------------------------------------


class InvalidActionTransitionError(ActionError):
    """The action's current state does not allow the requested transition (incl. stale UI)."""

    code = "ACTION_INVALID_TRANSITION"
    http_status = 409

    def __init__(self, message: str, current_status: ActionStatus | None) -> None:
        super().__init__(message)
        self.current_status = current_status


class ApprovalRequiredError(ActionError):
    """Execution fails closed when no recorded human approval exists."""

    code = "APPROVAL_REQUIRED"
    http_status = 409


class UnsupportedActionTypeError(ActionError):
    code = "UNSUPPORTED_ACTION_TYPE"
    http_status = 409


class ReviewerNotHumanError(ActionError):
    """The reviewer identity names the AI/system; only a human may decide."""

    code = "REVIEWER_NOT_HUMAN"
    http_status = 422


class ActionEditRejectedError(ActionError):
    code = "ACTION_EDIT_REJECTED"
    http_status = 422

    def __init__(self, message: str, issues: list[ActionEditIssue]) -> None:
        super().__init__(message)
        self.issues = issues


class AdapterNotConfiguredError(ActionError):
    code = "ADAPTER_NOT_CONFIGURED"
    http_status = 503


class ActionExecutionFailedError(ActionError):
    """The adapter failed; the failed execution has been persisted."""

    code = "ACTION_EXECUTION_FAILED"
    http_status = 502

    def __init__(self, message: str, execution: ExecutionOut) -> None:
        super().__init__(message)
        self.execution = execution
