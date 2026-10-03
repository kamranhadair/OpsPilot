"""Deterministic invariants of the synthetic dataset. Pure: no database needed."""

import statistics
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from functools import cache
from pathlib import Path

import pytest

import app.services.demo_data as demo_data_package
from app.models.enums import (
    CustomerTier,
    Product,
    Region,
    TicketCategory,
    TicketChannel,
    TicketPriority,
)
from app.services.demo_data.config import (
    DEFAULT_CONFIG,
    DEPLOYMENT_AT,
    SEED_VERSION,
    WINDOW_END,
    WINDOW_START,
)
from app.services.demo_data.generator import (
    TicketRefCollisionError,
    assign_refs,
    generate_dataset,
)
from app.services.demo_data.records import DemoDataset, TicketRecord, dataset_checksum

# Pinned for SEED_VERSION "1". If a deliberate config/generator change alters the
# dataset, update these AND bump SEED_VERSION in config.py (evals key off it).
GOLDEN_SEED_VERSION = "1"
GOLDEN_TICKET_COUNT = 5781
GOLDEN_CHECKSUM = "215c2254a8f00b90c4779c95deed3f9587afe5be356322cbcf60af489da62f0b"

LAST_DAY = datetime(2026, 10, 3, tzinfo=UTC)


@cache
def dataset() -> DemoDataset:
    return generate_dataset()


def customers_by_ref() -> dict[str, tuple[Region, CustomerTier]]:
    return {c.customer_ref: (c.region, c.tier) for c in dataset().customers}


def segment(ticket: TicketRecord) -> tuple[Region, CustomerTier]:
    return customers_by_ref()[ticket.customer_ref]


def billing(tickets: Iterable[TicketRecord]) -> list[TicketRecord]:
    return [t for t in tickets if t.category is TicketCategory.BILLING]


def between(tickets: Iterable[TicketRecord], start: datetime, end: datetime) -> list[TicketRecord]:
    return [t for t in tickets if start <= t.created_at < end]


def rate(tickets: list[TicketRecord], predicate: Callable[[TicketRecord], bool]) -> float:
    return sum(predicate(t) for t in tickets) / len(tickets)


def positive_delta_share(
    current: list[TicketRecord],
    baseline: list[TicketRecord],
    *,
    current_scale: float,
    baseline_scale: float,
    target: tuple[Region, CustomerTier],
) -> float:
    """Share of the summed positive region x tier deltas held by ``target``."""
    cur = Counter(segment(t) for t in current)
    base = Counter(segment(t) for t in baseline)
    deltas = {
        seg: cur[seg] * current_scale - base[seg] * baseline_scale for seg in set(cur) | set(base)
    }
    return deltas[target] / sum(d for d in deltas.values() if d > 0)


EMEA_ENTERPRISE = (Region.EMEA, CustomerTier.ENTERPRISE)
PRE_INCIDENT = [t for t in dataset().tickets if t.created_at < DEPLOYMENT_AT]


# --- determinism ------------------------------------------------------------------


def test_same_seed_gives_identical_dataset() -> None:
    first, second = generate_dataset(), generate_dataset()
    assert len(first.tickets) == len(second.tickets)
    assert dataset_checksum(first) == dataset_checksum(second)
    assert first == second


def test_golden_counts_and_checksum_match_seed_version() -> None:
    assert SEED_VERSION == GOLDEN_SEED_VERSION, "Update the golden values for the new seed version."
    assert len(dataset().tickets) == GOLDEN_TICKET_COUNT
    assert dataset_checksum(dataset()) == GOLDEN_CHECKSUM, (
        "The generated dataset changed. If intentional, bump SEED_VERSION and refresh the goldens."
    )


def test_different_seed_gives_different_dataset() -> None:
    other = generate_dataset(replace(DEFAULT_CONFIG, seed="another-seed"))
    assert dataset_checksum(other) != dataset_checksum(dataset())


# --- window -----------------------------------------------------------------------


def test_window_covers_45_fixed_days() -> None:
    assert timedelta(days=45) == (WINDOW_END - WINDOW_START)
    days = {t.created_at.date() for t in dataset().tickets}
    assert len(days) == 45
    assert min(days) == datetime(2026, 8, 20).date()
    assert max(days) == LAST_DAY.date()


def test_all_timestamps_are_utc_and_inside_window() -> None:
    for t in dataset().tickets:
        assert t.created_at.utcoffset() == timedelta(0)
        assert WINDOW_START <= t.created_at < WINDOW_END
        if t.resolved_at is not None:
            assert t.created_at <= t.resolved_at < WINDOW_END


# --- entities ---------------------------------------------------------------------


def test_every_region_tier_cell_has_customers() -> None:
    cells = {(c.region, c.tier) for c in dataset().customers}
    assert cells == {(r, t) for r in Region for t in CustomerTier}


