"""Proposed actions, human approvals and execution attempts."""

from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import (
    Base,
    JSONBType,
    OptionalJSONBType,
    RowTimestampsMixin,
    UTCDateTime,
    str_enum,
)
from app.models.enums import ActionStatus, ActionType, ApprovalDecision, ExecutionStatus


class ProposedAction(RowTimestampsMixin, Base):
    """One proposal per brief in V1 (unique ``brief_id``)."""

    __tablename__ = "proposed_actions"

    id: Mapped[int] = mapped_column(primary_key=True)
    brief_id: Mapped[int] = mapped_column(ForeignKey("briefs.id", ondelete="RESTRICT"), unique=True)
    action_type: Mapped[ActionType] = mapped_column(str_enum(ActionType, "action_type"))
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text)
    rationale: Mapped[str] = mapped_column(Text)
    investigation_steps_json: Mapped[list[str]] = mapped_column(
        JSONBType, server_default=text("'[]'::jsonb")
    )
    evidence_ids_json: Mapped[list[str]] = mapped_column(JSONBType)
    status: Mapped[ActionStatus] = mapped_column(str_enum(ActionStatus, "action_status"))


class Approval(Base):
    """The single human decision on an action (unique ``action_id``)."""

    __tablename__ = "approvals"

    id: Mapped[int] = mapped_column(primary_key=True)
    action_id: Mapped[int] = mapped_column(
        ForeignKey("proposed_actions.id", ondelete="RESTRICT"), unique=True
    )
    decision: Mapped[ApprovalDecision] = mapped_column(
        str_enum(ApprovalDecision, "approval_decision")
    )
    reviewer: Mapped[str] = mapped_column(String(200))
    comment: Mapped[str | None] = mapped_column(Text)
    edited_payload_json: Mapped[dict[str, Any] | None] = mapped_column(OptionalJSONBType)
    decided_at: Mapped[datetime] = mapped_column(UTCDateTime)


class ActionExecution(Base):
    """The single execution attempt for an action (unique ``action_id``; failure is terminal)."""

    __tablename__ = "action_executions"

    id: Mapped[int] = mapped_column(primary_key=True)
    action_id: Mapped[int] = mapped_column(
        ForeignKey("proposed_actions.id", ondelete="RESTRICT"), unique=True
    )
    adapter_key: Mapped[str] = mapped_column(String(100))
    external_ref: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[ExecutionStatus] = mapped_column(str_enum(ExecutionStatus, "execution_status"))
    request_json: Mapped[dict[str, Any]] = mapped_column(JSONBType)
    response_json: Mapped[dict[str, Any]] = mapped_column(JSONBType)
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
