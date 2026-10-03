"""Count and rate contribution formulas, ranking, and edge cases (pure; no database)."""

from decimal import Decimal

import pytest

from app.services.contributors.formulas import (
    FAMILIES,
    Excluded,
    ExcludeReason,
    FamilyStatus,
    Flag,
    Method,
    SegmentDelta,
    SegmentFacts,
    contribution_pct,
    count_delta,
    display_label,
    parent_baseline_rate,
    rank_segments,
    rate_excess,
    segment_value,
    supports_segmentation,
)
from app.services.metrics.definitions import METRIC_REGISTRY, Dimension

D = Decimal


def seg(value: str) -> dict[Dimension, str]:
    return {Dimension.REGION: value}


def count_facts(value: str, current: int, baseline: str | None) -> SegmentFacts:
    return SegmentFacts(
        segment=seg(value),
        current_events=current,
        current_denominator=None,
        baseline_value=None if baseline is None else D(baseline),
        baseline_numerator=0,
        baseline_denominator=0,
    )


def rate_facts(value: str, events: int, den: int, base_num: int, base_den: int) -> SegmentFacts:
    return SegmentFacts(
        segment=seg(value),
        current_events=events,
        current_denominator=den,
        baseline_value=None,
        baseline_numerator=base_num,
        baseline_denominator=base_den,
    )


def delta_of(value: str, current: int, baseline: str) -> SegmentDelta:
    result = count_delta(count_facts(value, current, baseline))
    assert result is not None
    return result


# --- count metrics -------------------------------------------------------------------


def test_count_delta_is_current_minus_normalised_baseline() -> None:
    result = delta_of("emea", 22, "5")
    assert result.method is Method.COUNT_DELTA
    assert result.delta == D("17")
    assert result.baseline_value == D("5")
    assert result.flags == ()


def test_count_delta_uses_a_fractional_baseline() -> None:
    assert delta_of("emea", 10, "3.428571").delta == D("6.571429")


def test_count_segment_new_in_current_window_is_flagged() -> None:
    for baseline in ("0", None):
        result = count_delta(count_facts("apac", 4, baseline))
        assert result is not None
        assert result.delta == D("4")
        assert result.flags == (Flag.NEW_SEGMENT,)


def test_count_segment_empty_in_both_windows_is_skipped() -> None:
    assert count_delta(count_facts("apac", 0, "0")) is None


def test_count_shares_use_only_positive_deltas_as_denominator() -> None:
    ranking = rank_segments(
        [delta_of("emea", 22, "5"), delta_of("apac", 8, "5"), delta_of("na", 1, "11")],
        min_sample=1,
    )
    assert ranking.positive_total == D("20")
    assert [(r.delta.label, r.contribution_pct) for r in ranking.ranked] == [
        ("emea", D("85")),
        ("apac", D("15")),
    ]  # the -10 segment is not ranked and does not shrink the shares
    assert ranking.other_contribution_pct == D("0")


# --- rate metrics --------------------------------------------------------------------


def test_rate_excess_events_arithmetic() -> None:
    # 40 breaches of 100 tickets today; baseline 70 of 700 (10%) -> expect 10, excess 30.
    result = rate_excess(rate_facts("emea", 40, 100, 70, 700), None)
    assert isinstance(result, SegmentDelta)
    assert result.method is Method.RATE_EXCESS
    assert result.baseline_rate == D("0.1")
    assert result.baseline_value == D("10")  # expected events
    assert result.delta == D("30")
    assert result.sample == 100
    assert result.flags == ()


def test_rate_ranking_follows_excess_events_not_percentage_points() -> None:
    big = rate_excess(rate_facts("emea", 30, 100, 70, 700), None)  # 30% vs 10%: +20 events
    tiny = rate_excess(rate_facts("apac", 5, 10, 7, 700), None)  # 50% vs 1%: +4.9 events
    assert isinstance(big, SegmentDelta) and isinstance(tiny, SegmentDelta)
    ranking = rank_segments([tiny, big], min_sample=10)
    assert [r.delta.label for r in ranking.ranked] == ["emea", "apac"]
    assert ranking.ranked[0].delta.delta == D("20")
    assert ranking.ranked[1].delta.delta == D("4.9")


def test_rate_segment_without_current_records_is_excluded_not_divided() -> None:
    result = rate_excess(rate_facts("emea", 0, 0, 7, 70), D("0.1"))
    assert result == Excluded(seg("emea"), ExcludeReason.ZERO_DENOMINATOR)


def test_rate_segment_empty_in_both_windows_is_skipped() -> None:
    assert rate_excess(rate_facts("emea", 0, 0, 0, 0), D("0.1")) is None


def test_new_rate_segment_borrows_the_parent_rate_and_says_so() -> None:
    result = rate_excess(rate_facts("apac", 12, 50, 0, 0), D("0.1"))
    assert isinstance(result, SegmentDelta)
    assert result.delta == D("7")  # 12 - 50 * 0.1
    assert result.flags == (Flag.NEW_SEGMENT, Flag.BASELINE_FROM_PARENT)


