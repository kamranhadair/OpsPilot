"""LLM call traces and the append-only audit log.

Traces store metadata only. Never persist raw model requests or secrets here.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, JSONBType, UTCDateTime, str_enum
from app.models.enums import ActorType, TraceStatus


class LLMTrace(Base):
    __tablename__ = "llm_traces"
    __table_args__ = (
        CheckConstraint("latency_ms >= 0", name="latency_nonneg"),
        Index("ix_llm_traces_brief_id", "brief_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    brief_id: Mapped[int | None] = mapped_column(ForeignKey("briefs.id", ondelete="SET NULL"))
    operation: Mapped[str] = mapped_column(String(100))
    model_name: Mapped[str] = mapped_column(String(100))
    latency_ms: Mapped[int] = mapped_column(Integer)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    estimated_cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    status: Mapped[TraceStatus] = mapped_column(str_enum(TraceStatus, "trace_status"))
    error_code: Mapped[str | None] = mapped_column(String(100))
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, server_default=func.now())


class AuditLog(Base):
    """Append-only: application code only inserts (see ``AuditLogRepository``)."""

    __tablename__ = "audit_logs"
    __table_args__ = (Index("ix_audit_logs_entity", "entity_type", "entity_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    actor_type: Mapped[ActorType] = mapped_column(str_enum(ActorType, "audit_actor_type"))
    actor_id: Mapped[str | None] = mapped_column(String(200))
    event_type: Mapped[str] = mapped_column(String(100))
    entity_type: Mapped[str] = mapped_column(String(100))
    entity_id: Mapped[str] = mapped_column(String(100))
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSONBType)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, server_default=func.now())
