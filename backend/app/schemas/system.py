"""Typed contracts for the internal/demo system endpoints (Spec 14).

Only safe metadata crosses this boundary: no secrets, connection strings, prompts or
model output. Every rate and aggregate is computed by the backend.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import TraceStatus
from app.schemas.health import ErrorResponse

SummaryPeriod = Literal["24h", "7d", "30d", "all"]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DatabaseReadiness(_Model):
    status: Literal["ok", "error"]
    migration_revision: str | None = Field(
        description="Applied Alembic revision, or null when it could not be read."
    )


class LLMReadiness(_Model):
    configured: bool = Field(description="True when an API key and model are configured.")
    model: str | None = Field(description="Configured model name; never the key.")


class CostReadiness(_Model):
    configured: bool = Field(description="True only when both token prices are configured.")


class EvaluationReadiness(_Model):
    model_enabled: bool
    latest_report: Literal["available", "not_run", "invalid"]


class SystemHealthResponse(_Model):
    status: Literal["ok", "degraded", "error"] = Field(
        description="error: the database is unreachable. degraded: the service works but an "
        "optional capability (the LLM) is not configured. ok: everything is ready."
    )
    service: str
    environment: str
    database: DatabaseReadiness
    llm: LLMReadiness
    cost_estimation: CostReadiness
    evaluation: EvaluationReadiness
    checked_at: datetime


class SystemHealthErrorResponse(ErrorResponse):
    """503 body: the stable error code plus the readiness detail that was gathered."""

    health: SystemHealthResponse


class LLMTraceOut(_Model):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: int
    operation: str
    model_name: str
    status: TraceStatus
    latency_ms: int
    input_tokens: int | None = Field(description="Null when the provider reported no usage.")
    output_tokens: int | None = Field(description="Null when the provider reported no usage.")
    estimated_cost_usd: float | None = Field(
        description="Null when prices are not configured or usage was not reported."
    )
    error_code: str | None
    error_message: str | None = Field(description="Safe, redacted provider error summary.")
    brief_id: int | None
    action_id: int | None
    request_id: str | None
    created_at: datetime


class LLMTraceListOut(_Model):
    items: list[LLMTraceOut]
    total: int
    limit: int
    offset: int


class LatencySummary(_Model):
    avg: float
    p50: float
    p95: float
    max: int


class OperationSummary(_Model):
    operation: str
    total_calls: int
    error_count: int
    error_rate: float | None
    avg_latency_ms: float | None
    input_tokens_total: int
    output_tokens_total: int
    estimated_cost_usd: float | None


class LLMSummary(_Model):
    total_calls: int
    success_count: int
    error_count: int
    error_rate: float | None = Field(description="error_count / total_calls; null with no calls.")
    latency_ms: LatencySummary | None = Field(description="Null when there are no calls.")
    input_tokens_total: int
    output_tokens_total: int
    calls_missing_usage: int = Field(description="Calls whose token usage was not reported.")
    cost_configured: bool
    estimated_cost_usd: float | None = Field(
        description="Sum of per-call estimates; null when no call in the window has one."
    )
    calls_missing_cost: int
    by_operation: list[OperationSummary]


class ExecutionFailureOut(_Model):
    execution_id: int
    action_id: int
    adapter_key: str
    error_code: str | None
    error_message: str | None
    started_at: datetime
    finished_at: datetime | None


class ExecutionSummary(_Model):
    total: int
    succeeded: int
    failed: int
    recent_failures: list[ExecutionFailureOut]


class SystemSummaryOut(_Model):
    period: SummaryPeriod
    window_start: datetime | None = Field(description="Null for period 'all'.")
    window_end: datetime
    llm: LLMSummary
    executions: ExecutionSummary