def test_new_rate_segment_without_any_baseline_rate_is_excluded() -> None:
    result = rate_excess(rate_facts("apac", 12, 50, 0, 0), None)
    assert result == Excluded(seg("apac"), ExcludeReason.NO_BASELINE_RATE)


def test_parent_baseline_rate_is_none_for_empty_baseline() -> None:
    assert parent_baseline_rate(0, 0) is None
    assert parent_baseline_rate(7, 70) == D("0.1")


# --- ranking -------------------------------------------------------------------------


def test_no_positive_contributors_reports_status_and_never_divides() -> None:
    ranking = rank_segments([delta_of("emea", 3, "5"), delta_of("apac", 5, "5")], min_sample=1)
    assert ranking.status is FamilyStatus.NO_POSITIVE_CONTRIBUTORS
    assert ranking.ranked == ()
    assert ranking.positive_total == D("0")
    assert contribution_pct(D("1"), D("0")) is None


def test_empty_family_has_no_positive_contributors() -> None:
    assert rank_segments([], min_sample=1).status is FamilyStatus.NO_POSITIVE_CONTRIBUTORS


def test_top_n_truncation_exposes_the_remainder_as_other() -> None:
    deltas = [delta_of(f"s{n}", 10 + n, "10") for n in range(1, 8)]  # +1 .. +7, total 28
    ranking = rank_segments(deltas, min_sample=1, top_n=5)
    assert [r.rank for r in ranking.ranked] == [1, 2, 3, 4, 5]
    assert [r.delta.label for r in ranking.ranked] == ["s7", "s6", "s5", "s4", "s3"]
    ranked_sum = sum(r.contribution_pct for r in ranking.ranked)
    assert ranking.other_contribution_pct == D("100") - ranked_sum
    assert ranking.other_contribution_pct > 0


def test_default_top_n_is_five() -> None:
    deltas = [delta_of(f"s{n}", 10 + n, "10") for n in range(1, 8)]
    assert len(rank_segments(deltas, min_sample=1).ranked) == 5


def test_equal_deltas_rank_deterministically_by_segment_key() -> None:
    deltas = [delta_of("b", 15, "10"), delta_of("c", 15, "10"), delta_of("a", 15, "10")]
    first = rank_segments(deltas, min_sample=1)
    second = rank_segments(list(reversed(deltas)), min_sample=1)
    assert [r.delta.label for r in first.ranked] == ["a", "b", "c"]
    assert first == second


def test_segments_below_minimum_sample_are_suppressed_but_still_in_the_denominator() -> None:
    big = delta_of("emea", 25, "5")  # +20, sample 25
    small = delta_of("apac", 4, "0.5")  # +3.5, sample 4 < 5
    ranking = rank_segments([big, small], min_sample=5)
    assert [r.delta.label for r in ranking.ranked] == ["emea"]
    assert [d.label for d in ranking.suppressed] == ["apac"]
    assert ranking.positive_total == D("23.5")
    assert ranking.suppressed_contribution_pct == contribution_pct(D("3.5"), D("23.5"))
    assert ranking.other_contribution_pct == ranking.suppressed_contribution_pct + (
        D("100") - ranking.ranked[0].contribution_pct - ranking.suppressed_contribution_pct
    )


def test_only_suppressed_positives_leave_nothing_ranked() -> None:
    ranking = rank_segments([delta_of("apac", 4, "0")], min_sample=5)
    assert ranking.status is FamilyStatus.NO_POSITIVE_CONTRIBUTORS
    assert ranking.ranked == ()
    assert ranking.suppressed_contribution_pct == D("100")


def test_contribution_is_reproducible_from_the_stored_delta_and_total() -> None:
    result = rank_segments(
        [delta_of("emea", 22, "3.428571"), delta_of("apac", 9, "3.428571")], min_sample=1
    )
    for ranked in result.ranked:
        assert ranked.contribution_pct == contribution_pct(
            ranked.delta.delta, result.positive_total
        )


# --- registry ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("metric_key", "supported"),
    [
        ("ticket_volume", True),
        ("open_backlog", True),
        ("p1_ticket_volume", True),
        ("sla_breach_rate", True),
        ("escalation_rate", True),
        ("negative_sentiment_rate", True),
        ("first_response_minutes", False),
        ("resolution_minutes", False),
    ],
)
def test_only_additive_metrics_support_segmentation(metric_key: str, supported: bool) -> None:
    assert supports_segmentation(METRIC_REGISTRY[metric_key]) is supported


def test_families_cover_the_documented_dimensions_and_the_canonical_combination() -> None:
    keys = {family.key for family in FAMILIES}
    assert keys == {
        "region",
        "customer_tier",
        "category",
        "product",
        "support_team",
        "region+customer_tier",
    }
    combo = next(f for f in FAMILIES if f.key == "region+customer_tier")
    assert combo.dimensions == (Dimension.REGION, Dimension.CUSTOMER_TIER)


def test_segment_keys_and_labels_follow_family_dimension_order() -> None:
    segment = {Dimension.REGION: "emea", Dimension.CUSTOMER_TIER: "enterprise"}
    assert segment_value(segment) == "emea|enterprise"
    assert display_label(segment) == "EMEA / Enterprise"
    assert display_label({Dimension.REGION: "north_america"}) == "North America"
