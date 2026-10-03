"""Deterministic metric math: analysis windows, formulas, baselines, change.

Pure functions only (no database access). Values use ``Decimal`` and are
quantised to the ``metric_snapshots`` storage precision (6 decimal places) so a
freshly computed result and its persisted snapshot are identical.

Window contract: the current window is ``[window_end - 24h, window_end)``; the
baseline is the seven contiguous 24h windows immediately before it. The current
window is never part of its own baseline.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_EVEN, Decimal

from app.services.metrics.definitions import (
    AggregateField,
    Aggregation,
    BaselineMethod,
    Dimension,
    MetricDefinition,
)

WINDOW_LENGTH = timedelta(hours=24)
BASELINE_WINDOW_COUNT = 7
STORAGE_QUANTUM = Decimal("0.000001")
_HUNDRED = Decimal(100)

Aggregates = Mapping[AggregateField, int]


@dataclass(frozen=True)
class TimeRange:
    start: datetime
    end: datetime


@dataclass(frozen=True)
class AnalysisWindow:
    current: TimeRange
    baseline: TimeRange
    # Oldest first; together they cover ``baseline`` exactly.
    baseline_days: tuple[TimeRange, ...]

    @property
    def buckets(self) -> tuple[TimeRange, ...]:
        """Baseline days followed by the current window (bucket 7)."""
        return (*self.baseline_days, self.current)


def to_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("Datetimes must be timezone-aware.")
    return value.astimezone(UTC)


def utc_midnight(value: datetime) -> datetime:
    return to_utc(value).replace(hour=0, minute=0, second=0, microsecond=0)


def analysis_window(window_end: datetime) -> AnalysisWindow:
    end = to_utc(window_end)
    current = TimeRange(end - WINDOW_LENGTH, end)
    baseline_start = current.start - WINDOW_LENGTH * BASELINE_WINDOW_COUNT
    days = tuple(
        TimeRange(baseline_start + WINDOW_LENGTH * i, baseline_start + WINDOW_LENGTH * (i + 1))
        for i in range(BASELINE_WINDOW_COUNT)
    )
    return AnalysisWindow(
        current=current, baseline=TimeRange(baseline_start, current.start), baseline_days=days
    )


def quantize(value: Decimal) -> Decimal:
    return value.quantize(STORAGE_QUANTUM, rounding=ROUND_HALF_EVEN)


@dataclass(frozen=True)
class WindowValue:
    """A metric evaluated over one window. ``value`` is None when undefined (0 samples)."""

    value: Decimal | None
    numerator: int
    denominator: int | None
    sample_size: int


def window_value(definition: MetricDefinition, aggregates: Aggregates) -> WindowValue:
    numerator = aggregates[definition.numerator]
    if definition.denominator is None:
        return WindowValue(Decimal(numerator), numerator, None, numerator)

    denominator = aggregates[definition.denominator]
    if denominator == 0:
        return WindowValue(None, numerator, denominator, 0)
    ratio = Decimal(numerator) / Decimal(denominator)
    if definition.aggregation is Aggregation.RATE:
        ratio *= _HUNDRED
    return WindowValue(quantize(ratio), numerator, denominator, denominator)


def baseline_value(definition: MetricDefinition, days: Sequence[WindowValue]) -> Decimal | None:
    """Baseline per the definition's method; None when the baseline is empty."""
    if definition.baseline_method is BaselineMethod.POOLED_RATE:
        numerator = sum(day.numerator for day in days)
        denominator = sum(day.denominator or 0 for day in days)
        if denominator == 0:
            return None
        return quantize(Decimal(numerator) / Decimal(denominator) * _HUNDRED)

    values = [day.value for day in days if day.value is not None]
    if not values:
        return None
    return quantize(sum(values, Decimal(0)) / Decimal(len(values)))


@dataclass(frozen=True)
class Change:
    change_pct: Decimal | None
    baseline_zero: bool


def change_pct(current: Decimal, baseline: Decimal | None) -> Change:
    """``(current - baseline) / |baseline| * 100`` with explicit zero/empty handling.

    Never divides by zero, so the result is always finite or None.
    """
    if baseline is None:
        return Change(None, baseline_zero=False)
    if baseline == 0:
        return Change(Decimal(0) if current == 0 else None, baseline_zero=True)
    return Change(quantize((current - baseline) / abs(baseline) * _HUNDRED), baseline_zero=False)


@dataclass(frozen=True)
class MetricResult:
    definition: MetricDefinition
    window: AnalysisWindow
    filters: Mapping[Dimension, str]
    current: WindowValue
    baseline_days: tuple[WindowValue, ...]
    baseline_value: Decimal | None
    change_pct: Decimal | None
    baseline_zero: bool

    @property
    def baseline_empty(self) -> bool:
        return self.baseline_value is None

    @property
    def is_defined(self) -> bool:
        """False when the current value cannot be computed (no samples)."""
        return self.current.value is not None

    @property
    def sample_sufficient(self) -> bool:
        minimum = self.definition.min_sample_size
        return minimum is None or self.current.sample_size >= minimum

    @property
    def baseline_sample_size(self) -> int:
        return sum(day.sample_size for day in self.baseline_days)


def compute_metric(
    definition: MetricDefinition,
    window: AnalysisWindow,
    filters: Mapping[Dimension, str],
    buckets: Sequence[Aggregates],
) -> MetricResult:
    """Evaluate one metric from eight bucket aggregates (7 baseline days + current)."""
    if len(buckets) != BASELINE_WINDOW_COUNT + 1:
        raise ValueError(f"Expected {BASELINE_WINDOW_COUNT + 1} buckets, got {len(buckets)}.")

    days = tuple(window_value(definition, bucket) for bucket in buckets[:BASELINE_WINDOW_COUNT])
    current = window_value(definition, buckets[BASELINE_WINDOW_COUNT])
    baseline = baseline_value(definition, days)
    change = (
        change_pct(current.value, baseline)
        if current.value is not None
        else Change(None, baseline_zero=baseline == 0)
    )
    return MetricResult(
        definition=definition,
        window=window,
        filters=filters,
        current=current,
        baseline_days=days,
        baseline_value=baseline,
        change_pct=change.change_pct,
        baseline_zero=change.baseline_zero,
    )
