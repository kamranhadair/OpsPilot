"""Typed contracts for AI operations briefs.

``BriefDraftOutput`` is what the model must return. It is validated structurally here;
whether the cited IDs are actually in the Evidence Bundle is checked afterwards by the
deterministic claim validator, so unknown IDs are accepted at this layer and never repaired.
"""

from datetime import datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from app.models.enums import BriefStatus, ClaimType, ClaimValidationStatus


class DraftClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_type: ClaimType
    text: str = Field(min_length=1)
    evidence_ids: list[str] = Field(min_length=1)


class BriefDraftOutput(BaseModel):
    """The structured answer required from the model."""

    model_config = ConfigDict(extra="forbid")

    headline: str = Field(min_length=1, max_length=500)
    summary: str = Field(min_length=1)
    claims: list[DraftClaim]
    attention_items: list[str]


ValidationIssueCode = Literal[
    "EVIDENCE_MISSING",
    "EVIDENCE_NOT_IN_BUNDLE",
    "EVIDENCE_UNRESOLVED",
    "EVIDENCE_WINDOW_MISMATCH",
    "CAUSAL_LANGUAGE_FOR_EVENT",
    "CAUSAL_LANGUAGE_IN_NARRATIVE",
    "BRIEF_HAS_NO_CLAIMS",
]


class ValidationIssue(BaseModel):
    """One deterministic validation failure, persisted on the claim and the brief."""

    model_config = ConfigDict(extra="forbid")

    code: ValidationIssueCode
    message: str
    evidence_id: str | None = None
    phrase: str | None = Field(default=None, description="The prohibited phrase that matched.")
    claim_ordinal: int | None = Field(
        default=None, description="Set on brief-level copies of claim issues."
    )
    field: Literal["headline", "summary"] | None = Field(
        default=None, description="Set for narrative (headline/summary) issues."
    )


class BriefClaimOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ordinal: int
    claim_type: ClaimType
    text: str
    evidence_ids: list[str]
    validation_status: ClaimValidationStatus
    validation_errors: list[ValidationIssue]


class BriefOut(BaseModel):
    id: int
    analysis_window_start: AwareDatetime
    analysis_window_end: AwareDatetime
    headline: str
    summary: str
    status: BriefStatus = Field(
        description="valid: every claim passed validation; invalid: see validation_errors; "
        "draft: never validated. Only 'valid' briefs are validated operational truth."
    )
    model_name: str
    validation_errors: list[ValidationIssue]
    created_at: datetime
    claims: list[BriefClaimOut]


class BriefGenerateResponse(BriefOut):
    attention_items: list[str] = Field(
        description="Investigation focus suggested by the model. Not persisted in V1."
    )
