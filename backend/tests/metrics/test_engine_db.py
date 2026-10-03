"""Known-fixture tests: SQL engine output vs. an independent Python oracle."""

import random
from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Customer, SupportTeam, Ticket
from app.models.enums import TicketCategory, TicketPriority
from app.services.metrics.definitions import (
    METRIC_REGISTRY,
    NEGATIVE_SENTIMENT_THRESHOLD,
    AggregateField,
    Dimension,
)
from app.services.metrics.engine import analysis_window, compute_metric
from app.services.metrics.queries import fetch_bucket_aggregates
from tests.metrics.conftest import World

pytestmark = pytest.mark.db

END = datetime(2026, 3, 10, tzinfo=UTC)
DAY = timedelta(days=1)


def build_fixture(world: World) -> None:
    """~300 deterministic tickets across 10 days, two segments, and two categories."""
    rng = random.Random(4)
    first = END - 10 * DAY
    for _ in range(300):
        created = first + timedelta(minutes=rng.randrange(int(10 * DAY.total_seconds() // 60)))
        world.ticket(
            created,
            customer=rng.choice([world.emea_enterprise, world.apac_starter]),
            category=rng.choice([TicketCategory.BILLING, TicketCategory.TECHNICAL]),
            priority=rng.choice(list(TicketPriority)),
            first_response_minutes=rng.choice([None, *range(5, 400, 7)]),
            resolved_after=rng.choice([None, *(timedelta(minutes=m) for m in (30, 600, 3000))]),
            sla_breached=rng.random() < 0.2,
            escalated=rng.random() < 0.1,
            sentiment=f"{rng.uniform(-1, 1):.3f}",
        )
    # Boundaries: exactly at the current start (current) and exactly at the end (excluded).
    world.ticket(END - DAY, priority=TicketPriority.P1)
    world.ticket(END, priority=TicketPriority.P1)
    world.session.flush()


# --- independent oracle ------------------------------------------------------------

Row = tuple[Ticket, Customer, SupportTeam]


def rows(session: Session, filters: dict[Dimension, str]) -> list[Row]:
    stmt = (
        select(Ticket, Customer, SupportTeam)
        .join(Customer, Ticket.customer_id == Customer.id)
        .join(SupportTeam, Ticket.support_team_id == SupportTeam.id)
    )
    result = [tuple(r) for r in session.execute(stmt)]

    def keep(r: Row) -> bool:
        t, c, s = r
        actual = {
            Dimension.CATEGORY: t.category.value,
            Dimension.PRODUCT: t.product.value,
            Dimension.REGION: c.region.value,
            Dimension.CUSTOMER_TIER: c.tier.value,
            Dimension.SUPPORT_TEAM: s.team_key,
        }
        return all(actual[d] == v for d, v in filters.items())

    return [r for r in result if keep(r)]  # type: ignore[misc]


def created(tickets: Sequence[Ticket], start: datetime, end: datetime) -> list[Ticket]:
    return [t for t in tickets if start <= t.created_at < end]


def ratio(num: int, den: int, scale: int = 1) -> float | None:
    return None if den == 0 else num * scale / den


def oracle_window(key: str, tickets: Sequence[Ticket], start: datetime, end: datetime) -> tuple:
    """Returns (value, numerator, denominator) computed directly from rows."""
    c = created(tickets, start, end)
    match key:
        case "ticket_volume":
            return len(c), len(c), None
        case "p1_ticket_volume":
            n = sum(t.priority is TicketPriority.P1 for t in c)
            return n, n, None
        case "open_backlog":
            n = sum(
                t.created_at < end and (t.resolved_at is None or t.resolved_at >= end)
                for t in tickets
            )
            return n, n, None
        case "first_response_minutes":
            vals = [t.first_response_minutes for t in c if t.first_response_minutes is not None]
            return ratio(sum(vals), len(vals)), sum(vals), len(vals)
        case "resolution_minutes":
            vals = [
                t.resolution_minutes
                for t in tickets
                if t.resolved_at is not None
                and start <= t.resolved_at < end
                and t.resolution_minutes is not None
            ]
            return ratio(sum(vals), len(vals)), sum(vals), len(vals)
        case _:
            predicate: Callable[[Ticket], bool] = {
                "sla_breach_rate": lambda t: t.sla_breached,
                "escalation_rate": lambda t: t.escalated,
                "negative_sentiment_rate": lambda t: (
                    t.sentiment_score <= NEGATIVE_SENTIMENT_THRESHOLD
                ),
            }[key]
            n = sum(predicate(t) for t in c)
            return ratio(n, len(c), 100), n, len(c)


def oracle(key: str, tickets: Sequence[Ticket]) -> tuple[float | None, float | None]:
    window = analysis_window(END)
    current = oracle_window(key, tickets, window.current.start, window.current.end)[0]
    days = [oracle_window(key, tickets, d.start, d.end) for d in window.baseline_days]
    if METRIC_REGISTRY[key].is_rate:
        num, den = sum(d[1] for d in days), sum(d[2] for d in days)
        baseline = ratio(num, den, 100)
    else:
        defined = [d[0] for d in days if d[0] is not None]
        baseline = sum(defined) / len(defined) if defined else None
    return current, baseline


def assert_close(actual: Decimal | None, expected: float | None) -> None:
    if expected is None:
        assert actual is None
    else:
        assert actual is not None
        assert abs(float(actual) - expected) < 1e-5


# --- tests -------------------------------------------------------------------------


@pytest.mark.parametrize(
    "filters",
    [
        {},
        {Dimension.CATEGORY: "billing"},
        {Dimension.REGION: "emea", Dimension.CUSTOMER_TIER: "enterprise"},
        {Dimension.SUPPORT_TEAM: "technical-support", Dimension.PRODUCT: "billing_api"},
    ],
    ids=["overall", "category", "region+tier", "team+product"],
)
@pytest.mark.parametrize("key", sorted(METRIC_REGISTRY))
def test_engine_matches_direct_computation(
    world: World, key: str, filters: dict[Dimension, str]
) -> None:
    build_fixture(world)
    window = analysis_window(END)
    buckets = fetch_bucket_aggregates(world.session, window, filters)
    result = compute_metric(METRIC_REGISTRY[key], window, filters, buckets)

    tickets = [r[0] for r in rows(world.session, filters)]
    expected_current, expected_baseline = oracle(key, tickets)
    assert_close(result.current.value, expected_current)
    assert_close(result.baseline_value, expected_baseline)


def test_ticket_exactly_at_window_end_is_excluded_and_at_start_included(world: World) -> None:
    world.ticket(END - DAY, priority=TicketPriority.P1)
    world.ticket(END, priority=TicketPriority.P1)
    world.session.flush()
    buckets = fetch_bucket_aggregates(world.session, analysis_window(END), {})
    result = compute_metric(METRIC_REGISTRY["p1_ticket_volume"], analysis_window(END), {}, buckets)
    assert result.current.value == 1


def test_current_window_tickets_do_not_change_the_baseline(world: World) -> None:
    window = analysis_window(END)
    for day in window.baseline_days:
        world.ticket(day.start + timedelta(hours=3))
    world.session.flush()
    definition = METRIC_REGISTRY["ticket_volume"]
    before = compute_metric(
        definition, window, {}, fetch_bucket_aggregates(world.session, window, {})
    )

    for minute in range(50):
        world.ticket(window.current.start + timedelta(minutes=minute))
    world.session.flush()
    after = compute_metric(
        definition, window, {}, fetch_bucket_aggregates(world.session, window, {})
    )

    assert before.baseline_value == after.baseline_value == Decimal(1)
    assert (before.current.value, after.current.value) == (0, 50)


def test_tickets_before_the_baseline_are_ignored(world: World) -> None:
    window = analysis_window(END)
    world.ticket(window.baseline.start - timedelta(seconds=1))
    world.session.flush()
    buckets = fetch_bucket_aggregates(world.session, window, {})
    assert all(b[AggregateField.TICKETS] == 0 for b in buckets)
    volume = compute_metric(METRIC_REGISTRY["ticket_volume"], window, {}, buckets)
    assert volume.baseline_value == 0
    # Still open at every bucket end, so it counts toward backlog.
    backlog = compute_metric(METRIC_REGISTRY["open_backlog"], window, {}, buckets)
    assert backlog.current.value == 1


def test_backlog_is_point_in_time_by_resolved_at(world: World) -> None:
    window = analysis_window(END)
    # Resolved inside the current window: open at every baseline day end, closed at END.
    world.ticket(window.baseline.start, resolved_after=7 * DAY + timedelta(hours=2))
    world.session.flush()
    buckets = fetch_bucket_aggregates(world.session, window, {})
    result = compute_metric(METRIC_REGISTRY["open_backlog"], window, {}, buckets)
    assert result.current.value == 0
    assert result.baseline_value == 1


def test_resolution_uses_resolved_in_window_cohort(world: World) -> None:
    window = analysis_window(END)
    # Created in the baseline, resolved in the current window after 3 days.
    world.ticket(window.current.start - 3 * DAY, resolved_after=3 * DAY + timedelta(hours=1))
    world.session.flush()
    buckets = fetch_bucket_aggregates(world.session, window, {})
    result = compute_metric(METRIC_REGISTRY["resolution_minutes"], window, {}, buckets)
    assert result.current.value == Decimal(3 * 24 * 60 + 60)
    assert result.baseline_value is None


def test_rate_numerator_and_denominator_are_counted_correctly(world: World) -> None:
    window = analysis_window(END)
    day = window.baseline_days[0]
    for i in range(10):  # 10 tickets, 3 breached, on one baseline day
        world.ticket(day.start + timedelta(minutes=i), sla_breached=i < 3)
    for i in range(90):  # 90 tickets, 9 breached, on another
        world.ticket(window.baseline_days[3].start + timedelta(minutes=i), sla_breached=i < 9)
    for i in range(25):  # current: 25 tickets, 5 breached
        world.ticket(window.current.start + timedelta(minutes=i), sla_breached=i < 5)
    world.session.flush()

    buckets = fetch_bucket_aggregates(world.session, window, {})
    result = compute_metric(METRIC_REGISTRY["sla_breach_rate"], window, {}, buckets)
    assert (result.current.numerator, result.current.denominator) == (5, 25)
    assert result.current.value == Decimal(20)
    assert result.baseline_value == Decimal(12)  # 12 / 100 pooled, not mean(30%, 10%)
