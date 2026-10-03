"""Deterministic anomaly detector: pure functions, no database, no model calls.

Given the numbers of one metric snapshot and its rule, return either a
``Detection`` (severity, score, full threshold explanation) or a ``Skip`` with a
machine-readable reason. Severity comes only from the rule thresholds and the
rule's critical business condition; the z-score is supporting evidence and never
changes severity.
"""

import statistics
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.models.enums import AnomalySeverity
from app.services.anomalies.rules import (
    ZSCORE_MIN_HISTORY,
    AnomalyRule,
    Comparison,
    get_anomaly_rule,
)
from app.services.metrics.definitions import Direction

SCHEMA_VERSION: Literal[1] = 1
_QUANTUM = Decimal("0.000001")


class SkipReason(StrEnum):
    NOT_CONFIGURED = "not_configured"
    NO_DATA = "no_data"
    BASELINE_MISSING = "baseline_missing"
    BASELINE_ZERO = "baseline_zero"
    IMPROVEMENT = "improvement"
    BELOW_THRESHOLD = "below_threshold"
    INSUFFICIENT_SAMPLE = "insufficient_sample"


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class GuardResult(_Frozen):
    name: str
    required: float
    actual: float
    passed: bool


class CriticalResult(_Frozen):
    description: str
    min_current_value: float
    current_value: float
    met: bool


class ZScoreResult(_Frozen):
    """Supporting statistic over the daily baseline values. Unavailable is explicit."""

    available: bool
    value: float | None
    mean: float | None
    stdev: float | None
    sample_count: int
    unavailable_reason: Literal["insufficient_history", "zero_stdev"] | None


class ThresholdDetails(_Frozen):
    """Persisted as ``anomalies.threshold_json``: everything needed to explain a result."""

    schema_version: Literal[1] = SCHEMA_VERSION
    detector_key: str
    metric_key: str
    comparison: Comparison
    direction: Direction
    observed: float
    medium_threshold: float
    high_threshold: float
    triggered_tier: Literal["medium", "high"]
    guards: list[GuardResult]
    critical: CriticalResult | None
    z_score: ZScoreResult


@dataclass(frozen=True)
class DetectionInput:
    """The facts of one metric snapshot the detector needs."""

    metric_key: str
    direction: Direction
    value: Decimal
    baseline_value: Decimal | None
    change_pct: Decimal | None
    baseline_zero: bool
    current_sample_size: int
    baseline_sample_size: int
    daily_baseline_values: Sequence[float | None]


@dataclass(frozen=True)
class Detection:
    rule: AnomalyRule
    severity: AnomalySeverity
    score: Decimal
    threshold: ThresholdDetails


@dataclass(frozen=True)
class Skip:
    reason: SkipReason
    detail: str | None = None


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(_QUANTUM)


def compute_z_score(value: Decimal, daily_values: Sequence[float | None]) -> ZScoreResult:
    """Z-score of ``value`` against the daily baseline values; never divides by zero."""
    history = [v for v in daily_values if v is not None]
    count = len(history)
    if count < ZSCORE_MIN_HISTORY:
        return ZScoreResult(
            available=False,
            value=None,
            mean=None,
            stdev=None,
            sample_count=count,
            unavailable_reason="insufficient_history",
        )
    mean = statistics.fmean(history)
    stdev = statistics.stdev(history)
    if stdev == 0:
        return ZScoreResult(
            available=False,
            value=None,
            mean=mean,
            stdev=0.0,
            sample_count=count,
            unavailable_reason="zero_stdev",
        )
    return ZScoreResult(
        available=True,
        value=round((float(value) - mean) / stdev, 6),
        mean=mean,
        stdev=stdev,
        sample_count=count,
        unavailable_reason=None,
    )


def _measure(rule: AnomalyRule, data: DetectionInput) -> Decimal | Skip:
    """The signed change in the rule's unit, or a Skip when it cannot be measured."""
    if data.baseline_value is None:
        return Skip(SkipReason.BASELINE_MISSING, "The baseline window has no samples.")
    if rule.comparison is Comparison.PERCENTAGE_POINTS:
        return _quantize(data.value - data.baseline_value)
    if data.baseline_zero or data.change_pct is None:
        return Skip(
            SkipReason.BASELINE_ZERO,
            "A zero baseline has no defined percentage change.",
        )
    return data.change_pct


