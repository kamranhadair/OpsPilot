"""Central anomaly rule registry: every threshold and guard lives here.

Detection is deterministic: a rule compares a metric snapshot's current value to
its seven-day baseline and maps the *adverse* change onto a severity tier. The
rule version is part of ``detector_key`` so changing a threshold means bumping
the version, which keeps older anomalies reproducible and re-detection
idempotent per (snapshot, detector).

``LOW`` severity exists in the domain enum but no V1 rule emits it.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from types import MappingProxyType

from app.models.enums import TicketCategory
from app.services.metrics.definitions import METRIC_REGISTRY, Dimension

# Minimum number of daily baseline values required for a z-score.
ZSCORE_MIN_HISTORY = 7


class Comparison(StrEnum):
    """How the change is measured against the thresholds."""

    RELATIVE_PCT = "relative_pct"  # (current - baseline) / |baseline| * 100
    PERCENTAGE_POINTS = "percentage_points"  # current - baseline, rate metrics only


@dataclass(frozen=True)
class SampleGuards:
    """Small-sample protections. ``None`` means the guard is not applied.

    A tiny baseline can turn a handful of tickets into a huge percentage, so the
    rules require enough volume before a change may count as an anomaly.
    """

    min_current_sample: int | None = None
    min_baseline_sample: int | None = None
    min_baseline_value: Decimal | None = None
    min_abs_delta: Decimal | None = None


@dataclass(frozen=True)
class CriticalCondition:
    """Business condition that upgrades a ``high`` anomaly to ``critical``.

    Never reachable from a percentage alone: the current value itself must reach
    an absolute level that matters operationally.
    """

    description: str
    min_current_value: Decimal


@dataclass(frozen=True)
class AnomalyRule:
    metric_key: str
    detector_key: str
    comparison: Comparison
    medium_threshold: Decimal
    high_threshold: Decimal
    guards: SampleGuards
    critical: CriticalCondition | None = None


def _pct_rule(
    metric_key: str,
    *,
    guards: SampleGuards,
    critical: CriticalCondition | None = None,
) -> AnomalyRule:
    return AnomalyRule(
        metric_key=metric_key,
        detector_key="pct_change.v1",
        comparison=Comparison.RELATIVE_PCT,
        medium_threshold=Decimal(30),
        high_threshold=Decimal(50),
        guards=guards,
        critical=critical,
    )


def _pp_rule(
    metric_key: str,
    *,
    medium: int,
    high: int,
    critical: CriticalCondition | None = None,
) -> AnomalyRule:
    return AnomalyRule(
        metric_key=metric_key,
        detector_key="pp_change.v1",
        comparison=Comparison.PERCENTAGE_POINTS,
        medium_threshold=Decimal(medium),
        high_threshold=Decimal(high),
        # >= 30 tickets today and >= 70 across the 7 baseline days keeps one or two
        # tickets in a small queue from moving a rate by whole percentage points.
        guards=SampleGuards(min_current_sample=30, min_baseline_sample=70),
        critical=critical,
    )


_COUNT_GUARDS = SampleGuards(min_baseline_value=Decimal(10), min_abs_delta=Decimal(10))

_RULES: tuple[AnomalyRule, ...] = (
    _pct_rule("ticket_volume", guards=_COUNT_GUARDS),
    _pct_rule("open_backlog", guards=_COUNT_GUARDS),
    _pct_rule(
        "p1_ticket_volume",
        # P1 baselines are tiny, so absolute-count safeguards replace the baseline floor.
        guards=SampleGuards(min_current_sample=5, min_abs_delta=Decimal(3)),
        critical=CriticalCondition(
            description="at least 12 P1 tickets created in the window",
            min_current_value=Decimal(12),
        ),
    ),
    _pp_rule(
        "sla_breach_rate",
        medium=3,
        high=5,
        critical=CriticalCondition(
            description="SLA breach rate of at least 25% of tickets in the window",
            min_current_value=Decimal(25),
        ),
    ),
    _pp_rule("escalation_rate", medium=2, high=4),
    _pp_rule("negative_sentiment_rate", medium=5, high=10),
)

# first_response_minutes and resolution_minutes are deliberately not configured in V1.
ANOMALY_RULES: Mapping[str, AnomalyRule] = MappingProxyType(
    {rule.metric_key: rule for rule in _RULES}
)


def get_anomaly_rule(metric_key: str) -> AnomalyRule | None:
    return ANOMALY_RULES.get(metric_key)


# Slices the detector evaluates: overall, then one per support queue (category).
# Region/tier/team breakdowns are contributor analysis (Spec 06), not detection.
DETECTION_SLICES: tuple[Mapping[Dimension, str], ...] = (
    MappingProxyType({}),
    *(MappingProxyType({Dimension.CATEGORY: str(category)}) for category in TicketCategory),
)

# Every rule must target a registered metric; fail at import rather than at runtime.
_unknown = set(ANOMALY_RULES) - set(METRIC_REGISTRY)
if _unknown:  # pragma: no cover - guards against registry drift
    raise RuntimeError(f"Anomaly rules reference unknown metrics: {sorted(_unknown)}")
