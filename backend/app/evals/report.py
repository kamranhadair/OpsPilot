"""Aggregate case results into the evaluation report and render its Markdown companion.

Aggregation is deliberately conservative: an unexecuted case lowers nothing and raises
nothing; a rate over zero executed cases is ``None``; any failure or error makes the
run ``fail``; any not-run deterministic/AI case makes a non-failing run ``incomplete``.
Model-based results are never folded into these totals.
"""

import uuid
from collections.abc import Sequence
from datetime import datetime

from app.schemas.evaluations import (
    STATISTICAL_NOTE,
    CaseResult,
    CategorySummary,
    CountMetric,
    EvalCategory,
    EvaluationReport,
    ModelBasedSection,
    OverallStatus,
    RatioMetric,
    ReplaySummary,
    SeedInfo,
    SuiteName,
)


def _ratio(numerator: int, denominator: int) -> float | None:
    return None if denominator == 0 else numerator / denominator


def summarize(cases: Sequence[CaseResult]) -> list[CategorySummary]:
    """One summary per category, in a stable order, including empty categories."""
    summaries = []
    for category in EvalCategory:
        group = [c for c in cases if c.category is category]
        passed = sum(c.status == "pass" for c in group)
        failed = sum(c.status == "fail" for c in group)
        errored = sum(c.status == "error" for c in group)
        summaries.append(
            CategorySummary(
                category=category,
                total=len(group),
                passed=passed,
                failed=failed,
                errored=errored,
                not_run=sum(c.status == "not_run" for c in group),
                pass_rate=_ratio(passed, passed + failed + errored),
            )
        )
    return summaries


_RATE_LABELS: tuple[tuple[str, str, EvalCategory, str], ...] = (
    (
        "metric_fixture_pass_rate",
        "Metric fixture pass rate",
        EvalCategory.METRIC_CORRECTNESS,
        "Hand-computed metric fixtures reproduced exactly by the metric engine.",
    ),
    (
        "planted_anomaly_recall",
        "Planted anomaly recall",
        EvalCategory.ANOMALY_DETECTION,
        "Planted demo anomalies detected at the expected severity.",
    ),
    (
        "contributor_top_k_hit_rate",
        "Contributor top-k hit rate",
        EvalCategory.CONTRIBUTOR_ATTRIBUTION,
        "Expected segment ranked within the top k of its contributor family.",
    ),
    (
        "citation_validity_rate",
        "Citation ID validity checks",
        EvalCategory.CITATION_VALIDITY,
        "Citation cases where the validator accepted real IDs and rejected fabricated or "
        "unresolved ones as expected.",
    ),
    (
        "action_grounding_pass_rate",
        "Action grounding pass rate",
        EvalCategory.ACTION_GROUNDING,
        "Action proposals accepted or rejected by the grounding policy as expected.",
    ),
    (
        "approval_boundary_pass_rate",
        "Approval boundary pass rate",
        EvalCategory.APPROVAL_BOUNDARY,
        "Execution/approval bypass attempts refused and approved actions executed once.",
    ),
)


def build_metrics(
    cases: Sequence[CaseResult], summaries: Sequence[CategorySummary]
) -> tuple[list[RatioMetric], list[CountMetric]]:
    by_category = {s.category: s for s in summaries}
    ratios = []
    for key, label, category, description in _RATE_LABELS:
        s = by_category[category]
        executed = s.passed + s.failed + s.errored
        ratios.append(
            RatioMetric(
                key=key,
                label=label,
                numerator=s.passed,
                denominator=executed,
                value=_ratio(s.passed, executed),
                description=description,
            )
        )

    normal = [
        c
        for c in cases
        if c.category is EvalCategory.FALSE_POSITIVE and c.status != "not_run" and c.tally
    ]
    flagged = sum(c.tally.flagged for c in normal if c.tally)
    checked = sum(c.tally.checked for c in normal if c.tally)
    ratios.insert(
        2,
        RatioMetric(
            key="high_critical_false_positive_rate",
            label="High/critical false positives on normal cases",
            numerator=flagged,
            denominator=checked,
            value=_ratio(flagged, checked),
            description="High/critical anomalies among metrics checked on designated normal "
            "queue/days. Lower is better; the numerator is the false-positive count.",
        ),
    )

    causal = by_category[EvalCategory.CAUSAL_GUARDRAIL]
    counts = [
        CountMetric(
            key="causation_guard",
            label="Runtime causation guard",
            passed=causal.passed,
            failed=causal.failed,
            errored=causal.errored,
            not_run=causal.not_run,
            description="Causal wording rejected and cautious correlation wording accepted.",
        )
    ]
    return ratios, counts


