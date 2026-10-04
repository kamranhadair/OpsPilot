"""Read-only deterministic pipeline used by golden cases and replay.

It runs the production metric math and anomaly detector for one slice/window
without persisting anything: ``fetch_bucket_aggregates`` -> ``compute_metric`` ->
``detect``. Window semantics, rules and slices are the production ones, so the
current window is never part of its own baseline and later data never leaks into
an earlier window.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.repositories.metric_repository import MetricRepository
from app.schemas.metrics import MetricFilters
from app.services.anomalies.detector import Detection, DetectionInput, Skip, SkipReason, detect
from app.services.anomalies.rules import ANOMALY_RULES
from app.services.metrics.definitions import METRIC_REGISTRY, Dimension
from app.services.metrics.engine import (
    AnalysisWindow,
    MetricResult,
    analysis_window,
    compute_metric,
    to_utc,
    utc_midnight,
)
from app.services.metrics.queries import fetch_bucket_aggregates


@dataclass(frozen=True)
class SliceOutcome:
    metric_key: str
    filters: dict[str, str]
    result: MetricResult
    outcome: Detection | Skip


def detection_input_from_result(result: MetricResult) -> DetectionInput:
    """The facts ``AnomalyService`` reads back from a persisted snapshot, taken in memory.

    A test asserts this equals the production input built from the persisted snapshot.
    """
    if result.current.value is None:
        raise ValueError("An undefined metric has no detection input.")
    return DetectionInput(
        metric_key=result.definition.key,
        direction=result.definition.direction,
        value=result.current.value,
        baseline_value=result.baseline_value,
        change_pct=result.change_pct,
        baseline_zero=result.baseline_zero,
        current_sample_size=result.current.sample_size,
        baseline_sample_size=result.baseline_sample_size,
        daily_baseline_values=[
            None if day.value is None else float(day.value) for day in result.baseline_days
        ],
    )


def data_range(session: Session) -> tuple[datetime, datetime] | None:
    """``[first midnight, midnight after the last ticket)`` like the metrics service."""
    bounds = MetricRepository(session).ticket_time_bounds()
    if bounds is None:
        return None
    return utc_midnight(bounds[0]), utc_midnight(bounds[1]) + timedelta(days=1)


def window_in_range(window: AnalysisWindow, bounds: tuple[datetime, datetime]) -> bool:
    return window.baseline.start >= bounds[0] and window.current.end <= bounds[1]


def evaluate_slice(
    session: Session, window_end: datetime, filters: Mapping[str, str]
) -> list[SliceOutcome]:
    """Every rule-configured metric for one slice/window, detected without persistence."""
    dimensions: dict[Dimension, str] = MetricFilters.model_validate(dict(filters)).as_dimensions()
    window = analysis_window(to_utc(window_end))
    buckets = fetch_bucket_aggregates(session, window, dimensions)
    canonical = {str(k): v for k, v in sorted(dimensions.items())}
    outcomes: list[SliceOutcome] = []
    for metric_key in ANOMALY_RULES:
        result = compute_metric(METRIC_REGISTRY[metric_key], window, dimensions, buckets)
        outcome: Detection | Skip
        if not result.is_defined:
            outcome = Skip(SkipReason.NO_DATA, "The current window has no samples.")
        else:
            outcome = detect(detection_input_from_result(result))
        outcomes.append(SliceOutcome(metric_key, canonical, result, outcome))
    return outcomes
