"""The metric registry is complete, central, and self-consistent."""

import pytest

from app.services.metrics.definitions import (
    METRIC_REGISTRY,
    Aggregation,
    BaselineMethod,
    Dimension,
    MetricDefinition,
    MetricUnit,
    get_metric_definition,
)

SPEC_METRIC_KEYS = {
    "ticket_volume",
    "open_backlog",
    "p1_ticket_volume",
    "first_response_minutes",
    "resolution_minutes",
    "sla_breach_rate",
    "escalation_rate",
    "negative_sentiment_rate",
}
SPEC_DIMENSIONS = {"category", "product", "region", "customer_tier", "support_team"}


def test_registry_contains_exactly_the_eight_spec_metrics() -> None:
    assert set(METRIC_REGISTRY) == SPEC_METRIC_KEYS


def test_supported_dimensions_are_the_spec_dimensions() -> None:
    assert {d.value for d in Dimension} == SPEC_DIMENSIONS


@pytest.mark.parametrize("definition", METRIC_REGISTRY.values(), ids=lambda d: d.key)
def test_definition_declares_required_fields(definition: MetricDefinition) -> None:
    assert definition.key and definition.display_name and definition.formula
    assert definition.unit in MetricUnit
    assert definition.direction is not None
    assert definition.supported_dimensions <= set(Dimension)
    assert definition.version >= 1
    assert get_metric_definition(definition.key) is definition


@pytest.mark.parametrize("definition", METRIC_REGISTRY.values(), ids=lambda d: d.key)
def test_aggregation_matches_unit_and_baseline_method(definition: MetricDefinition) -> None:
    match definition.aggregation:
        case Aggregation.RATE:
            assert definition.unit is MetricUnit.PERCENT
            assert definition.denominator is not None
            assert definition.baseline_method is BaselineMethod.POOLED_RATE
            assert definition.min_sample_size
        case Aggregation.MEAN:
            assert definition.unit is MetricUnit.MINUTES
            assert definition.denominator is not None
            assert definition.baseline_method is BaselineMethod.MEAN_OF_DAILY_VALUES
            assert definition.min_sample_size
        case Aggregation.COUNT | Aggregation.POINT_IN_TIME_COUNT:
            assert definition.unit is MetricUnit.COUNT
            assert definition.denominator is None
            assert definition.baseline_method is BaselineMethod.MEAN_OF_DAILY_VALUES


def test_unknown_metric_is_none() -> None:
    assert get_metric_definition("csat") is None
