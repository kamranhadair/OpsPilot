"""Pure detector behaviour: boundaries, guards, direction, z-score, determinism."""

from collections.abc import Sequence
from decimal import Decimal

import pytest

from app.models.enums import AnomalySeverity
from app.services.anomalies.detector import (
    Detection,
    DetectionInput,
    Skip,
    SkipReason,
    compute_z_score,
    detect,
    explain,
)
from app.services.metrics.definitions import Direction

D = Decimal
STEADY = [100.0, 102.0, 98.0, 101.0, 99.0, 103.0, 97.0]


def pct_input(
    change_pct: str,
    *,
    key: str = "ticket_volume",
    baseline: str = "100",
    direction: Direction = Direction.HIGHER_IS_WORSE,
    daily: Sequence[float | None] = tuple(STEADY),
) -> DetectionInput:
    base = D(baseline)
    pct = D(change_pct)
    value = base * (1 + pct / 100)
    return DetectionInput(
        metric_key=key,
        direction=direction,
        value=value,
        baseline_value=base,
        change_pct=pct,
        baseline_zero=False,
        current_sample_size=int(value),
        baseline_sample_size=int(base) * 7,
        daily_baseline_values=daily,
    )


def pp_input(
    pp: str,
    *,
    key: str = "sla_breach_rate",
    baseline: str = "8",
    current_n: int = 100,
    baseline_n: int = 700,
    baseline_zero: bool = False,
) -> DetectionInput:
    base = D(baseline)
    value = base + D(pp)
    return DetectionInput(
        metric_key=key,
        direction=Direction.HIGHER_IS_WORSE,
        value=value,
        baseline_value=base,
        change_pct=None if base == 0 else (value - base) / base * 100,
        baseline_zero=baseline_zero,
        current_sample_size=current_n,
        baseline_sample_size=baseline_n,
        daily_baseline_values=STEADY,
    )


def detected(result: Detection | Skip) -> Detection:
    assert isinstance(result, Detection), result
    return result


def skipped(result: Detection | Skip) -> Skip:
    assert isinstance(result, Skip), result
    return result


# --- relative percentage thresholds -------------------------------------------------


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        ("29.99", None),
        ("30", AnomalySeverity.MEDIUM),
        ("49.99", AnomalySeverity.MEDIUM),
        ("50", AnomalySeverity.HIGH),
        ("400", AnomalySeverity.HIGH),
    ],
)
def test_percentage_boundaries(change: str, expected: AnomalySeverity | None) -> None:
    result = detect(pct_input(change))
    if expected is None:
        assert skipped(result).reason is SkipReason.BELOW_THRESHOLD
    else:
        assert detected(result).severity is expected


@pytest.mark.parametrize("key", ["ticket_volume", "open_backlog"])
def test_count_rules_share_thresholds(key: str) -> None:
    assert detected(detect(pct_input("50", key=key))).severity is AnomalySeverity.HIGH


# --- percentage-point thresholds ----------------------------------------------------


@pytest.mark.parametrize(
    ("key", "pp", "expected"),
    [
        ("sla_breach_rate", "2.99", None),
        ("sla_breach_rate", "3", AnomalySeverity.MEDIUM),
        ("sla_breach_rate", "4.99", AnomalySeverity.MEDIUM),
        ("sla_breach_rate", "5", AnomalySeverity.HIGH),
        ("escalation_rate", "1.99", None),
        ("escalation_rate", "2", AnomalySeverity.MEDIUM),
        ("escalation_rate", "3.99", AnomalySeverity.MEDIUM),
        ("escalation_rate", "4", AnomalySeverity.HIGH),
        ("negative_sentiment_rate", "4.99", None),
        ("negative_sentiment_rate", "5", AnomalySeverity.MEDIUM),
        ("negative_sentiment_rate", "9.99", AnomalySeverity.MEDIUM),
        ("negative_sentiment_rate", "10", AnomalySeverity.HIGH),
    ],
)
def test_percentage_point_boundaries(key: str, pp: str, expected: AnomalySeverity | None) -> None:
    result = detect(pp_input(pp, key=key))
    if expected is None:
        assert skipped(result).reason is SkipReason.BELOW_THRESHOLD
    else:
        assert detected(result).severity is expected


