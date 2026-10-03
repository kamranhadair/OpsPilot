"""Pure formula tests: windows, per-window values, baselines, change, zero handling."""

import math
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.services.metrics.definitions import METRIC_REGISTRY, AggregateField
from app.services.metrics.engine import (
    WindowValue,
    analysis_window,
    baseline_value,
    change_pct,
    compute_metric,
    window_value,
)

END = datetime(2026, 3, 10, tzinfo=UTC)


def aggregates(**values: int) -> dict[AggregateField, int]:
    result = dict.fromkeys(AggregateField, 0)
    result.update({AggregateField(k): v for k, v in values.items()})
    return result


# --- windows -----------------------------------------------------------------------


def test_current_window_is_24h_ending_at_window_end() -> None:
    window = analysis_window(END)
    assert window.current.start == END - timedelta(hours=24)
    assert window.current.end == END


def test_baseline_is_seven_contiguous_days_immediately_before_current() -> None:
    window = analysis_window(END)
    assert window.baseline.start == END - timedelta(days=8)
    assert window.baseline.end == window.current.start
    assert len(window.baseline_days) == 7
    assert window.baseline_days[0].start == window.baseline.start
    assert window.baseline_days[-1].end == window.current.start
    for earlier, later in zip(window.baseline_days, window.baseline_days[1:], strict=False):
        assert earlier.end == later.start


def test_baseline_never_overlaps_current_window() -> None:
    window = analysis_window(END)
    assert all(day.end <= window.current.start for day in window.baseline_days)


def test_window_end_is_normalised_to_utc_and_naive_is_rejected() -> None:
    plus_two = datetime(2026, 3, 10, 2, tzinfo=timezone(timedelta(hours=2)))
    assert analysis_window(plus_two).current.end == END
    with pytest.raises(ValueError):
        analysis_window(datetime(2026, 3, 10))


# --- per-window formulas -----------------------------------------------------------


def test_count_metric_value_and_sample() -> None:
    value = window_value(METRIC_REGISTRY["ticket_volume"], aggregates(tickets=42))
    assert value == WindowValue(Decimal(42), 42, None, 42)


def test_p1_and_backlog_use_their_own_numerators() -> None:
    agg = aggregates(tickets=40, p1_tickets=3, open_backlog_tickets=17)
    assert window_value(METRIC_REGISTRY["p1_ticket_volume"], agg).value == 3
    assert window_value(METRIC_REGISTRY["open_backlog"], agg).value == 17


def test_mean_metric_divides_sum_by_count() -> None:
    agg = aggregates(first_response_minutes_sum=100, first_response_minutes_count=3)
    value = window_value(METRIC_REGISTRY["first_response_minutes"], agg)
    assert value.value == Decimal("33.333333")
    assert value.sample_size == 3


def test_rate_metric_is_numerator_over_denominator_in_percent() -> None:
    agg = aggregates(tickets=40, sla_breached_tickets=6, escalated_tickets=2)
    breach = window_value(METRIC_REGISTRY["sla_breach_rate"], agg)
    assert breach.value == Decimal("15.000000")
    assert (breach.numerator, breach.denominator, breach.sample_size) == (6, 40, 40)
    assert window_value(METRIC_REGISTRY["escalation_rate"], agg).value == Decimal(5)


@pytest.mark.parametrize("key", ["first_response_minutes", "sla_breach_rate"])
def test_zero_denominator_is_undefined_not_zero(key: str) -> None:
    value = window_value(METRIC_REGISTRY[key], aggregates())
    assert value.value is None
    assert value.sample_size == 0


# --- baselines ---------------------------------------------------------------------


def test_count_baseline_is_mean_of_daily_values_including_zero_days() -> None:
    days = [WindowValue(Decimal(v), v, None, v) for v in (10, 0, 20, 30, 0, 10, 0)]
    assert baseline_value(METRIC_REGISTRY["ticket_volume"], days) == Decimal(10)


