"""Read/write access for LLM call traces and the execution-outcome summary (Spec 14).

All aggregation runs in SQL so the API and UI only present computed values.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import ColumnElement, func, or_, select

from app.models.action import ActionExecution
from app.models.enums import ExecutionStatus, TraceStatus
from app.models.observability import LLMTrace
from app.repositories.base import BaseRepository


@dataclass(frozen=True)
class TraceAggregate:
    operation: str | None  # None for the all-operations total
    total_calls: int
    success_count: int
    error_count: int
    avg_latency_ms: float | None
    p50_latency_ms: float | None
    p95_latency_ms: float | None
    max_latency_ms: int | None
    input_tokens_total: int
    output_tokens_total: int
    calls_missing_usage: int
    cost_total_usd: Decimal | None  # None when no trace in the window has a cost
    calls_missing_cost: int


@dataclass(frozen=True)
class ExecutionCounts:
    total: int
    succeeded: int
    failed: int


def _window(since: datetime | None, until: datetime | None) -> list[ColumnElement[bool]]:
    conditions: list[ColumnElement[bool]] = []
    if since is not None:
        conditions.append(LLMTrace.created_at >= since)
    if until is not None:
        conditions.append(LLMTrace.created_at <= until)
    return conditions


def _aggregate_columns() -> list[Any]:
    missing_usage = or_(LLMTrace.input_tokens.is_(None), LLMTrace.output_tokens.is_(None))
    return [
        func.count(),
        func.count().filter(LLMTrace.status == TraceStatus.SUCCESS),
        func.count().filter(LLMTrace.status == TraceStatus.ERROR),
        func.avg(LLMTrace.latency_ms),
        func.percentile_cont(0.5).within_group(LLMTrace.latency_ms),
        func.percentile_cont(0.95).within_group(LLMTrace.latency_ms),
        func.max(LLMTrace.latency_ms),
        func.coalesce(func.sum(LLMTrace.input_tokens), 0),
        func.coalesce(func.sum(LLMTrace.output_tokens), 0),
        func.count().filter(missing_usage),
        func.sum(LLMTrace.estimated_cost_usd),
        func.count().filter(LLMTrace.estimated_cost_usd.is_(None)),
    ]


def _to_aggregate(operation: str | None, row: Sequence[Any]) -> TraceAggregate:
    (total, ok, err, avg, p50, p95, mx, tin, tout, missing_usage, cost, missing_cost) = row
    return TraceAggregate(
        operation=operation,
        total_calls=int(total),
        success_count=int(ok),
        error_count=int(err),
        avg_latency_ms=float(avg) if avg is not None else None,
        p50_latency_ms=float(p50) if p50 is not None else None,
        p95_latency_ms=float(p95) if p95 is not None else None,
        max_latency_ms=int(mx) if mx is not None else None,
        input_tokens_total=int(tin),
        output_tokens_total=int(tout),
        calls_missing_usage=int(missing_usage),
        cost_total_usd=cost,
        calls_missing_cost=int(missing_cost),
    )


class LLMTraceRepository(BaseRepository[LLMTrace]):
    model = LLMTrace

    def page(
        self,
        *,
        operation: str | None,
        status: TraceStatus | None,
        since: datetime | None,
        until: datetime | None,
        limit: int,
        offset: int,
    ) -> tuple[list[LLMTrace], int]:
        """Newest first, with the total matching count for pagination."""
        conditions = _window(since, until)
        if operation is not None:
            conditions.append(LLMTrace.operation == operation)
        if status is not None:
            conditions.append(LLMTrace.status == status)
        stmt = (
            select(LLMTrace)
            .where(*conditions)
            .order_by(LLMTrace.created_at.desc(), LLMTrace.id.desc())
            .limit(limit)
            .offset(offset)
        )
        total = self.session.execute(
            select(func.count()).select_from(LLMTrace).where(*conditions)
        ).scalar_one()
        return list(self.session.execute(stmt).scalars()), int(total)

    def aggregate(self, since: datetime | None, until: datetime | None) -> TraceAggregate:
        row = self.session.execute(select(*_aggregate_columns()).where(*_window(since, until)))
        return _to_aggregate(None, row.one())

    def aggregate_by_operation(
        self, since: datetime | None, until: datetime | None
    ) -> list[TraceAggregate]:
        stmt = (
            select(LLMTrace.operation, *_aggregate_columns())
            .where(*_window(since, until))
            .group_by(LLMTrace.operation)
            .order_by(LLMTrace.operation)
        )
        return [_to_aggregate(row[0], row[1:]) for row in self.session.execute(stmt)]


def _execution_window(since: datetime | None, until: datetime | None) -> list[ColumnElement[bool]]:
    conditions: list[ColumnElement[bool]] = []
    if since is not None:
        conditions.append(ActionExecution.started_at >= since)
    if until is not None:
        conditions.append(ActionExecution.started_at <= until)
    return conditions


class ExecutionOutcomeRepository(BaseRepository[ActionExecution]):
    model = ActionExecution

    def counts(self, since: datetime | None, until: datetime | None) -> ExecutionCounts:
        stmt = select(
            func.count(),
            func.count().filter(ActionExecution.status == ExecutionStatus.SUCCEEDED),
            func.count().filter(ActionExecution.status == ExecutionStatus.FAILED),
        ).where(*_execution_window(since, until))
        total, succeeded, failed = self.session.execute(stmt).one()
        return ExecutionCounts(total=int(total), succeeded=int(succeeded), failed=int(failed))

    def recent_failures(
        self, since: datetime | None, until: datetime | None, limit: int
    ) -> list[ActionExecution]:
        stmt = (
            select(ActionExecution)
            .where(
                ActionExecution.status == ExecutionStatus.FAILED,
                *_execution_window(since, until),
            )
            .order_by(
                ActionExecution.finished_at.desc().nulls_last(),
                ActionExecution.id.desc(),
            )
            .limit(limit)
        )
        return list(self.session.execute(stmt).scalars())