def test_rate_with_zero_baseline_still_uses_percentage_points() -> None:
    result = detect(pp_input("6", baseline="0", baseline_zero=True))
    assert detected(result).severity is AnomalySeverity.HIGH


# --- direction ----------------------------------------------------------------------


@pytest.mark.parametrize("change", ["-60", "-5"])
def test_improvement_is_not_an_anomaly(change: str) -> None:
    assert skipped(detect(pct_input(change))).reason is SkipReason.IMPROVEMENT


def test_rate_improvement_is_not_an_anomaly() -> None:
    assert skipped(detect(pp_input("-6"))).reason is SkipReason.IMPROVEMENT


def test_higher_is_better_flags_a_fall() -> None:
    result = detect(pct_input("-60", direction=Direction.HIGHER_IS_BETTER))
    assert detected(result).severity is AnomalySeverity.HIGH
    assert skipped(detect(pct_input("60", direction=Direction.HIGHER_IS_BETTER))).reason is (
        SkipReason.IMPROVEMENT
    )


# --- missing baseline / not configured ----------------------------------------------


def test_missing_baseline_is_skipped() -> None:
    data = DetectionInput(
        metric_key="ticket_volume",
        direction=Direction.HIGHER_IS_WORSE,
        value=D(50),
        baseline_value=None,
        change_pct=None,
        baseline_zero=False,
        current_sample_size=50,
        baseline_sample_size=0,
        daily_baseline_values=[None] * 7,
    )
    assert skipped(detect(data)).reason is SkipReason.BASELINE_MISSING


def test_zero_baseline_has_no_percentage_change() -> None:
    data = DetectionInput(
        metric_key="ticket_volume",
        direction=Direction.HIGHER_IS_WORSE,
        value=D(50),
        baseline_value=D(0),
        change_pct=None,
        baseline_zero=True,
        current_sample_size=50,
        baseline_sample_size=0,
        daily_baseline_values=[0.0] * 7,
    )
    assert skipped(detect(data)).reason is SkipReason.BASELINE_ZERO


@pytest.mark.parametrize("key", ["first_response_minutes", "resolution_minutes", "csat"])
def test_unconfigured_metric_is_skipped(key: str) -> None:
    assert skipped(detect(pct_input("500", key=key))).reason is SkipReason.NOT_CONFIGURED


# --- small-sample guards ------------------------------------------------------------


def test_tiny_baseline_cannot_explode_into_an_anomaly() -> None:
    # 3 -> 9 tickets is +200% but baseline < 10 and delta < 10.
    result = detect(pct_input("200", baseline="3"))
    assert skipped(result).reason is SkipReason.INSUFFICIENT_SAMPLE


def test_small_absolute_delta_is_guarded_even_with_a_big_baseline() -> None:
    # 10 -> 14 is +40% (above medium) but only 4 tickets.
    result = detect(pct_input("40", baseline="10"))
    assert skipped(result).reason is SkipReason.INSUFFICIENT_SAMPLE


def test_rate_needs_enough_current_samples() -> None:
    result = detect(pp_input("8", current_n=29))
    skip = skipped(result)
    assert skip.reason is SkipReason.INSUFFICIENT_SAMPLE
    assert skip.detail is not None and "min_current_sample" in skip.detail
    assert detected(detect(pp_input("8", current_n=30))).severity is not None


def test_rate_needs_enough_baseline_samples() -> None:
    assert skipped(detect(pp_input("8", baseline_n=69))).reason is SkipReason.INSUFFICIENT_SAMPLE
    assert detected(detect(pp_input("8", baseline_n=70))).severity is not None


def test_below_threshold_wins_over_sample_guards() -> None:
    assert skipped(detect(pp_input("1", current_n=3))).reason is SkipReason.BELOW_THRESHOLD


# --- critical severity --------------------------------------------------------------


def test_sla_critical_needs_the_policy_level_not_just_a_big_change() -> None:
    # +5pp is high; rate 13% is below the 25% critical condition.
    assert detected(detect(pp_input("5"))).severity is AnomalySeverity.HIGH
    # 8% -> 33% crosses the 25% condition.
    result = detected(detect(pp_input("25")))
    assert result.severity is AnomalySeverity.CRITICAL
    assert result.threshold.critical is not None and result.threshold.critical.met


