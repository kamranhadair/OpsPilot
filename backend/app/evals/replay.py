"""Historical replay: which anomalies the deterministic pipeline shows on each recent day.

Read-only: every day is computed in memory with the production windows, rules and
detection slices; nothing is persisted and the canonical seed is untouched.
"""

from datetime import timedelta

from sqlalchemy.orm import Session

from app.evals.pipeline import data_range, evaluate_slice, window_in_range
from app.models.enums import AnomalySeverity
from app.schemas.evaluations import ReplayAnomaly, ReplayDay, ReplaySummary
from app.services.anomalies.detector import Detection
from app.services.anomalies.rules import DETECTION_SLICES
from app.services.metrics.definitions import METRIC_REGISTRY
from app.services.metrics.engine import analysis_window

DEFAULT_REPLAY_DAYS = 7
MAX_REPLAY_DAYS = 30
_ESCALATED = frozenset({AnomalySeverity.HIGH, AnomalySeverity.CRITICAL})


def replay(session: Session, days: int = DEFAULT_REPLAY_DAYS) -> ReplaySummary:
    """Replay the final ``days`` analysis days, oldest first."""
    bounds = data_range(session)
    if bounds is None:
        return ReplaySummary(status="not_run", reason="no tickets available", days_requested=days)

    results: list[ReplayDay] = []
    for offset in range(days - 1, -1, -1):
        window = analysis_window(bounds[1] - timedelta(days=offset))
        start, end = window.current.start, window.current.end
        if not window_in_range(window, bounds):
            results.append(
                ReplayDay(
                    window_start=start,
                    window_end=end,
                    status="no_data",
                    detail="The window or its 7-day baseline lies outside the available data.",
                )
            )
            continue

        slices = [
            evaluate_slice(session, end, {str(k): v for k, v in f.items()})
            for f in DETECTION_SLICES
        ]
        overall_volume = next(o for o in slices[0] if o.metric_key == "ticket_volume")
        if overall_volume.result.current.numerator == 0:
            results.append(
                ReplayDay(
                    window_start=start,
                    window_end=end,
                    status="no_data",
                    detail="No tickets were created in this window.",
                )
            )
            continue
        anomalies = [
            ReplayAnomaly(
                metric_key=o.metric_key,
                display_name=METRIC_REGISTRY[o.metric_key].display_name,
                filters=o.filters,
                severity=o.outcome.severity,
                score=float(o.outcome.score),
            )
            for outcomes in slices
            for o in outcomes
            if isinstance(o.outcome, Detection)
        ]
        results.append(
            ReplayDay(
                window_start=start,
                window_end=end,
                status="ok",
                anomalies=anomalies,
                high_or_critical_count=sum(1 for a in anomalies if a.severity in _ESCALATED),
            )
        )
    return ReplaySummary(status="completed", days_requested=days, days=results)