def test_customer_refs_and_names_are_unique_and_fictional_demo_refs() -> None:
    refs = [c.customer_ref for c in dataset().customers]
    names = [c.name for c in dataset().customers]
    assert len(set(refs)) == len(refs) and len(set(names)) == len(names)
    assert all(ref.startswith("DEMO-CUST-") for ref in refs)


def test_four_support_teams() -> None:
    assert {t.name for t in dataset().teams} == {
        "Billing Support",
        "Technical Support",
        "Integration Support",
        "Account Support",
    }


def test_every_enum_dimension_is_represented() -> None:
    tickets = dataset().tickets
    assert {t.category for t in tickets} == set(TicketCategory)
    assert {t.product for t in tickets} == set(Product)
    assert {t.priority for t in tickets} == set(TicketPriority)
    assert {t.channel for t in tickets} == set(TicketChannel)
    assert {t.team_key for t in tickets} == {t.team_key for t in dataset().teams}


def test_tickets_reference_existing_customers_and_teams_with_unique_refs() -> None:
    refs = [t.ticket_ref for t in dataset().tickets]
    assert len(set(refs)) == len(refs)
    assert all(ref.startswith("DEMO-TCK-") for ref in refs)
    assert {t.customer_ref for t in dataset().tickets} <= set(customers_by_ref())


# --- normal behaviour -------------------------------------------------------------


def test_normal_weekly_volume_is_800_to_1000() -> None:
    for week in range(6):  # six complete pre-incident weeks (2026-08-20 .. 2026-09-30)
        start = WINDOW_START + timedelta(days=7 * week)
        count = len(between(dataset().tickets, start, start + timedelta(days=7)))
        assert 800 <= count <= 1000, f"week {week}: {count}"


def test_weekdays_are_busier_than_weekends() -> None:
    per_day = Counter(t.created_at.date() for t in PRE_INCIDENT)
    weekday = [n for d, n in per_day.items() if d.weekday() < 5]
    weekend = [n for d, n in per_day.items() if d.weekday() >= 5]
    assert statistics.mean(weekday) > 1.8 * statistics.mean(weekend)


def test_priority_mix_is_dominated_by_p3_p4_with_larger_slas_for_lower_priorities() -> None:
    tickets = dataset().tickets
    assert rate(tickets, lambda t: t.priority in (TicketPriority.P3, TicketPriority.P4)) >= 0.7
    targets = {t.priority: t.sla_target_minutes for t in tickets}
    assert targets[TicketPriority.P1] < targets[TicketPriority.P2]
    assert targets[TicketPriority.P2] < targets[TicketPriority.P3]
    assert targets[TicketPriority.P3] < targets[TicketPriority.P4]


def test_baseline_escalation_is_low_but_nonzero() -> None:
    assert 0.0 < rate(PRE_INCIDENT, lambda t: t.escalated) < 0.08


def test_sentiment_is_mostly_non_negative_with_a_negative_tail() -> None:
    scores = [t.sentiment_score for t in PRE_INCIDENT]
    assert statistics.median(scores) >= Decimal(0)
    negative = rate(PRE_INCIDENT, lambda t: t.sentiment_score <= Decimal("-0.3"))
    assert 0.03 < negative < 0.25


