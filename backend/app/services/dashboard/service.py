"""Dashboard overview: one read-only composition of existing deterministic read paths.

Nothing is computed here. Cards, trends and the active anomaly summary come from
persisted snapshots and anomalies via the metrics and anomaly services; this module
only decides which metrics the overview shows and in what order.
"""

from sqlalchemy.orm import Session

from app.models.enums import AnomalyStatus
from app.schemas.dashboard import DashboardOverviewResponse, DashboardTrend, TrendPoint
from app.schemas.metrics import MetricFilters, MetricSnapshotOut
from app.services.anomalies.service import AnomalyService
from app.services.metrics.definitions import METRIC_REGISTRY
from app.services.metrics.service import MetricsService

# Headline cards first, in this order; every other registered metric follows in registry order.
CARD_METRIC_KEYS: tuple[str, ...] = (
    "ticket_volume",
    "open_backlog",
    "sla_breach_rate",
    "escalation_rate",
)
TREND_METRIC_KEYS: tuple[str, ...] = ("ticket_volume", "sla_breach_rate", "open_backlog")
TREND_POINTS = 30
ACTIVE_ANOMALY_LIMIT = 10

_unknown = (set(CARD_METRIC_KEYS) | set(TREND_METRIC_KEYS)) - set(METRIC_REGISTRY)
if _unknown:  # pragma: no cover - guards against registry drift
    raise RuntimeError(f"Dashboard references unknown metrics: {sorted(_unknown)}")


_CARD_RANK = {
    key: rank
    for rank, key in enumerate(
        (*CARD_METRIC_KEYS, *(k for k in METRIC_REGISTRY if k not in CARD_METRIC_KEYS))
    )
}


def _card_order(card: MetricSnapshotOut) -> int:
    return _CARD_RANK[card.metric_key]


class DashboardService:
    def __init__(self, session: Session) -> None:
        self.metrics = MetricsService(session)
        self.anomalies = AnomalyService(session)

    def overview(self) -> DashboardOverviewResponse:
        """Latest overall cards, short overall trends and active anomalies, read-only."""
        latest = self.metrics.overview(None)
        trends = [self._trend(key) for key in TREND_METRIC_KEYS]
        active = self.anomalies.list(status=AnomalyStatus.ACTIVE, limit=ACTIVE_ANOMALY_LIMIT)
        return DashboardOverviewResponse(
            window_end=latest.window_end,
            cards=sorted(latest.items, key=_card_order),
            missing_metric_keys=latest.missing_metric_keys,
            trends=trends,
            active_anomalies=active.items,
            active_anomaly_total=active.total,
        )

    def _trend(self, metric_key: str) -> DashboardTrend:
        series = self.metrics.series(metric_key, None, None, MetricFilters(), TREND_POINTS)
        return DashboardTrend(
            definition=series.definition,
            points=[
                TrendPoint(
                    evidence_id=point.evidence_id,
                    window_end=point.window_end,
                    value=point.value,
                    baseline_value=point.baseline_value,
                    change_pct=point.change_pct,
                    sample_size=point.sample_size,
                )
                for point in series.points
            ],
        )
