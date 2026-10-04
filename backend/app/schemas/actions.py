"""Typed contracts for AI action proposals.

``ActionProposalOutput`` is what the model must return. ``action_type`` is a plain
string on purpose: the backend allow-list (``services/actions/policy.py``) rejects an
unsupported type explicitly instead of it surfacing as a parse failure. Cited IDs are
accepted structurally here and judged afterwards by the deterministic proposal policy;
they are never repaired.
"""

from datetime import datetime
from typing import Annotated, Literal, Self

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    model_validator,
)

from app.models.enums import (
    ActionStatus,
    ActionType,
    ActorType,
    ApprovalDecision,
    BriefStatus,
    ClaimType,
    ExecutionStatus,
)
from app.schemas.evidence import EvidenceDetailOut, WindowOut
from app.schemas.health import ErrorResponse


def _not_blank(value: str) -> str:
    """Reject whitespace-only text without altering what the model wrote."""
    if not value.strip():
        raise ValueError("must not be blank")
    return value


NonBlankText = Annotated[str, AfterValidator(_not_blank)]


class ActionProposalOutput(BaseModel):
    """The structured answer required from the model."""

    model_config = ConfigDict(extra="forbid")

    action_type: str
    title: NonBlankText = Field(max_length=300)
    description: NonBlankText
    rationale: NonBlankText
    investigation_steps: list[NonBlankText] = Field(min_length=1)
    evidence_ids: list[str] = Field(min_length=1)


class ContextClaim(BaseModel):
    """A validated brief claim as shown to the model."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    claim_type: ClaimType
    text: str
    evidence_ids: list[str]


class ActionProposalContext(BaseModel):
    """The model's entire input: one validated brief and its resolved evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    brief_id: int
    analysis_window: WindowOut
    headline: str
    summary: str
    claims: list[ContextClaim]
    allowed_action_types: list[ActionType]
    allowed_evidence_ids: list[str] = Field(description="Sorted; the only citable IDs.")
    evidence: list[EvidenceDetailOut]


ActionProposalIssueCode = Literal[
    "UNSUPPORTED_ACTION_TYPE",
    "EVIDENCE_MISSING",
    "EVIDENCE_NOT_IN_BRIEF",
    "EVIDENCE_UNRESOLVED",
    "ANOMALY_EVIDENCE_MISSING",
    "CAUSAL_LANGUAGE",
    "ACTION_CLAIMED_COMPLETE",
]

ProposalField = Literal["action_type", "title", "description", "rationale", "investigation_steps"]


class ActionProposalIssue(BaseModel):
    """One deterministic reason a model proposal was rejected."""

    model_config = ConfigDict(extra="forbid")

    code: ActionProposalIssueCode
    message: str
    evidence_id: str | None = None
    phrase: str | None = Field(default=None, description="The prohibited phrase that matched.")
    field: ProposalField | None = None


class ActionSourceBriefOut(BaseModel):
    id: int
    headline: str
    status: BriefStatus
    analysis_window_start: AwareDatetime
    analysis_window_end: AwareDatetime


class ActionOut(BaseModel):
    id: int
    action_type: ActionType
    title: str
    description: str
    rationale: str
    investigation_steps: list[str]
    evidence_ids: list[str]
    status: ActionStatus = Field(
        description="pending_approval: drafted by AI and awaiting a human decision. "
        "approved/rejected require a recorded human decision; executing/succeeded/failed "
        "follow only from a human approval. The system never approves an action."
    )
    source_brief: ActionSourceBriefOut
    created_at: datetime
    updated_at: datetime


class ActionListOut(BaseModel):
    items: list[ActionOut]
    limit: int
    offset: int


class ActionConflictResponse(ErrorResponse):
    """409 body; ``existing_action_id`` is set for ``ACTION_ALREADY_PROPOSED``."""

    existing_action_id: int | None = None


class ActionProposalRejectedResponse(ErrorResponse):
    """422 body for a model proposal that failed the deterministic policy."""

    issues: list[ActionProposalIssue]


# --- Spec 12: human approval and execution ------------------------------------------------

ActionOperation = Literal["approve", "reject", "execute"]
EditableField = Literal["title", "description", "investigation_steps"]

Reviewer = Annotated[
    NonBlankText,
    Field(
        max_length=200,
        description="Demo reviewer identity (e.g. 'Operations Manager'). V1 has no "
        "authentication; this is recorded, not verified.",
    ),
]


class ActionEdits(BaseModel):
    """Human edits applied at approval. Evidence, action type and rationale are not editable."""

    model_config = ConfigDict(extra="forbid")

    title: NonBlankText | None = Field(default=None, max_length=300)
    description: NonBlankText | None = None
    investigation_steps: list[NonBlankText] | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def _at_least_one(self) -> Self:
        if self.title is None and self.description is None and self.investigation_steps is None:
            raise ValueError("edits must change at least one field")
        return self


class ApproveActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reviewer: Reviewer
    comment: str | None = Field(default=None, max_length=2000)
    edits: ActionEdits | None = None


class RejectActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reviewer: Reviewer
    comment: str | None = Field(default=None, max_length=2000)


class ApprovalOut(BaseModel):
    id: int
    decision: ApprovalDecision
    reviewer: str
    comment: str | None
    edited_fields: list[EditableField] = Field(
        description="Fields the reviewer changed; before/after values are in the audit trail."
    )
    decided_at: AwareDatetime


class ExecutionOut(BaseModel):
    id: int
    status: ExecutionStatus
    adapter_key: str
    external_ref: str | None = Field(description="Mock investigation reference, e.g. INV-0001.")
    error_message: str | None
    started_at: AwareDatetime
    finished_at: AwareDatetime | None


class AuditEventOut(BaseModel):
    id: int
    actor_type: ActorType
    actor_id: str | None
    event_type: str
    payload: dict[str, JsonValue]
    created_at: AwareDatetime


class ActionDetailOut(ActionOut):
    """One action with its human decision, execution outcome and audit timeline."""

    approval: ApprovalOut | None
    execution: ExecutionOut | None
    audit_events: list[AuditEventOut] = Field(description="Oldest first.")
    allowed_operations: list[ActionOperation] = Field(
        description="Transitions the backend would currently accept. Presentation hint only; "
        "every request is re-checked server side."
    )


class ActionTransitionConflictResponse(ErrorResponse):
    """409 body for a transition the current state does not allow."""

    current_status: ActionStatus | None = None


class ActionEditIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: Literal["CAUSAL_LANGUAGE", "ACTION_CLAIMED_COMPLETE"]
    message: str
    phrase: str
    field: EditableField


class ActionEditRejectedResponse(ErrorResponse):
    issues: list[ActionEditIssue]


class ActionExecutionFailedResponse(ErrorResponse):
    """502 body; the failed execution is persisted and returned for display."""

    execution: ExecutionOut
