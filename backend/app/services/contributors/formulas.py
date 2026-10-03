"""Contributor formulas and ranking: pure functions, no database access.

Contribution is attribution of *observed* change across segments. It says how
the positive change is distributed, never why it happened.

Count metrics (volume, backlog, P1 volume):
    ``delta = current_segment_count - normalized_baseline_segment_count``
    where the baseline is the segment's mean daily value over the 7 baseline days.

Rate metrics (SLA breach, escalation, negative sentiment):
    ``expected_current_events = current_segment_denominator * baseline_segment_rate``
    ``excess_events = actual_current_events - expected_current_events``
    where ``baseline_segment_rate = sum(baseline numerators) / sum(baseline denominators)``.

Either way only positive deltas form the denominator of the share:
    ``contribution_pct = positive_segment_delta / sum(all_positive_deltas) * 100``

Deltas are quantised to storage precision first and the share is computed from
those quantised values, so a persisted row can be recomputed exactly.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum

from app.services.metrics.definitions import Aggregation, Dimension, MetricDefinition
from app.services.metrics.engine import quantize

ANALYSIS_VERSION = "contrib.v1"
TOP_N = 5
# Minimum current sample for a segment to be ranked. A tiny segment can show a
# large share from a handful of records; it is suppressed (and reported), not ranked.
MIN_COUNT_SEGMENT_CURRENT = 5
MIN_RATE_SEGMENT_DENOMINATOR = 10

_HUNDRED = Decimal(100)

SUPPORTED_AGGREGATIONS = frozenset(
    {Aggregation.COUNT, Aggregation.POINT_IN_TIME_COUNT, Aggregation.RATE}
)


@dataclass(frozen=True)
class ContributorFamily:
    """A group of segments that partition the anomaly's slice (one or more dimensions)."""

    key: str
    dimensions: tuple[Dimension, ...]


FAMILIES: tuple[ContributorFamily, ...] = (
    ContributorFamily("region", (Dimension.REGION,)),
    ContributorFamily("customer_tier", (Dimension.CUSTOMER_TIER,)),
    ContributorFamily("category", (Dimension.CATEGORY,)),
    ContributorFamily("product", (Dimension.PRODUCT,)),
    ContributorFamily("support_team", (Dimension.SUPPORT_TEAM,)),
    ContributorFamily("region+customer_tier", (Dimension.REGION, Dimension.CUSTOMER_TIER)),
)


class Method(StrEnum):
    COUNT_DELTA = "count_delta"
    RATE_EXCESS = "rate_excess"


class Flag(StrEnum):
    NEW_SEGMENT = "new_segment"  # no baseline records for this segment
    BASELINE_FROM_PARENT = "baseline_rate_from_parent_slice"


class ExcludeReason(StrEnum):
    ZERO_DENOMINATOR = "zero_denominator"  # rate segment with no current records
    NO_BASELINE_RATE = "no_baseline_rate"  # neither segment nor parent has a baseline rate


class FamilyStatus(StrEnum):
    RANKED = "ranked"
    NO_POSITIVE_CONTRIBUTORS = "no_positive_contributors"
    SKIPPED_FIXED_DIMENSION = "skipped_fixed_dimension"


def supports_segmentation(definition: MetricDefinition) -> bool:
    return definition.aggregation in SUPPORTED_AGGREGATIONS


def method_for(definition: MetricDefinition) -> Method:
    return Method.RATE_EXCESS if definition.is_rate else Method.COUNT_DELTA


def min_sample_for(method: Method) -> int:
    if method is Method.RATE_EXCESS:
        return MIN_RATE_SEGMENT_DENOMINATOR
    return MIN_COUNT_SEGMENT_CURRENT


def formula_for(method: Method) -> str:
    if method is Method.RATE_EXCESS:
        return (
            "excess_events = actual_current_events - current_denominator * baseline_rate; "
            "baseline_rate = sum(baseline_numerators) / sum(baseline_denominators); "
            "contribution_pct = positive_excess_events / sum(positive_excess_events) * 100"
        )
    return (
        "delta = current_count - mean_daily_baseline_count; "
        "contribution_pct = positive_delta / sum(positive_deltas) * 100"
    )


