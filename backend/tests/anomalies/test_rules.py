"""The rule registry: one central, documented set of thresholds."""

from decimal import Decimal

import pytest

from app.models.enums import TicketCategory
from app.services.anomalies.rules import (
    ANOMALY_RULES,
    DETECTION_SLICES,
    Comparison,
    get_anomaly_rule,
)
from app.services.metrics.definitions import METRIC_REGISTRY, Dimension

PINNED = {
    # metric: (comparison, medium, high)
    "ticket_volume": (Comparison.RELATIVE_PCT, 30, 50),
    "open_backlog": (Comparison.RELATIVE_PCT, 30, 50),
    "p1_ticket_volume": (Comparison.RELATIVE_PCT, 30, 50),
    "sla_breach_rate": (Comparison.PERCENTAGE_POINTS, 3, 5),
    "escalation_rate": (Comparison.PERCENTAGE_POINTS, 2, 4),
    "negative_sentiment_rate": (Comparison.PERCENTAGE_POINTS, 5, 10),
}


def test_registry_holds_exactly_the_pinned_rules() -> None:
    assert set(ANOMALY_RULES) == set(PINNED)


@pytest.mark.parametrize(("key", "expected"), PINNED.items())
def test_thresholds_are_pinned(key: str, expected: tuple[Comparison, int, int]) -> None:
    rule = ANOMALY_RULES[key]
    comparison, medium, high = expected
    assert rule.comparison is comparison
    assert rule.medium_threshold == Decimal(medium)
    assert rule.high_threshold == Decimal(high)


@pytest.mark.parametrize("key", PINNED)
def test_rule_is_consistent_with_its_metric(key: str) -> None:
    rule = ANOMALY_RULES[key]
    definition = METRIC_REGISTRY[key]
    assert rule.medium_threshold < rule.high_threshold
    assert rule.detector_key.endswith(".v1")
    if rule.comparison is Comparison.PERCENTAGE_POINTS:
        assert definition.is_rate  # percentage points only make sense for rates


def test_rate_rules_guard_both_samples() -> None:
    for key in ("sla_breach_rate", "escalation_rate", "negative_sentiment_rate"):
        guards = ANOMALY_RULES[key].guards
        assert guards.min_current_sample == 30
        assert guards.min_baseline_sample == 70


def test_critical_requires_a_business_condition_on_the_value() -> None:
    with_critical = {k for k, r in ANOMALY_RULES.items() if r.critical is not None}
    assert with_critical == {"p1_ticket_volume", "sla_breach_rate"}
    assert ANOMALY_RULES["sla_breach_rate"].critical is not None
    assert ANOMALY_RULES["sla_breach_rate"].critical.min_current_value == Decimal(25)


@pytest.mark.parametrize("key", ["first_response_minutes", "resolution_minutes"])
def test_latency_metrics_are_not_configured(key: str) -> None:
    assert key in METRIC_REGISTRY
    assert get_anomaly_rule(key) is None


def test_slices_are_overall_plus_each_category() -> None:
    assert dict(DETECTION_SLICES[0]) == {}
    assert [dict(s) for s in DETECTION_SLICES[1:]] == [
        {Dimension.CATEGORY: str(category)} for category in TicketCategory
    ]
