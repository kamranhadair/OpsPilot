"""Metrics service: persistence, idempotency, provenance, edge cases, demo sanity."""

import math
import re
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import MetricSnapshot
from app.models.enums import TicketCategory, TicketPriority
from app.schemas.metrics import MetricFilters
from app.services.demo_data.seeder import seed_demo_data
from app.services.metrics.definitions import METRIC_REGISTRY
from app.services.metrics.errors import (
    InvalidDimensionValueError,
    NoSourceDataError,
    WindowOutOfRangeError,
)
from app.services.metrics.provenance import MetricProvenance
from app.services.metrics.service import MetricsService
from tests.db import factories
from tests.metrics.conftest import World

pytestmark = pytest.mark.db

END = datetime(2026, 3, 10, tzinfo=UTC)
DAY = timedelta(days=1)


def snapshot_count(session: Session) -> int:
    return session.execute(select(func.count()).select_from(MetricSnapshot)).scalar_one()


def fill_days(world: World, *, per_day: int = 25, days: int = 9) -> None:
    """``per_day`` tickets on each of the ``days`` UTC days ending at END."""
    for d in range(days):
        start = END - (days - d) * DAY
        for i in range(per_day):
            world.ticket(
                start + timedelta(minutes=10 * i),
                sla_breached=i % 5 == 0,
                resolved_after=timedelta(hours=2),
            )
    world.session.flush()


def items_by_key(response: object) -> dict[str, object]:
    return {item.metric_key: item for item in response.items}  # type: ignore[attr-defined]


def test_compute_persists_all_eight_metrics_with_mtr_ids(world: World) -> None:
    fill_days(world)
    response = MetricsService(world.session).compute(END, MetricFilters())

    assert {i.metric_key for i in response.items} == set(METRIC_REGISTRY)
    assert all(i.status == "computed" for i in response.items)
    assert snapshot_count(world.session) == 8
    for item in response.items:
        assert item.snapshot is not None
        assert re.fullmatch(r"MTR-\d{6,}", item.snapshot.evidence_id)


def test_default_window_end_is_midnight_after_last_ticket(world: World) -> None:
    fill_days(world)
    response = MetricsService(world.session).compute(None, MetricFilters())
    assert response.window_end == END
    assert response.baseline_start == END - 8 * DAY


def test_provenance_has_windows_filters_samples_and_daily_breakdown(world: World) -> None:
    fill_days(world)
    filters = MetricFilters(category=TicketCategory.BILLING, support_team="billing-support")
    MetricsService(world.session).compute(END, filters)

    row = world.session.execute(
        select(MetricSnapshot).where(MetricSnapshot.metric_key == "sla_breach_rate")
    ).scalar_one()
    provenance = MetricProvenance.model_validate(row.provenance_json)

    assert provenance.source.table == "tickets"
    assert provenance.definition.key == "sla_breach_rate"
    assert provenance.definition.version == 1
    assert provenance.current_window.start == END - DAY
    assert provenance.current_window.end == END
    assert (provenance.baseline.start, provenance.baseline.end) == (END - 8 * DAY, END - DAY)
    assert len(provenance.baseline.days) == 7
    assert provenance.filters == {"category": "billing", "support_team": "billing-support"}
    assert row.dimensions_json == provenance.filters
    assert provenance.sample.current_sample_size == row.sample_size == 25
    assert provenance.sample.current_numerator == 5
    assert provenance.sample.baseline_sample_size == 7 * 25
    assert provenance.sample.sufficient
    assert provenance.signature == row.analysis_signature
    assert provenance.computed_at == row.computed_at


def test_repeated_compute_is_idempotent(world: World) -> None:
    fill_days(world)
    service = MetricsService(world.session)
    first = service.compute(END, MetricFilters())
    second = service.compute(END, MetricFilters())

    assert snapshot_count(world.session) == 8
    assert all(i.status == "reused" for i in second.items)
    assert [i.snapshot.evidence_id for i in first.items if i.snapshot] == [
        i.snapshot.evidence_id for i in second.items if i.snapshot
    ]


def test_different_signature_creates_new_snapshots(world: World) -> None:
    fill_days(world)
    service = MetricsService(world.session)
    service.compute(END, MetricFilters())
    service.compute(END, MetricFilters(category=TicketCategory.BILLING))
    service.compute(END - DAY, MetricFilters())
    assert snapshot_count(world.session) == 24


def test_duplicate_signature_is_rejected_by_the_database(clean_db: Session) -> None:
    clean_db.add(factories.metric_snapshot(clean_db, analysis_signature="dup"))
    clean_db.flush()
    with pytest.raises(IntegrityError), clean_db.begin_nested():
        clean_db.add(factories.metric_snapshot(clean_db, analysis_signature="dup"))
        clean_db.flush()


def test_zero_baseline_yields_null_change_and_flag(world: World) -> None:
    fill_days(world)
    world.ticket(END - timedelta(hours=1), priority=TicketPriority.P1)
    world.session.flush()
    response = MetricsService(world.session).compute(END, MetricFilters())

    p1 = items_by_key(response)["p1_ticket_volume"].snapshot  # type: ignore[attr-defined]
    assert p1.value == 1
    assert p1.baseline_value == 0
    assert p1.change_pct is None
    assert p1.baseline_zero
    for item in response.items:
        snap = item.snapshot
        assert snap is not None
        for number in (snap.value, snap.baseline_value, snap.change_pct, snap.change_pp):
            assert number is None or math.isfinite(number)