def _guard_results(rule: AnomalyRule, data: DetectionInput) -> list[GuardResult]:
    guards = rule.guards
    assert data.baseline_value is not None  # _measure already skipped a missing baseline
    delta = abs(data.value - data.baseline_value)
    checks: list[tuple[str, int | Decimal | None, int | Decimal]] = [
        ("min_current_sample", guards.min_current_sample, data.current_sample_size),
        ("min_baseline_sample", guards.min_baseline_sample, data.baseline_sample_size),
        ("min_baseline_value", guards.min_baseline_value, data.baseline_value),
        ("min_abs_delta", guards.min_abs_delta, delta),
    ]
    return [
        GuardResult(
            name=name, required=float(required), actual=float(actual), passed=actual >= required
        )
        for name, required, actual in checks
        if required is not None
    ]


def detect(data: DetectionInput) -> Detection | Skip:
    """Evaluate one snapshot against its rule. Deterministic for identical input."""
    rule = get_anomaly_rule(data.metric_key)
    if rule is None:
        return Skip(SkipReason.NOT_CONFIGURED, f"No anomaly rule for {data.metric_key!r}.")

    measured = _measure(rule, data)
    if isinstance(measured, Skip):
        return measured

    # Only the adverse direction counts, so an improvement is never an anomaly.
    adverse = measured if data.direction is Direction.HIGHER_IS_WORSE else -measured
    if adverse < 0:
        return Skip(SkipReason.IMPROVEMENT, "The metric moved in the favourable direction.")

    if adverse >= rule.high_threshold:
        tier: Literal["medium", "high"] = "high"
    elif adverse >= rule.medium_threshold:
        tier = "medium"
    else:
        return Skip(
            SkipReason.BELOW_THRESHOLD,
            f"Adverse change {adverse} is below the medium threshold {rule.medium_threshold}.",
        )

    guards = _guard_results(rule, data)
    failed = [g.name for g in guards if not g.passed]
    if failed:
        return Skip(SkipReason.INSUFFICIENT_SAMPLE, f"Failed sample guards: {', '.join(failed)}.")

    severity = AnomalySeverity.HIGH if tier == "high" else AnomalySeverity.MEDIUM
    critical: CriticalResult | None = None
    if rule.critical is not None:
        met = tier == "high" and data.value >= rule.critical.min_current_value
        critical = CriticalResult(
            description=rule.critical.description,
            min_current_value=float(rule.critical.min_current_value),
            current_value=float(data.value),
            met=met,
        )
        if met:
            severity = AnomalySeverity.CRITICAL

    threshold = ThresholdDetails(
        detector_key=rule.detector_key,
        metric_key=rule.metric_key,
        comparison=rule.comparison,
        direction=data.direction,
        observed=float(measured),
        medium_threshold=float(rule.medium_threshold),
        high_threshold=float(rule.high_threshold),
        triggered_tier=tier,
        guards=guards,
        critical=critical,
        z_score=compute_z_score(data.value, data.daily_baseline_values),
    )
    return Detection(rule=rule, severity=severity, score=measured, threshold=threshold)


_UNITS: dict[Comparison, str] = {
    Comparison.RELATIVE_PCT: "%",
    Comparison.PERCENTAGE_POINTS: " pp",
}


def explain(severity: AnomalySeverity, threshold: ThresholdDetails, display_name: str) -> str:
    """Deterministic, template-built explanation of why an anomaly fired."""
    unit = _UNITS[threshold.comparison]
    limit = (
        threshold.high_threshold
        if threshold.triggered_tier == "high"
        else threshold.medium_threshold
    )
    text = (
        f"{display_name} changed {threshold.observed:+.2f}{unit} against its 7-day baseline, "
        f"meeting the {threshold.triggered_tier} threshold of {limit:g}{unit} "
        f"(rule {threshold.detector_key})."
    )
    if threshold.critical is not None and threshold.critical.met:
        text += f" Escalated to critical: {threshold.critical.description}."
    z = threshold.z_score
    if z.available and z.value is not None:
        text += f" Z-score vs daily baseline: {z.value:+.2f}."
    return f"{text} Severity: {severity}."
