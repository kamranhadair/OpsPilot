"""Dashboard overview composition over persisted snapshots and anomalies."""

from datetime import timedelta

import pytest
from sqlalchemy.orm import Session

from app.models.enums import AnomalyStatus
from app.schemas.metrics import MetricFilters
from app.services.anomalies.service import AnomalyService
from app.services.dashboard.service import CARD_METRIC_KEYS, TREND_METRIC_KEYS, DashboardService
from app.services.metrics.service import MetricsService
from tests.anomalies.conftest import END
from tests.metrics.conftest import World

pytestmark = pytest.mark.db


def test_empty_database_is_an_explicit_empty_overview(clean_db: Session) -> None:
    overview = DashboardService(clean_db).overview()

    assert overview.window_end is None
    assert overview.cards == []
    assert set(overview.missing_metric_keys) >= set(CARD_METRIC_KEYS)
    assert [t.definition.key for t in overview.trends] == list(TREND_METRIC_KEYS)
    assert all(t.points == [] for t in overview.trends)
    assert overview.active_anomalies == []
    assert overview.active_anomaly_total == 0


def test_cards_are_the_overall_overview_snapshots_in_display_order(
    spike_world: World,
) -> None:
    session = spike_world.session
    MetricsService(session).compute(END, MetricFilters())

    overview = DashboardService(session).overview()
    expected = MetricsService(session).overview(None)

    assert overview.window_end == expected.window_end == END
    assert {c.evidence_id for c in overview.cards} == {s.evidence_id for s in expected.items}
    keys = [c.metric_key for c in overview.cards]
    present_headline = [k for k in CARD_METRIC_KEYS if k in keys]
    assert keys[: len(present_headline)] == present_headline
    assert overview.missing_metric_keys == expected.missing_metric_keys


def test_trend_points_mirror_the_series_oldest_first(spike_world: World) -> None:
    session = spike_world.session
    MetricsService(session).compute(END, MetricFilters())
    # A billing-only snapshot must never leak into the overall trend.
    MetricsService(session).compute(END, MetricFilters.model_validate({"category": "billing"}))

    overview = DashboardService(session).overview()

    for trend in overview.trends:
        series = MetricsService(session).series(
            trend.definition.key, None, None, MetricFilters(), 30
        )
        assert [p.evidence_id for p in trend.points] == [p.evidence_id for p in series.points]
        assert [p.value for p in trend.points] == [p.value for p in series.points]
        windows = [p.window_end for p in trend.points]
        assert windows == sorted(windows)


def test_active_anomalies_come_from_the_anomaly_list_in_its_order(spike_world: World) -> None:
    session = spike_world.session
    AnomalyService(session).detect(END)

    overview = DashboardService(session).overview()
    listed = AnomalyService(session).list(status=AnomalyStatus.ACTIVE, limit=10)

    assert overview.active_anomaly_total == listed.total > 0
    assert [a.evidence_id for a in overview.active_anomalies] == [
        a.evidence_id for a in listed.items
    ]
    billing = next(
        a
        for a in overview.active_anomalies
        if a.metric_key == "ticket_volume" and a.dimensions == {"category": "billing"}
    )
    assert billing.severity == "high"  # read from the detector, not recomputed


def test_overview_is_read_only(spike_world: World) -> None:
    session = spike_world.session
    before = DashboardService(session).overview()
    again = DashboardService(session).overview()
    assert before == again
    assert before.window_end is None  # nothing was computed by reading


def test_trend_is_bounded_and_ordered_across_windows(demo_session: Session) -> None:
    metrics = MetricsService(demo_session)
    latest = metrics.compute(None, MetricFilters()).window_end
    for offset in (1, 2):
        metrics.compute(latest - timedelta(days=offset), MetricFilters())

    trend = DashboardService(demo_session).overview().trends[0]

    assert trend.definition.key == "ticket_volume"
    assert [p.window_end for p in trend.points] == [
        latest - timedelta(days=2),
        latest - timedelta(days=1),
        latest,
    ]