def test_rate_metrics_expose_percentage_point_difference(world: World) -> None:
    fill_days(world)
    response = MetricsService(world.session).compute(END, MetricFilters())
    by_key = items_by_key(response)
    breach = by_key["sla_breach_rate"].snapshot  # type: ignore[attr-defined]
    assert breach.value == 20 and breach.baseline_value == 20
    assert breach.change_pp == 0
    assert by_key["ticket_volume"].snapshot.change_pp is None  # type: ignore[attr-defined]


def test_empty_current_window_persists_counts_and_skips_undefined(world: World) -> None:
    fill_days(world)
    # A day after the data but still within range: shift the last ticket later.
    world.ticket(END + 2 * DAY - timedelta(minutes=1), category=TicketCategory.TECHNICAL)
    world.session.flush()
    response = MetricsService(world.session).compute(
        END + DAY, MetricFilters(category=TicketCategory.BILLING)
    )
    by_key = items_by_key(response)
    assert by_key["ticket_volume"].status == "computed"  # type: ignore[attr-defined]
    assert by_key["ticket_volume"].snapshot.value == 0  # type: ignore[attr-defined]
    for key in ("first_response_minutes", "sla_breach_rate", "escalation_rate"):
        assert by_key[key].status == "insufficient_data"  # type: ignore[attr-defined]
        assert by_key[key].snapshot is None  # type: ignore[attr-defined]
    assert snapshot_count(world.session) == len(
        [i for i in response.items if i.status == "computed"]
    )


def test_small_sample_is_persisted_but_flagged_insufficient(world: World) -> None:
    fill_days(world, per_day=5)
    response = MetricsService(world.session).compute(END, MetricFilters())
    breach = items_by_key(response)["sla_breach_rate"].snapshot  # type: ignore[attr-defined]
    assert breach.sample_size == 5
    assert not breach.sample_sufficient
    assert breach.provenance.sample.min_required == 20


def test_no_tickets_is_reported(clean_db: Session) -> None:
    with pytest.raises(NoSourceDataError):
        MetricsService(clean_db).compute(None, MetricFilters())


@pytest.mark.parametrize("offset", [-DAY, DAY], ids=["baseline-before-data", "after-data"])
def test_window_outside_available_data_is_rejected(world: World, offset: timedelta) -> None:
    fill_days(world, days=9)  # data covers exactly END-9d .. END
    window_end = END + offset if offset > timedelta(0) else END - 2 * DAY + offset
    with pytest.raises(WindowOutOfRangeError):
        MetricsService(world.session).compute(window_end, MetricFilters())
    assert snapshot_count(world.session) == 0


def test_unknown_support_team_is_rejected(world: World) -> None:
    fill_days(world)
    with pytest.raises(InvalidDimensionValueError):
        MetricsService(world.session).compute(END, MetricFilters(support_team="nope"))


def test_overview_returns_latest_overall_window(world: World) -> None:
    fill_days(world)
    service = MetricsService(world.session)
    assert service.overview(None).items == []
    service.compute(END - DAY, MetricFilters())
    service.compute(END, MetricFilters())
    service.compute(END, MetricFilters(category=TicketCategory.BILLING))

    overview = service.overview(None)
    assert overview.window_end == END
    assert {i.metric_key for i in overview.items} == set(METRIC_REGISTRY)
    assert all(i.dimensions == {} for i in overview.items)
    assert overview.missing_metric_keys == []


def test_series_is_ordered_and_filtered(world: World) -> None:
    fill_days(world)
    service = MetricsService(world.session)
    for end in (END, END - DAY):
        service.compute(end, MetricFilters())
    service.compute(END, MetricFilters(category=TicketCategory.BILLING))

    series = service.series("ticket_volume", None, None, MetricFilters())
    assert [p.window_end for p in series.points] == [END - DAY, END]
    billing = service.series(
        "ticket_volume", None, None, MetricFilters(category=TicketCategory.BILLING)
    )
    assert [p.dimensions for p in billing.points] == [{"category": "billing"}]
    latest = service.series("ticket_volume", None, None, MetricFilters(), limit=1)
    assert [p.window_end for p in latest.points] == [END]
    ranged = service.series("ticket_volume", END, END, MetricFilters())
    assert [p.window_end for p in ranged.points] == [END]


def test_demo_dataset_shows_the_planted_billing_signal(clean_db: Session) -> None:
    seed_demo_data(clean_db, settings=Settings(environment="development"))
    response = MetricsService(clean_db).compute(
        None, MetricFilters(category=TicketCategory.BILLING)
    )
    assert response.window_end == datetime(2026, 10, 4, tzinfo=UTC)
    by_key = items_by_key(response)
    volume = by_key["ticket_volume"].snapshot  # type: ignore[attr-defined]
    breach = by_key["sla_breach_rate"].snapshot  # type: ignore[attr-defined]
    assert volume.change_pct > 60
    assert breach.value > breach.baseline_value
