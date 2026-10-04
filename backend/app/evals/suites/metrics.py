"""Metric correctness: hand-computed fixtures through the production metric engine."""

from datetime import UTC, datetime
from decimal import Decimal
from functools import partial

from app.evals.cases import MetricFixtureCase, load_metric_fixtures
from app.evals.context import EvalContext
from app.evals.results import guarded, verdict
from app.schemas.evaluations import CaseResult, EvalCategory
from app.services.metrics.definitions import METRIC_REGISTRY
from app.services.metrics.engine import analysis_window, compute_metric

CATEGORY = EvalCategory.METRIC_CORRECTNESS
# Fixtures are pure arithmetic; the window only labels the buckets.
FIXTURE_WINDOW_END = datetime(2026, 1, 9, tzinfo=UTC)


def _fmt(value: Decimal | None) -> str:
    return "null" if value is None else format(value.normalize(), "f")


def _equal(observed: Decimal | None, expected: Decimal | None) -> bool:
    if observed is None or expected is None:
        return observed is expected
    return observed == expected


def _check(case: MetricFixtureCase) -> CaseResult:
    window = analysis_window(FIXTURE_WINDOW_END)
    result = compute_metric(METRIC_REGISTRY[case.metric_key], window, {}, case.buckets())
    exp = case.expected
    fields = {
        "value": (result.current.value, exp.value),
        "baseline_value": (result.baseline_value, exp.baseline_value),
        "change_pct": (result.change_pct, exp.change_pct),
    }
    mismatches = [
        f"{name}: expected {_fmt(want)}, got {_fmt(got)}"
        for name, (got, want) in fields.items()
        if not _equal(got, want)
    ]
    if result.baseline_zero is not exp.baseline_zero:
        mismatches.append(
            f"baseline_zero: expected {exp.baseline_zero}, got {result.baseline_zero}"
        )
    observed = ", ".join(
        [f"{name}={_fmt(got)}" for name, (got, _) in fields.items()]
        + [f"baseline_zero={result.baseline_zero}"]
    )
    expected = ", ".join(
        [f"{name}={_fmt(want)}" for name, (_, want) in fields.items()]
        + [f"baseline_zero={exp.baseline_zero}"]
    )
    return verdict(
        case.case_id,
        case.title,
        CATEGORY,
        passed=not mismatches,
        expected=expected,
        observed=observed,
        failure_reason="; ".join(mismatches),
    )


def run(ctx: EvalContext) -> list[CaseResult]:
    fixtures = load_metric_fixtures(ctx.cases_dir)
    return [
        guarded(c.case_id, c.title, CATEGORY, "fixture values match", partial(_check, c))
        for c in fixtures.cases
    ]
