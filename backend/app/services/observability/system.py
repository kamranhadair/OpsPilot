"""System health, trace listing and summary use cases (Spec 14).

Internal/demo inspection only: every call is refused outside demo environments. The
responses carry configuration *readiness* (booleans, the model name, the migration
revision), never secrets or connection strings.
"""

import contextlib
import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.logging import log_event
from app.evals.store import EvaluationReportInvalidError, read_latest
from app.models.enums import TraceStatus
from app.repositories.observability import (
    ExecutionOutcomeRepository,
    LLMTraceRepository,
    TraceAggregate,
)
from app.schemas.system import (
    CostReadiness,
    DatabaseReadiness,
    EvaluationReadiness,
    ExecutionFailureOut,
    ExecutionSummary,
    LatencySummary,
    LLMReadiness,
    LLMSummary,
    LLMTraceListOut,
    LLMTraceOut,
    OperationSummary,
    SummaryPeriod,
    SystemHealthResponse,
    SystemSummaryOut,
)
from app.services.observability.errors import (
    InvalidTraceFilterError,
    SystemEndpointsDisabledError,
)

logger = logging.getLogger(__name__)

PERIODS: dict[SummaryPeriod, timedelta | None] = {
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
    "all": None,
}
RECENT_FAILURES_LIMIT = 5
_RATE_DIGITS = 4


def _rate(part: int, total: int) -> float | None:
    return round(part / total, _RATE_DIGITS) if total else None


def _usd(value: Decimal | None) -> float | None:
    return float(value) if value is not None else None


class SystemService:
    def __init__(self, session: Session, settings: Settings, now: datetime | None = None) -> None:
        self.session = session
        self.settings = settings
        self._now = now
        self.traces = LLMTraceRepository(session)
        self.executions = ExecutionOutcomeRepository(session)

    def _ensure_enabled(self) -> None:
        if not self.settings.is_demo_environment:
            raise SystemEndpointsDisabledError(
                "System inspection endpoints are disabled outside demo environments."
            )

    def _now_utc(self) -> datetime:
        return self._now or datetime.now(UTC)

    # --- health --------------------------------------------------------------------

    def health(self) -> SystemHealthResponse:
        """Readiness of the database and configuration. ``status`` is ``error`` when the
        database is unreachable; the route maps that to 503."""
        self._ensure_enabled()
        database = self._database()
        llm = LLMReadiness(
            configured=self.settings.llm_configured,
            model=self.settings.openai_model if self.settings.llm_configured else None,
        )
        if database.status == "error":
            overall = "error"
        elif not llm.configured:
            overall = "degraded"
        else:
            overall = "ok"
        return SystemHealthResponse(
            status=overall,
            service=self.settings.service_name,
            environment=self.settings.environment,
            database=database,
            llm=llm,
            cost_estimation=CostReadiness(configured=self.settings.cost_estimation_configured),
            evaluation=EvaluationReadiness(
                model_enabled=self.settings.eval_model_enabled,
                latest_report=self._latest_report_state(),
            ),
            checked_at=self._now_utc(),
        )

    def _database(self) -> DatabaseReadiness:
        try:
            self.session.execute(text("SELECT 1"))
        except SQLAlchemyError as exc:
            self._rollback()
            # Class name only: the error text can carry the connection string.
            log_event(
                logger, logging.ERROR, "system.database_unavailable", error_type=type(exc).__name__
            )
            return DatabaseReadiness(status="error", migration_revision=None)
        try:
            revision = self.session.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one_or_none()
        except SQLAlchemyError:
            self._rollback()
            revision = None
        return DatabaseReadiness(status="ok", migration_revision=revision)

    def _rollback(self) -> None:
        """Best effort: a dead connection can fail the rollback too."""
        with contextlib.suppress(SQLAlchemyError):
            self.session.rollback()

    def _latest_report_state(self) -> str:
        try:
            report = read_latest(Path(self.settings.eval_reports_dir))
        except EvaluationReportInvalidError:
            return "invalid"
        return "available" if report is not None else "not_run"

    # --- traces --------------------------------------------------------------------

    def list_traces(
        self,
        *,
        operation: str | None,
        status: TraceStatus | None,
        since: datetime | None,
        until: datetime | None,
        limit: int,
        offset: int,
    ) -> LLMTraceListOut:
        self._ensure_enabled()
        if since is not None and until is not None and since > until:
            raise InvalidTraceFilterError("'since' must not be later than 'until'.")
        rows, total = self.traces.page(
            operation=operation,
            status=status,
            since=since,
            until=until,
            limit=limit,
            offset=offset,
        )
        return LLMTraceListOut(
            items=[LLMTraceOut.model_validate(row) for row in rows],
            total=total,
            limit=limit,
            offset=offset,
        )

    # --- summary -------------------------------------------------------------------

    def summary(self, period: SummaryPeriod) -> SystemSummaryOut:
        self._ensure_enabled()
        window_end = self._now_utc()
        span = PERIODS[period]
        window_start = window_end - span if span is not None else None

        total = self.traces.aggregate(window_start, window_end)
        by_operation = self.traces.aggregate_by_operation(window_start, window_end)
        counts = self.executions.counts(window_start, window_end)
        failures = self.executions.recent_failures(window_start, window_end, RECENT_FAILURES_LIMIT)
        return SystemSummaryOut(
            period=period,
            window_start=window_start,
            window_end=window_end,
            llm=self._llm_summary(total, by_operation),
            executions=ExecutionSummary(
                total=counts.total,
                succeeded=counts.succeeded,
                failed=counts.failed,
                recent_failures=[
                    ExecutionFailureOut(
                        execution_id=row.id,
                        action_id=row.action_id,
                        adapter_key=row.adapter_key,
                        error_code=_error_code(row.response_json),
                        error_message=row.error_message,
                        started_at=row.started_at,
                        finished_at=row.finished_at,
                    )
                    for row in failures
                ],
            ),
        )

    def _llm_summary(self, total: TraceAggregate, by_operation: list[TraceAggregate]) -> LLMSummary:
        latency = None
        if total.total_calls and total.avg_latency_ms is not None:
            latency = LatencySummary(
                avg=round(total.avg_latency_ms, 2),
                p50=round(total.p50_latency_ms or 0.0, 2),
                p95=round(total.p95_latency_ms or 0.0, 2),
                max=total.max_latency_ms or 0,
            )
        return LLMSummary(
            total_calls=total.total_calls,
            success_count=total.success_count,
            error_count=total.error_count,
            error_rate=_rate(total.error_count, total.total_calls),
            latency_ms=latency,
            input_tokens_total=total.input_tokens_total,
            output_tokens_total=total.output_tokens_total,
            calls_missing_usage=total.calls_missing_usage,
            cost_configured=self.settings.cost_estimation_configured,
            estimated_cost_usd=_usd(total.cost_total_usd),
            calls_missing_cost=total.calls_missing_cost,
            by_operation=[
                OperationSummary(
                    operation=op.operation or "",
                    total_calls=op.total_calls,
                    error_count=op.error_count,
                    error_rate=_rate(op.error_count, op.total_calls),
                    avg_latency_ms=(
                        round(op.avg_latency_ms, 2) if op.avg_latency_ms is not None else None
                    ),
                    input_tokens_total=op.input_tokens_total,
                    output_tokens_total=op.output_tokens_total,
                    estimated_cost_usd=_usd(op.cost_total_usd),
                )
                for op in by_operation
            ],
        )


def _error_code(response: object) -> str | None:
    if isinstance(response, dict):
        code = response.get("error_code")
        return code if isinstance(code, str) else None
    return None
