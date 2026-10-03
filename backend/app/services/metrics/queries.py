"""Computation query layer: per-window integer aggregates straight from SQL.

Three parameterised queries cover all eight metrics for one analysis window:

1. created-cohort aggregates, bucketed by ``created_at``;
2. resolved-cohort aggregates, bucketed by ``resolved_at``;
3. point-in-time open backlog at each bucket end.

Buckets 0-6 are the baseline days (oldest first) and bucket 7 is the current
window. This module only counts and sums; formulas live in the registry.
"""

from collections.abc import Mapping
from typing import Any

from sqlalchemy import ColumnElement, Select, and_, case, func, or_, select
from sqlalchemy.orm import InstrumentedAttribute, Session

from app.models import Customer, SupportTeam, Ticket
from app.models.enums import CustomerTier, Product, Region, TicketCategory, TicketPriority
from app.services.metrics.definitions import (
    NEGATIVE_SENTIMENT_THRESHOLD,
    AggregateField,
    Dimension,
)
from app.services.metrics.engine import AnalysisWindow, TimeRange

CREATED_FIELDS = (
    AggregateField.TICKETS,
    AggregateField.P1_TICKETS,
    AggregateField.FIRST_RESPONSE_SUM,
    AggregateField.FIRST_RESPONSE_COUNT,
    AggregateField.SLA_BREACHED,
    AggregateField.ESCALATED,
    AggregateField.NEGATIVE_SENTIMENT,
)
RESOLVED_FIELDS = (AggregateField.RESOLUTION_SUM, AggregateField.RESOLUTION_COUNT)

SOURCE_TABLE = "tickets"
SOURCE_JOINS = ("customers", "support_teams")


def _filter_clause(dimension: Dimension, value: str) -> ColumnElement[bool]:
    match dimension:
        case Dimension.CATEGORY:
            return Ticket.category == TicketCategory(value)
        case Dimension.PRODUCT:
            return Ticket.product == Product(value)
        case Dimension.REGION:
            return Customer.region == Region(value)
        case Dimension.CUSTOMER_TIER:
            return Customer.tier == CustomerTier(value)
        case Dimension.SUPPORT_TEAM:
            return SupportTeam.team_key == value


def _scoped[*Ts](stmt: Select[*Ts], filters: Mapping[Dimension, str]) -> Select[*Ts]:
    stmt = stmt.select_from(Ticket).join(Customer, Ticket.customer_id == Customer.id)
    stmt = stmt.join(SupportTeam, Ticket.support_team_id == SupportTeam.id)
    for dimension, value in sorted(filters.items()):
        stmt = stmt.where(_filter_clause(dimension, value))
    return stmt


def _bucket(
    column: InstrumentedAttribute[Any], buckets: tuple[TimeRange, ...]
) -> ColumnElement[int]:
    return case(
        *[
            (and_(column >= bucket.start, column < bucket.end), index)
            for index, bucket in enumerate(buckets)
        ],
        else_=None,
    )


def _empty_buckets(count: int) -> list[dict[AggregateField, int]]:
    return [dict.fromkeys(AggregateField, 0) for _ in range(count)]


def fetch_bucket_aggregates(
    session: Session, window: AnalysisWindow, filters: Mapping[Dimension, str]
) -> list[dict[AggregateField, int]]:
    """Return one aggregate mapping per bucket (7 baseline days + current)."""
    buckets = window.buckets
    result = _empty_buckets(len(buckets))
    start, end = window.baseline.start, window.current.end

    created_bucket = _bucket(Ticket.created_at, buckets).label("bucket")
    created = _scoped(
        select(
            created_bucket,
            func.count().label(AggregateField.TICKETS),
            func.count()
            .filter(Ticket.priority == TicketPriority.P1)
            .label(AggregateField.P1_TICKETS),
            func.coalesce(func.sum(Ticket.first_response_minutes), 0).label(
                AggregateField.FIRST_RESPONSE_SUM
            ),
            func.count(Ticket.first_response_minutes).label(AggregateField.FIRST_RESPONSE_COUNT),
            func.count().filter(Ticket.sla_breached.is_(True)).label(AggregateField.SLA_BREACHED),
            func.count().filter(Ticket.escalated.is_(True)).label(AggregateField.ESCALATED),
            func.count()
            .filter(Ticket.sentiment_score <= NEGATIVE_SENTIMENT_THRESHOLD)
            .label(AggregateField.NEGATIVE_SENTIMENT),
        ),
        filters,
    )
    created = created.where(Ticket.created_at >= start, Ticket.created_at < end).group_by(
        created_bucket
    )
    for row in session.execute(created).mappings():
        for field in CREATED_FIELDS:
            result[row["bucket"]][field] = int(row[field])

    resolved_bucket = _bucket(Ticket.resolved_at, buckets).label("bucket")
    resolved = _scoped(
        select(
            resolved_bucket,
            func.coalesce(func.sum(Ticket.resolution_minutes), 0).label(
                AggregateField.RESOLUTION_SUM
            ),
            func.count(Ticket.resolution_minutes).label(AggregateField.RESOLUTION_COUNT),
        ),
        filters,
    )
    resolved = resolved.where(Ticket.resolved_at >= start, Ticket.resolved_at < end).group_by(
        resolved_bucket
    )
    for row in session.execute(resolved).mappings():
        for field in RESOLVED_FIELDS:
            result[row["bucket"]][field] = int(row[field])

    backlog = _scoped(
        select(
            *[
                func.count()
                .filter(
                    Ticket.created_at < bucket.end,
                    or_(Ticket.resolved_at.is_(None), Ticket.resolved_at >= bucket.end),
                )
                .label(f"b{index}")
                for index, bucket in enumerate(buckets)
            ]
        ),
        filters,
    ).where(Ticket.created_at < end)
    row = session.execute(backlog).mappings().one()
    for index in range(len(buckets)):
        result[index][AggregateField.OPEN_BACKLOG] = int(row[f"b{index}"])

    return result
