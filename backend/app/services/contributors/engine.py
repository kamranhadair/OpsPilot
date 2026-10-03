"""Orchestrates contributor analysis for one anomaly over the existing metrics layer.

Segment facts come from the same per-window aggregates and metric computation the
anomaly's snapshot used (``fetch_bucket_aggregates`` / ``compute_metric``), so
cohort definitions, windows and baselines are identical by construction.
"""

import itertools
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.models import MetricSnapshot
from app.models.enums import CustomerTier, Product, Region, TicketCategory
from app.services.contributors.errors import SegmentationNotSupportedError, WindowMismatchError
from app.services.contributors.formulas import (
    FAMILIES,
    ContributorFamily,
    Excluded,
    FamilyRanking,
    FamilyStatus,
    Method,
    SegmentDelta,
    SegmentFacts,
    count_delta,
    method_for,
    min_sample_for,
    parent_baseline_rate,
    rank_segments,
    rate_excess,
    supports_segmentation,
)
from app.services.metrics.definitions import METRIC_REGISTRY, Dimension, MetricDefinition
from app.services.metrics.engine import (
    AnalysisWindow,
    MetricResult,
    analysis_window,
    compute_metric,
)
from app.services.metrics.queries import fetch_bucket_aggregates

_ENUM_VALUES: Mapping[Dimension, tuple[str, ...]] = {
    Dimension.REGION: tuple(str(v) for v in Region),
    Dimension.CUSTOMER_TIER: tuple(str(v) for v in CustomerTier),
    Dimension.CATEGORY: tuple(str(v) for v in TicketCategory),
    Dimension.PRODUCT: tuple(str(v) for v in Product),
}


@dataclass(frozen=True)
class FamilyResult:
    family: ContributorFamily
    ranking: FamilyRanking


@dataclass(frozen=True)
class AnalysisResult:
    definition: MetricDefinition
    method: Method
    window: AnalysisWindow
    base_filters: dict[Dimension, str]
    families: list[FamilyResult] = field(default_factory=list)


def base_filters_of(snapshot: MetricSnapshot) -> dict[Dimension, str]:
    return {Dimension(key): value for key, value in snapshot.dimensions_json.items()}


def verified_window(snapshot: MetricSnapshot) -> AnalysisWindow:
    """The anomaly metric's windows, rebuilt and checked against the snapshot."""
    window = analysis_window(snapshot.window_end)
    if (
        window.current.start != snapshot.window_start
        or snapshot.baseline_start != window.baseline.start
        or snapshot.baseline_end != window.baseline.end
    ):
        raise WindowMismatchError(
            f"Snapshot {snapshot.evidence_id} does not use the standard 24h/7-day windows."
        )
    return window


def _facts(result: MetricResult, segment: Mapping[Dimension, str]) -> SegmentFacts:
    if result.definition.is_rate:
        return SegmentFacts(
            segment=segment,
            current_events=result.current.numerator,
            current_denominator=result.current.denominator,
            baseline_value=None,
            baseline_numerator=sum(day.numerator for day in result.baseline_days),
            baseline_denominator=sum(day.denominator or 0 for day in result.baseline_days),
        )
    return SegmentFacts(
        segment=segment,
        current_events=result.current.numerator,
        current_denominator=None,
        baseline_value=result.baseline_value,
        baseline_numerator=0,
        baseline_denominator=0,
    )


def _segments(family: ContributorFamily, team_keys: Sequence[str]) -> list[dict[Dimension, str]]:
    values = [
        tuple(team_keys) if dim is Dimension.SUPPORT_TEAM else _ENUM_VALUES[dim]
        for dim in family.dimensions
    ]
    return [
        dict(zip(family.dimensions, combo, strict=True)) for combo in itertools.product(*values)
    ]


def analyze(session: Session, snapshot: MetricSnapshot, team_keys: Sequence[str]) -> AnalysisResult:
    """Rank contributors across every family for the anomaly's metric snapshot.

    Raises:
        SegmentationNotSupportedError: the metric is a mean, which has no additive split.
        WindowMismatchError: the snapshot's windows are not the standard analysis windows.
    """
    definition = METRIC_REGISTRY[snapshot.metric_key]
    if not supports_segmentation(definition):
        raise SegmentationNotSupportedError(
            f"{definition.display_name} is a {definition.aggregation} metric and "
            "has no additive per-segment contribution."
        )
    window = verified_window(snapshot)
    base = base_filters_of(snapshot)
    method = method_for(definition)

    parent_rate = None
    if definition.is_rate:
        parent = compute_metric(
            definition, window, base, fetch_bucket_aggregates(session, window, base)
        )
        parent_rate = parent_baseline_rate(
            sum(day.numerator for day in parent.baseline_days),
            sum(day.denominator or 0 for day in parent.baseline_days),
        )

    result = AnalysisResult(definition=definition, method=method, window=window, base_filters=base)
    for family in FAMILIES:
        if any(dim in base for dim in family.dimensions):
            result.families.append(
                FamilyResult(family, FamilyRanking(status=FamilyStatus.SKIPPED_FIXED_DIMENSION))
            )
            continue
        deltas: list[SegmentDelta] = []
        excluded: list[Excluded] = []
        for segment in _segments(family, team_keys):
            filters = {**base, **segment}
            segment_result = compute_metric(
                definition, window, filters, fetch_bucket_aggregates(session, window, filters)
            )
            facts = _facts(segment_result, segment)
            outcome = rate_excess(facts, parent_rate) if definition.is_rate else count_delta(facts)
            if isinstance(outcome, Excluded):
                excluded.append(outcome)
            elif outcome is not None:
                deltas.append(outcome)
        result.families.append(
            FamilyResult(
                family,
                rank_segments(deltas, min_sample=min_sample_for(method), excluded=excluded),
            )
        )
    return result
