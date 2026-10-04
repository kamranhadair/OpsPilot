"""The investigation adapter boundary.

The action service only knows this protocol; no tracker-specific API (Jira or
otherwise) leaks past an adapter implementation.
"""

from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from app.models.enums import ActionType


class InvestigationRequest(BaseModel):
    """The human-approved action content handed to an adapter."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    action_id: int
    action_type: ActionType
    title: str
    description: str
    investigation_steps: list[str]
    evidence_ids: list[str]
    approval_id: int
    approved_by: str


class InvestigationResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    external_ref: str = Field(min_length=1, max_length=200)
    response: dict[str, JsonValue] = Field(default_factory=dict)


class InvestigationAdapterError(Exception):
    """An expected adapter failure. ``safe_message`` may be shown to users and stored."""

    def __init__(self, code: str, safe_message: str) -> None:
        super().__init__(safe_message)
        self.code = code
        self.safe_message = safe_message


class InvestigationAdapter(Protocol):
    adapter_key: str

    def create_investigation(self, request: InvestigationRequest) -> InvestigationResult: ...
