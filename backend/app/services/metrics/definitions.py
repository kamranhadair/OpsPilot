"""Central metric registry: the single source of truth for metric formulas.

Each definition names the aggregate fields (produced by ``queries``) that form
its numerator/denominator. The engine applies these declarations generically,
so no formula is restated anywhere else in the codebase.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from types import MappingProxyType


class MetricUnit(StrEnum):
    COUNT = "count"
    MINUTES = "minutes"
    PERCENT = "percent"


class Aggregation(StrEnum):
    COUNT = "count"
    POINT_IN_TIME_COUNT = "point_in_time_count"
    MEAN = "mean"
    RATE = "rate"


class Direction(StrEnum):
    """Which direction of change is operationally worse."""

    HIGHER_IS_WORSE = "higher_is_worse"
    HIGHER_IS_BETTER = "higher_is_better"


class Dimension(StrEnum):
    CATEGORY = "category"
    PRODUCT = "product"
    REGION = "region"
    CUSTOMER_TIER = "customer_tier"
    SUPPORT_TEAM = "support_team"


class Cohort(StrEnum):
    """Which tickets belong to a window."""

    CREATED_IN_WINDOW = "created_in_window"
    RESOLVED_IN_WINDOW = "resolved_in_window"
    OPEN_AT_WINDOW_END = "open_at_window_end"


class BaselineMethod(StrEnum):
    # Mean of the seven daily values (count/average metrics).
    MEAN_OF_DAILY_VALUES = "mean_of_daily_values"
    # Sum of daily numerators / sum of daily denominators (rate metrics).
    POOLED_RATE = "pooled_rate"


class AggregateField(StrEnum):
    """Per-window integer aggregates produced by the computation query layer."""

    TICKETS = "tickets"
    P1_TICKETS = "p1_tickets"
    FIRST_RESPONSE_SUM = "first_response_minutes_sum"
    FIRST_RESPONSE_COUNT = "first_response_minutes_count"
    SLA_BREACHED = "sla_breached_tickets"
    ESCALATED = "escalated_tickets"
    NEGATIVE_SENTIMENT = "negative_sentiment_tickets"
    RESOLUTION_SUM = "resolution_minutes_sum"
    RESOLUTION_COUNT = "resolution_minutes_count"
    OPEN_BACKLOG = "open_backlog_tickets"


# A ticket counts as negative sentiment at or below this score (range [-1, 1]).
NEGATIVE_SENTIMENT_THRESHOLD = Decimal("-0.30")

ALL_DIMENSIONS: frozenset[Dimension] = frozenset(Dimension)


@dataclass(frozen=True)
class MetricDefinition:
    key: str
    display_name: str
    description: str
    unit: MetricUnit
    aggregation: Aggregation
    cohort: Cohort
    formula: str
    numerator: AggregateField
    denominator: AggregateField | None
    direction: Direction
    baseline_method: BaselineMethod
    supported_dimensions: frozenset[Dimension] = ALL_DIMENSIONS
    min_sample_size: int | None = None
    version: int = 1

    @property
    def is_rate(self) -> bool:
        return self.aggregation is Aggregation.RATE

    @property
    def sample_field(self) -> AggregateField:
        """The aggregate counted as the sample size for this metric."""
        return self.denominator or self.numerator


_DEFINITIONS: tuple[MetricDefinition, ...] = (
    MetricDefinition(
        key="ticket_volume",
        display_name="Ticket volume",
        description="Tickets created in the window.",
        unit=MetricUnit.COUNT,
        aggregation=Aggregation.COUNT,
        cohort=Cohort.CREATED_IN_WINDOW,
        formula="count(tickets)",
        numerator=AggregateField.TICKETS,
        denominator=None,
        direction=Direction.HIGHER_IS_WORSE,
        baseline_method=BaselineMethod.MEAN_OF_DAILY_VALUES,
    ),
    MetricDefinition(
        key="open_backlog",
        display_name="Open backlog",
        description="Tickets created before the window end and not resolved by it.",
        unit=MetricUnit.COUNT,
        aggregation=Aggregation.POINT_IN_TIME_COUNT,
        cohort=Cohort.OPEN_AT_WINDOW_END,
        formula=(
            "count(tickets where created_at < end and (resolved_at is null or resolved_at >= end))"
        ),
        numerator=AggregateField.OPEN_BACKLOG,
        denominator=None,
        direction=Direction.HIGHER_IS_WORSE,
        baseline_method=BaselineMethod.MEAN_OF_DAILY_VALUES,
    ),
    MetricDefinition(
        key="p1_ticket_volume",
        display_name="P1 ticket volume",
        description="Priority-1 tickets created in the window.",
        unit=MetricUnit.COUNT,
        aggregation=Aggregation.COUNT,
        cohort=Cohort.CREATED_IN_WINDOW,
        formula="count(tickets where priority = 'p1')",
        numerator=AggregateField.P1_TICKETS,
        denominator=None,
        direction=Direction.HIGHER_IS_WORSE,
        baseline_method=BaselineMethod.MEAN_OF_DAILY_VALUES,
    ),
    MetricDefinition(
        key="first_response_minutes",
        display_name="Avg first response",
        description="Mean first-response minutes of tickets created in the window.",
        unit=MetricUnit.MINUTES,
        aggregation=Aggregation.MEAN,
        cohort=Cohort.CREATED_IN_WINDOW,
        formula="sum(first_response_minutes) / count(first_response_minutes)",
        numerator=AggregateField.FIRST_RESPONSE_SUM,
        denominator=AggregateField.FIRST_RESPONSE_COUNT,
        direction=Direction.HIGHER_IS_WORSE,
        baseline_method=BaselineMethod.MEAN_OF_DAILY_VALUES,
        min_sample_size=20,
    ),
    MetricDefinition(
        key="resolution_minutes",
        display_name="Avg resolution time",
        description=(
            "Mean resolution minutes of tickets resolved in the window. The resolved "
            "cohort avoids biasing recent windows toward quickly resolved tickets."
        ),
        unit=MetricUnit.MINUTES,
        aggregation=Aggregation.MEAN,
        cohort=Cohort.RESOLVED_IN_WINDOW,
        formula="sum(resolution_minutes) / count(resolution_minutes)",
        numerator=AggregateField.RESOLUTION_SUM,
        denominator=AggregateField.RESOLUTION_COUNT,
        direction=Direction.HIGHER_IS_WORSE,
        baseline_method=BaselineMethod.MEAN_OF_DAILY_VALUES,
        min_sample_size=20,
    ),
    MetricDefinition(
        key="sla_breach_rate",
        display_name="SLA breach rate",
        description="Share of tickets created in the window that breached their SLA.",
        unit=MetricUnit.PERCENT,
        aggregation=Aggregation.RATE,
        cohort=Cohort.CREATED_IN_WINDOW,
        formula="count(tickets where sla_breached) / count(tickets) * 100",
        numerator=AggregateField.SLA_BREACHED,
        denominator=AggregateField.TICKETS,
        direction=Direction.HIGHER_IS_WORSE,
        baseline_method=BaselineMethod.POOLED_RATE,
        min_sample_size=20,
    ),
    MetricDefinition(
        key="escalation_rate",
        display_name="Escalation rate",
        description="Share of tickets created in the window that were escalated.",
        unit=MetricUnit.PERCENT,
        aggregation=Aggregation.RATE,
        cohort=Cohort.CREATED_IN_WINDOW,
        formula="count(tickets where escalated) / count(tickets) * 100",
        numerator=AggregateField.ESCALATED,
        denominator=AggregateField.TICKETS,
        direction=Direction.HIGHER_IS_WORSE,
        baseline_method=BaselineMethod.POOLED_RATE,
        min_sample_size=20,
    ),
    MetricDefinition(
        key="negative_sentiment_rate",
        display_name="Negative sentiment rate",
        description=(
            "Share of tickets created in the window with sentiment score "
            f"<= {NEGATIVE_SENTIMENT_THRESHOLD}."
        ),
        unit=MetricUnit.PERCENT,
        aggregation=Aggregation.RATE,
        cohort=Cohort.CREATED_IN_WINDOW,
        formula=(
            f"count(tickets where sentiment_score <= {NEGATIVE_SENTIMENT_THRESHOLD}) "
            "/ count(tickets) * 100"
        ),
        numerator=AggregateField.NEGATIVE_SENTIMENT,
        denominator=AggregateField.TICKETS,
        direction=Direction.HIGHER_IS_WORSE,
        baseline_method=BaselineMethod.POOLED_RATE,
        min_sample_size=20,
    ),
)

METRIC_REGISTRY: Mapping[str, MetricDefinition] = MappingProxyType(
    {definition.key: definition for definition in _DEFINITIONS}
)


def get_metric_definition(key: str) -> MetricDefinition | None:
    return METRIC_REGISTRY.get(key)