@dataclass(frozen=True)
class SegmentFacts:
    """Integer facts for one segment, taken from the metric engine's per-window values."""

    segment: Mapping[Dimension, str]
    # Count metrics: the current count. Rate metrics: the current numerator (events).
    current_events: int
    # Count metrics: None. Rate metrics: the current denominator (records).
    current_denominator: int | None
    # Count metrics: mean daily baseline count (None when the baseline is empty).
    baseline_value: Decimal | None
    # Rate metrics: summed baseline numerator / denominator over the 7 baseline days.
    baseline_numerator: int
    baseline_denominator: int


@dataclass(frozen=True)
class SegmentDelta:
    segment: Mapping[Dimension, str]
    method: Method
    current_events: int
    current_denominator: int | None
    baseline_numerator: int
    baseline_denominator: int
    # Count: the normalised baseline count. Rate: the expected current events.
    baseline_value: Decimal
    # Rate only: the baseline rate used (as a fraction, not percent) and where it came from.
    baseline_rate: Decimal | None
    delta: Decimal
    sample: int
    flags: tuple[Flag, ...] = ()

    @property
    def current_value(self) -> Decimal:
        return Decimal(self.current_events)

    @property
    def label(self) -> str:
        return segment_value(self.segment)


@dataclass(frozen=True)
class Excluded:
    segment: Mapping[Dimension, str]
    reason: ExcludeReason


def segment_value(segment: Mapping[Dimension, str]) -> str:
    """Stable storage key in family dimension order, e.g. ``emea|enterprise``."""
    return "|".join(segment.values())


def parent_baseline_rate(numerator: int, denominator: int) -> Decimal | None:
    """The whole slice's pooled baseline rate as a fraction, or None without a baseline."""
    return None if denominator == 0 else Decimal(numerator) / Decimal(denominator)


def expected_events(current_denominator: int, baseline_rate: Decimal) -> Decimal:
    return quantize(Decimal(current_denominator) * baseline_rate)


def count_delta(facts: SegmentFacts) -> SegmentDelta | None:
    """Delta of a count segment, or None when the segment is empty in both windows."""
    baseline = facts.baseline_value if facts.baseline_value is not None else Decimal(0)
    if facts.current_events == 0 and baseline == 0:
        return None
    flags = (Flag.NEW_SEGMENT,) if baseline == 0 else ()
    return SegmentDelta(
        segment=facts.segment,
        method=Method.COUNT_DELTA,
        current_events=facts.current_events,
        current_denominator=None,
        baseline_numerator=0,
        baseline_denominator=0,
        baseline_value=baseline,
        baseline_rate=None,
        delta=quantize(Decimal(facts.current_events) - baseline),
        sample=facts.current_events,
        flags=flags,
    )


def rate_excess(facts: SegmentFacts, parent_rate: Decimal | None) -> SegmentDelta | Excluded | None:
    """Excess events of a rate segment.

    Returns None when the segment is empty in both windows, ``Excluded`` when it
    cannot contribute, otherwise the delta. A segment with no baseline records
    uses the parent slice's baseline rate and says so in its flags.
    """
    current_den = facts.current_denominator or 0
    if current_den == 0:
        if facts.baseline_denominator == 0:
            return None
        return Excluded(facts.segment, ExcludeReason.ZERO_DENOMINATOR)

    flags: tuple[Flag, ...] = ()
    rate = parent_baseline_rate(facts.baseline_numerator, facts.baseline_denominator)
    if rate is None:
        rate = parent_rate
        if rate is None:
            return Excluded(facts.segment, ExcludeReason.NO_BASELINE_RATE)
        flags = (Flag.NEW_SEGMENT, Flag.BASELINE_FROM_PARENT)

    expected = expected_events(current_den, rate)
    return SegmentDelta(
        segment=facts.segment,
        method=Method.RATE_EXCESS,
        current_events=facts.current_events,
        current_denominator=current_den,
        baseline_numerator=facts.baseline_numerator,
        baseline_denominator=facts.baseline_denominator,
        baseline_value=expected,
        baseline_rate=rate,
        delta=quantize(Decimal(facts.current_events) - expected),
        sample=current_den,
        flags=flags,
    )