def test_p1_percentage_alone_is_never_critical() -> None:
    # +1000% on a tiny sample: 1 -> 11 is high (>=5 current, delta>=3) but 11 < 12 P1s.
    data = pct_input("1000", key="p1_ticket_volume", baseline="1")
    result = detected(detect(data))
    assert result.severity is AnomalySeverity.HIGH
    assert result.threshold.critical is not None and not result.threshold.critical.met


def test_p1_critical_when_absolute_level_is_reached() -> None:
    data = pct_input("200", key="p1_ticket_volume", baseline="4")  # 4 -> 12
    assert detected(detect(data)).severity is AnomalySeverity.CRITICAL


def test_medium_never_becomes_critical() -> None:
    data = pct_input("40", key="p1_ticket_volume", baseline="30")  # 30 -> 42 P1s
    result = detected(detect(data))
    assert result.severity is AnomalySeverity.MEDIUM
    assert result.threshold.critical is not None and not result.threshold.critical.met


def test_p1_small_counts_are_guarded() -> None:
    # 1 -> 4: current < 5 despite +300%.
    data = pct_input("300", key="p1_ticket_volume", baseline="1")
    assert skipped(detect(data)).reason is SkipReason.INSUFFICIENT_SAMPLE


# --- z-score ------------------------------------------------------------------------


def test_zero_standard_deviation_makes_z_score_unavailable() -> None:
    z = compute_z_score(D(150), [100.0] * 7)
    assert not z.available
    assert z.value is None
    assert z.unavailable_reason == "zero_stdev"


def test_fewer_than_seven_days_makes_z_score_unavailable() -> None:
    z = compute_z_score(D(150), [100.0, 101.0, 99.0, 100.0, 102.0, None, None])
    assert not z.available
    assert z.unavailable_reason == "insufficient_history"
    assert z.sample_count == 5


def test_z_score_value() -> None:
    z = compute_z_score(D(150), STEADY)
    assert z.available and z.value is not None
    mean = sum(STEADY) / 7
    stdev = (sum((v - mean) ** 2 for v in STEADY) / 6) ** 0.5
    assert z.value == pytest.approx((150 - mean) / stdev, abs=1e-5)


def test_detection_with_zero_stdev_still_detects() -> None:
    result = detected(detect(pct_input("80", daily=[100.0] * 7)))
    assert result.severity is AnomalySeverity.HIGH
    assert not result.threshold.z_score.available


def test_z_score_never_changes_severity() -> None:
    steady = detected(detect(pct_input("80", daily=STEADY)))
    noisy = detected(detect(pct_input("80", daily=[10.0, 200.0, 30.0, 180.0, 60.0, 150.0, 90.0])))
    flat = detected(detect(pct_input("80", daily=[100.0] * 7)))
    assert steady.severity is noisy.severity is flat.severity is AnomalySeverity.HIGH


# --- determinism and explanation ----------------------------------------------------


def test_severity_is_deterministic() -> None:
    data = pct_input("62.5")
    first = detect(data)
    assert all(detect(data) == first for _ in range(10))


def test_threshold_explains_the_triggering_rule() -> None:
    result = detected(detect(pct_input("80")))
    t = result.threshold
    assert t.detector_key == "pct_change.v1"
    assert t.metric_key == "ticket_volume"
    assert t.triggered_tier == "high"
    assert (t.medium_threshold, t.high_threshold) == (30.0, 50.0)
    assert t.observed == pytest.approx(80.0)
    assert {g.name for g in t.guards} == {"min_baseline_value", "min_abs_delta"}
    assert all(g.passed for g in t.guards)
    assert result.score == D("80")

    text = explain(result.severity, t, "Ticket volume")
    assert "+80.00%" in text
    assert "high threshold of 50%" in text
    assert "pct_change.v1" in text


def test_critical_explanation_names_the_business_condition() -> None:
    result = detected(detect(pp_input("25")))
    text = explain(result.severity, result.threshold, "SLA breach rate")
    assert "critical" in text
    assert "25%" in text
