"""The reporting layer itself, on tiny fixtures, so it can never falsely show green."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.evals.report import build_report, render_markdown
from app.evals.store import EvaluationReportInvalidError, read_latest, write_report
from app.schemas.evaluations import (
    CaseResult,
    CaseTally,
    EvalCategory,
    EvaluationReport,
    ModelBasedSection,
    ReplaySummary,
    SeedInfo,
)

NOW = datetime(2026, 10, 4, 6, tzinfo=UTC)
SEED = SeedInfo(
    expected_version="1",
    case_version="1",
    observed_state="complete",
    observed_version="1",
    matches=True,
)
MODEL_NOT_RUN = ModelBasedSection(status="not_run", reason="disabled")


def case(
    status: str, category: EvalCategory = EvalCategory.METRIC_CORRECTNESS, **kw: object
) -> CaseResult:
    return CaseResult.model_validate(
        {
            "case_id": f"c.{status}.{category.value}.{kw.pop('n', 0)}",
            "title": "t",
            "category": category,
            "status": status,
            "expected": "e",
            **kw,
        }
    )


def report(*cases: CaseResult, **kw: object) -> EvaluationReport:
    values: dict[str, object] = {
        "suite": "all",
        "generated_at": NOW,
        "seed": SEED,
        "cases": list(cases),
        "replay": None,
        "model_based": MODEL_NOT_RUN,
        **kw,
    }
    return build_report(**values)  # type: ignore[arg-type]


def ratio(r: EvaluationReport, key: str) -> tuple[int, int, float | None]:
    item = next(x for x in r.ratios if x.key == key)
    return item.numerator, item.denominator, item.value


def test_all_not_run_is_incomplete_with_null_rates() -> None:
    r = report(case("not_run", failure_reason="seed_missing"))
    assert r.overall_status == "incomplete"
    assert ratio(r, "metric_fixture_pass_rate") == (0, 0, None)
    metric_summary = next(s for s in r.categories if s.category is EvalCategory.METRIC_CORRECTNESS)
    assert metric_summary.pass_rate is None and metric_summary.not_run == 1


def test_empty_run_is_never_a_pass() -> None:
    assert report().overall_status == "incomplete"


def test_one_failure_fails_the_run_and_counts_against_the_rate() -> None:
    r = report(case("pass", n=1), case("fail", n=2))
    assert r.overall_status == "fail"
    assert ratio(r, "metric_fixture_pass_rate") == (1, 2, 0.5)
    assert not r.partial_failure


def test_error_is_a_partial_failure_and_counts_against_the_rate() -> None:
    r = report(case("pass", n=1), case("error", n=2))
    assert r.overall_status == "fail" and r.partial_failure
    assert ratio(r, "metric_fixture_pass_rate") == (1, 2, 0.5)


def test_mixed_pass_and_not_run_is_incomplete() -> None:
    r = report(case("pass", n=1), case("not_run", n=2))
    assert r.overall_status == "incomplete"
    assert ratio(r, "metric_fixture_pass_rate") == (1, 1, 1.0)


def test_all_pass_with_completed_replay_passes() -> None:
    replay = ReplaySummary(status="completed", days_requested=7)
    assert report(case("pass"), replay=replay).overall_status == "pass"


def test_replay_error_fails_and_not_run_replay_is_incomplete() -> None:
    errored = ReplaySummary(status="error", reason="boom", days_requested=7)
    r = report(case("pass"), replay=errored)
    assert r.overall_status == "fail" and r.partial_failure
    skipped = ReplaySummary(status="not_run", reason="db", days_requested=7)
    assert report(case("pass"), replay=skipped).overall_status == "incomplete"


def test_false_positive_rate_sums_tallies_and_skips_not_run() -> None:
    fp = EvalCategory.FALSE_POSITIVE
    r = report(
        case("fail", fp, n=1, tally=CaseTally(flagged=2, checked=10)),
        case("pass", fp, n=2, tally=CaseTally(flagged=0, checked=6)),
        case("not_run", fp, n=3),
    )
    assert ratio(r, "high_critical_false_positive_rate") == (2, 16, 0.125)


def test_no_false_positive_checks_is_null_not_zero() -> None:
    r = report(case("not_run", EvalCategory.FALSE_POSITIVE))
    assert ratio(r, "high_critical_false_positive_rate") == (0, 0, None)


def test_model_based_results_never_enter_deterministic_totals() -> None:
    judged = ModelBasedSection(
        status="completed",
        model_name="m",
        prompt_version="p",
        cases=[case("pass", EvalCategory.CITATION_VALIDITY, n=9)],
    )
    r = report(case("fail", EvalCategory.CITATION_VALIDITY), model_based=judged)
    assert ratio(r, "citation_validity_rate") == (0, 1, 0.0)
    assert r.overall_status == "fail"


def test_model_error_marks_partial_failure_only() -> None:
    errored = ModelBasedSection(status="error", reason="every judge call failed")
    r = report(case("pass"), model_based=errored)
    assert r.partial_failure and r.overall_status == "pass"


def test_causation_guard_count() -> None:
    c = EvalCategory.CAUSAL_GUARDRAIL
    r = report(case("pass", c, n=1), case("fail", c, n=2), case("not_run", c, n=3))
    (guard,) = r.counts
    assert (guard.passed, guard.failed, guard.errored, guard.not_run) == (1, 1, 0, 1)


def test_markdown_lists_failures_first_and_labels_model_section() -> None:
    r = report(case("pass", n=1), case("fail", n=2, failure_reason="value mismatch"))
    text = render_markdown(r)
    assert text.index("## Failed or errored cases") < text.index("## Metrics")
    assert "value mismatch" in text
    assert "Model-based (non-deterministic" in text and "NOT_RUN" in text


def test_round_trip_and_store(tmp_path: Path) -> None:
    r = report(case("pass"))
    paths = write_report(tmp_path, r, render_markdown(r))
    assert [p.name for p in paths] == ["latest.json", "latest.md"]
    assert read_latest(tmp_path) == r
    assert not list(tmp_path.glob(".*.tmp"))


def test_store_missing_and_corrupt(tmp_path: Path) -> None:
    assert read_latest(tmp_path) is None
    (tmp_path / "latest.json").write_text("{not json")
    with pytest.raises(EvaluationReportInvalidError):
        read_latest(tmp_path)
    (tmp_path / "latest.json").write_text('{"schema_version": 99}')
    with pytest.raises(EvaluationReportInvalidError):
        read_latest(tmp_path)