def overall_status(cases: Sequence[CaseResult], replay: ReplaySummary | None) -> OverallStatus:
    if any(c.status in {"fail", "error"} for c in cases):
        return "fail"
    if replay is not None and replay.status == "error":
        return "fail"
    executed = [c for c in cases if c.status == "pass"]
    if not executed or any(c.status == "not_run" for c in cases):
        return "incomplete"
    if replay is not None and replay.status != "completed":
        return "incomplete"
    return "pass"


def build_report(
    *,
    suite: SuiteName,
    generated_at: datetime,
    seed: SeedInfo,
    cases: Sequence[CaseResult],
    replay: ReplaySummary | None,
    model_based: ModelBasedSection,
    notes: Sequence[str] = (),
) -> EvaluationReport:
    summaries = summarize(cases)
    ratios, counts = build_metrics(cases, summaries)
    partial = (
        any(c.status == "error" for c in cases)
        or (replay is not None and replay.status == "error")
        or model_based.status == "error"
        or any(c.status == "error" for c in model_based.cases)
    )
    return EvaluationReport(
        run_id=str(uuid.uuid4()),
        suite=suite,
        generated_at=generated_at,
        overall_status=overall_status(cases, replay),
        partial_failure=partial,
        seed=seed,
        cases=list(cases),
        categories=summaries,
        ratios=ratios,
        counts=counts,
        replay=replay,
        model_based=model_based,
        notes=[STATISTICAL_NOTE, *notes],
    )


def _slice(filters: dict[str, str]) -> str:
    return ", ".join(filters.values()) or "overall"


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.1f}%"


def render_markdown(report: EvaluationReport) -> str:
    """Human-readable companion: failures first, then the summary tables."""
    lines = [
        "# OpsPilot evaluation report",
        "",
        f"- Suite: `{report.suite}` — overall **{report.overall_status.upper()}**"
        + (" (partial failure)" if report.partial_failure else ""),
        f"- Generated: {report.generated_at.isoformat()} — run `{report.run_id}`",
        f"- Seed: expected `{report.seed.expected_version}`, database "
        f"{report.seed.observed_state} (`{report.seed.observed_version}`)",
        "",
        "## Failed or errored cases",
        "",
    ]
    bad = [c for c in report.cases if c.status in {"fail", "error"}]
    if not bad:
        lines.append("None.")
    for c in bad:
        lines += [
            f"### {c.case_id} — {c.status.upper()}",
            f"- Category: {c.category.value}",
            f"- Expected: {c.expected}",
            f"- Observed: {c.observed or '—'}",
            f"- Reason: {c.failure_reason or '—'}",
            "",
        ]
    skipped = [c for c in report.cases if c.status == "not_run"]
    if skipped:
        lines += ["", "## Not run", ""]
        lines += [f"- {c.case_id}: {c.failure_reason}" for c in skipped]
    lines += ["", "## Metrics", "", "| Metric | Value | n |", "|---|---|---|"]
    lines += [
        f"| {r.label} | {_pct(r.value)} | {r.numerator}/{r.denominator} |" for r in report.ratios
    ]
    lines += [
        f"| {c.label} | {c.passed} pass / {c.failed} fail / {c.errored} error | "
        f"{c.not_run} not run |"
        for c in report.counts
    ]
    lines += ["", "## Categories", "", "| Category | Pass | Fail | Error | Not run |"]
    lines += ["|---|---|---|---|---|"]
    lines += [
        f"| {s.category.value} | {s.passed} | {s.failed} | {s.errored} | {s.not_run} |"
        for s in report.categories
    ]
    if report.replay is not None:
        lines += ["", f"## Replay ({report.replay.status})", ""]
        if report.replay.reason:
            lines.append(f"Reason: {report.replay.reason}")
        for day in report.replay.days:
            flagged = ", ".join(
                f"{a.display_name} [{_slice(a.filters)}] {a.severity.value}" for a in day.anomalies
            )
            lines.append(
                f"- {day.window_start.date()}: {day.status}"
                + (f" — {flagged}" if flagged else (f" — {day.detail}" if day.detail else ""))
            )
    mb = report.model_based
    lines += ["", "## Model-based (non-deterministic, reported separately)", ""]
    lines.append(f"Status: **{mb.status.upper()}**" + (f" — {mb.reason}" if mb.reason else ""))
    if mb.model_name:
        lines.append(f"Model: `{mb.model_name}`, prompt `{mb.prompt_version}`")
    lines += [f"- {c.case_id}: {c.status} — {c.observed or c.failure_reason}" for c in mb.cases]
    lines += ["", "## Notes", ""] + [f"- {n}" for n in report.notes]
    return "\n".join(lines) + "\n"