def test_mean_baseline_skips_days_without_samples() -> None:
    days = [WindowValue(Decimal(10), 10, 1, 1), WindowValue(None, 0, 0, 0)] + [
        WindowValue(Decimal(20), 20, 1, 1)
    ]
    assert baseline_value(METRIC_REGISTRY["first_response_minutes"], days) == Decimal(15)


def test_rate_baseline_is_pooled_not_mean_of_daily_rates() -> None:
    # Day A: 1/2 = 50%; day B: 9/90 = 10%. Pooled 10/92; mean of daily rates 30%.
    days = [WindowValue(Decimal(50), 1, 2, 2), WindowValue(Decimal(10), 9, 90, 90)]
    pooled = baseline_value(METRIC_REGISTRY["sla_breach_rate"], days)
    assert pooled == Decimal("10.869565")  # 10 / 92
    assert pooled != Decimal(30)  # mean of daily rates


@pytest.mark.parametrize("key", ["ticket_volume", "first_response_minutes", "sla_breach_rate"])
def test_empty_baseline(key: str) -> None:
    definition = METRIC_REGISTRY[key]
    days = [window_value(definition, aggregates()) for _ in range(7)]
    expected = Decimal(0) if definition.denominator is None else None
    assert baseline_value(definition, days) == expected


# --- change ------------------------------------------------------------------------


def test_change_pct_uses_absolute_baseline() -> None:
    assert change_pct(Decimal(150), Decimal(100)).change_pct == Decimal(50)
    assert change_pct(Decimal(50), Decimal(100)).change_pct == Decimal(-50)
    assert change_pct(Decimal(-5), Decimal(-10)).change_pct == Decimal(50)


def test_zero_baseline_and_zero_current_is_zero_change() -> None:
    change = change_pct(Decimal(0), Decimal(0))
    assert change.change_pct == 0
    assert change.baseline_zero


def test_zero_baseline_and_nonzero_current_is_null_with_flag() -> None:
    change = change_pct(Decimal(7), Decimal(0))
    assert change.change_pct is None
    assert change.baseline_zero


def test_missing_baseline_is_null_without_zero_flag() -> None:
    change = change_pct(Decimal(7), None)
    assert change.change_pct is None
    assert not change.baseline_zero


def test_change_is_always_finite_or_null() -> None:
    values = [Decimal(v) for v in ("0", "0.000001", "1", "-3", "1000000", "33.333333")]
    for current in values:
        for baseline in [*values, None]:
            result = change_pct(current, baseline).change_pct
            assert result is None or math.isfinite(result)


# --- compute_metric ----------------------------------------------------------------


def test_compute_metric_excludes_current_bucket_from_baseline() -> None:
    window = analysis_window(END)
    buckets = [aggregates(tickets=10) for _ in range(7)] + [aggregates(tickets=1000)]
    result = compute_metric(METRIC_REGISTRY["ticket_volume"], window, {}, buckets)
    assert result.baseline_value == Decimal(10)
    assert result.current.value == Decimal(1000)
    assert result.change_pct == Decimal(9900)


def test_compute_metric_flags_insufficient_samples() -> None:
    window = analysis_window(END)
    buckets = [aggregates(tickets=30, sla_breached_tickets=3)] * 7 + [
        aggregates(tickets=5, sla_breached_tickets=1)
    ]
    result = compute_metric(METRIC_REGISTRY["sla_breach_rate"], window, {}, buckets)
    assert result.is_defined
    assert not result.sample_sufficient
    assert result.baseline_sample_size == 210


def test_compute_metric_with_undefined_current_value() -> None:
    window = analysis_window(END)
    buckets = [aggregates(tickets=30, sla_breached_tickets=3)] * 7 + [aggregates()]
    result = compute_metric(METRIC_REGISTRY["sla_breach_rate"], window, {}, buckets)
    assert not result.is_defined
    assert result.change_pct is None


def test_compute_metric_requires_eight_buckets() -> None:
    with pytest.raises(ValueError):
        compute_metric(METRIC_REGISTRY["ticket_volume"], analysis_window(END), {}, [])