def test_rows_satisfy_schema_constraints_and_sla_consistency() -> None:
    for t in dataset().tickets:
        assert Decimal(-1) <= t.sentiment_score <= Decimal(1)
        assert t.sla_target_minutes > 0
        assert t.first_response_minutes is not None and t.first_response_minutes >= 0
        assert t.sla_breached == (t.first_response_minutes > t.sla_target_minutes)
        assert (t.resolved_at is None) == (t.resolution_minutes is None)
        if t.resolved_at is not None:
            assert t.resolution_minutes == int((t.resolved_at - t.created_at).total_seconds() // 60)
        assert len(t.subject) <= 200


def test_normal_billing_sla_breach_rate_is_about_8_percent() -> None:
    assert 0.06 <= rate(billing(PRE_INCIDENT), lambda t: t.sla_breached) <= 0.10


# --- planted incident -------------------------------------------------------------


def test_single_billing_api_deployment_event_on_oct_1() -> None:
    event = dataset().incident
    assert event.event_type == "deployment"
    assert event.product is Product.BILLING_API
    assert event.occurred_at == DEPLOYMENT_AT
    assert event.occurred_at.date() == datetime(2026, 10, 1).date()
    assert event.metadata["synthetic"] is True


def test_no_incident_tickets_before_the_deployment() -> None:
    # Pre-deployment Billing volume follows the normal weekday pattern (no early spike).
    per_day = Counter(t.created_at.date() for t in billing(PRE_INCIDENT))
    weekday = [n for d, n in per_day.items() if d.weekday() < 5]
    assert max(weekday) < 1.6 * statistics.mean(weekday)


def test_billing_volume_materially_exceeds_preceding_baseline() -> None:
    tickets = dataset().tickets
    # (a) hourly rate after the deployment vs the 7 days before it
    post = billing(between(tickets, DEPLOYMENT_AT, WINDOW_END))
    pre = billing(between(tickets, DEPLOYMENT_AT - timedelta(days=7), DEPLOYMENT_AT))
    post_hours = (WINDOW_END - DEPLOYMENT_AT).total_seconds() / 3600
    assert (len(post) / post_hours) / (len(pre) / 168) >= 1.6
    # (b) final day vs the mean of the seven preceding days (Spec 04 window contract)
    final = billing(between(tickets, LAST_DAY, WINDOW_END))
    baseline = billing(between(tickets, LAST_DAY - timedelta(days=7), LAST_DAY))
    assert len(final) / (len(baseline) / 7) >= 1.6


def test_emea_enterprise_dominates_excess_billing_volume() -> None:
    tickets = dataset().tickets
    post = billing(between(tickets, DEPLOYMENT_AT, WINDOW_END))
    pre = billing(between(tickets, DEPLOYMENT_AT - timedelta(days=7), DEPLOYMENT_AT))
    post_hours = (WINDOW_END - DEPLOYMENT_AT).total_seconds() / 3600
    share_a = positive_delta_share(
        post,
        pre,
        current_scale=1 / post_hours,
        baseline_scale=1 / 168,
        target=EMEA_ENTERPRISE,
    )
    final = billing(between(tickets, LAST_DAY, WINDOW_END))
    baseline = billing(between(tickets, LAST_DAY - timedelta(days=7), LAST_DAY))
    share_b = positive_delta_share(
        final, baseline, current_scale=1, baseline_scale=1 / 7, target=EMEA_ENTERPRISE
    )
    assert share_a >= 0.65
    assert share_b >= 0.65


def test_billing_sla_breach_rate_worsens_materially() -> None:
    post = billing(between(dataset().tickets, DEPLOYMENT_AT, WINDOW_END))
    before = rate(billing(PRE_INCIDENT), lambda t: t.sla_breached)
    after = rate(post, lambda t: t.sla_breached)
    assert after >= 0.14
    assert after >= 1.5 * before


def test_billing_escalations_and_negative_sentiment_increase() -> None:
    post = billing(between(dataset().tickets, DEPLOYMENT_AT, WINDOW_END))
    before = billing(PRE_INCIDENT)
    assert rate(post, lambda t: t.escalated) >= 1.5 * rate(before, lambda t: t.escalated)

    def negative(t: TicketRecord) -> bool:
        return t.sentiment_score <= Decimal("-0.3")

    assert rate(post, negative) >= 1.5 * rate(before, negative)


def test_non_billing_queues_do_not_receive_the_planted_spike() -> None:
    tickets = dataset().tickets
    for category in set(TicketCategory) - {TicketCategory.BILLING}:
        subset = [t for t in tickets if t.category is category]
        post = between(subset, DEPLOYMENT_AT, WINDOW_END)
        pre = between(subset, DEPLOYMENT_AT - timedelta(days=7), DEPLOYMENT_AT)
        hours = (WINDOW_END - DEPLOYMENT_AT).total_seconds() / 3600
        assert (len(post) / hours) / (len(pre) / 168) < 1.25, category
        assert rate(post, lambda t: t.sla_breached) < 0.14, category


# --- generator hygiene ------------------------------------------------------------


def test_assign_refs_numbers_in_creation_order() -> None:
    template = dataset().tickets[0]
    late = replace(template, created_at=template.created_at + timedelta(days=1))
    early = replace(template, created_at=template.created_at)
    numbered = assign_refs([late, early], "X-")
    assert [t.ticket_ref for t in numbered] == ["X-000001", "X-000002"]
    assert numbered[0].created_at < numbered[1].created_at


def test_duplicate_ticket_refs_are_detected(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.services.demo_data.generator as module

    monkeypatch.setattr(module, "replace", lambda ticket, **_: replace(ticket, ticket_ref="DUP"))
    with pytest.raises(TicketRefCollisionError, match="DUP"):
        assign_refs(dataset().tickets[:2], "X-")


@pytest.mark.parametrize("module_name", ["config", "generator", "records"])
def test_generator_modules_never_read_the_wall_clock(module_name: str) -> None:
    source = Path(demo_data_package.__file__).parent.joinpath(f"{module_name}.py").read_text()
    for forbidden in (".now(", ".today(", "utcnow", "time.time(", "import time\n"):
        assert forbidden not in source, f"{module_name}.py uses {forbidden!r}"