def contribution_pct(delta: Decimal, positive_total: Decimal) -> Decimal | None:
    """Share of the positive total; None (never a division) when there is no positive total."""
    if positive_total <= 0:
        return None
    return quantize(delta / positive_total * _HUNDRED)


@dataclass(frozen=True)
class RankedContributor:
    rank: int
    delta: SegmentDelta
    contribution_pct: Decimal


@dataclass(frozen=True)
class FamilyRanking:
    status: FamilyStatus
    ranked: tuple[RankedContributor, ...] = ()
    # Positive segments held back for being below the minimum sample.
    suppressed: tuple[SegmentDelta, ...] = ()
    excluded: tuple[Excluded, ...] = ()
    positive_total: Decimal = field(default_factory=lambda: Decimal(0))
    min_sample: int = 0
    # Share of segments not in the ranked list: truncated by top-N plus suppressed.
    other_contribution_pct: Decimal = field(default_factory=lambda: Decimal(0))
    suppressed_contribution_pct: Decimal = field(default_factory=lambda: Decimal(0))


def rank_segments(
    deltas: Sequence[SegmentDelta],
    *,
    min_sample: int,
    excluded: Sequence[Excluded] = (),
    top_n: int = TOP_N,
) -> FamilyRanking:
    """Rank positive contributors by share of the family's total positive change.

    Suppressed segments still count in the denominator (they are real change)
    but are not ranked. Ties break on the segment key so output is deterministic.
    """
    positives = [d for d in deltas if d.delta > 0]
    positive_total = sum((d.delta for d in positives), Decimal(0))
    if positive_total <= 0:
        return FamilyRanking(
            status=FamilyStatus.NO_POSITIVE_CONTRIBUTORS,
            excluded=tuple(excluded),
            min_sample=min_sample,
        )

    eligible = [d for d in positives if d.sample >= min_sample]
    suppressed = [d for d in positives if d.sample < min_sample]
    ordered = sorted(eligible, key=lambda d: (-d.delta, d.label))[:top_n]

    ranked: list[RankedContributor] = []
    for rank, item in enumerate(ordered, start=1):
        share = contribution_pct(item.delta, positive_total)
        assert share is not None  # positive_total > 0 here
        ranked.append(RankedContributor(rank, item, share))

    suppressed_pct = quantize(
        sum(
            (contribution_pct(d.delta, positive_total) or Decimal(0) for d in suppressed),
            Decimal(0),
        )
    )
    ranked_pct = sum((r.contribution_pct for r in ranked), Decimal(0))
    return FamilyRanking(
        status=FamilyStatus.RANKED if ranked else FamilyStatus.NO_POSITIVE_CONTRIBUTORS,
        ranked=tuple(ranked),
        suppressed=tuple(sorted(suppressed, key=lambda d: (-d.delta, d.label))),
        excluded=tuple(excluded),
        positive_total=positive_total,
        min_sample=min_sample,
        other_contribution_pct=quantize(max(_HUNDRED - ranked_pct, Decimal(0))),
        suppressed_contribution_pct=suppressed_pct,
    )


_UPPER_LABELS = frozenset({"emea", "apac"})


def display_label(segment: Mapping[Dimension, str]) -> str:
    """Human-readable segment name, e.g. ``EMEA / Enterprise``."""
    parts = []
    for value in segment.values():
        parts.append(value.upper() if value in _UPPER_LABELS else value.replace("_", " ").title())
    return " / ".join(parts)
