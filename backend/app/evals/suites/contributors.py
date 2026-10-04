"""Contributor attribution: expected segment within the top-k of a contributor family."""

from functools import partial

from sqlalchemy.orm import Session

from app.evals.cases import ContributorCase, load_contributor_golden
from app.evals.context import EvalContext, seed_gate
from app.evals.results import guarded, not_run, verdict
from app.models import MetricSnapshot
from app.repositories.contributor_repository import ContributorRepository
from app.schemas.evaluations import CaseResult, EvalCategory
from app.services.contributors.engine import analyze
from app.services.contributors.formulas import display_label
from app.services.metrics.engine import analysis_window, to_utc

CATEGORY = EvalCategory.CONTRIBUTOR_ATTRIBUTION


def _transient_snapshot(case: ContributorCase) -> MetricSnapshot:
    """An unsaved snapshot carrying only what ``analyze`` reads; never added to a session."""
    window = analysis_window(to_utc(case.window_end))
    return MetricSnapshot(
        evidence_id="EVAL-TRANSIENT",
        metric_key=case.metric_key,
        window_start=window.current.start,
        window_end=window.current.end,
        baseline_start=window.baseline.start,
        baseline_end=window.baseline.end,
        dimensions_json=dict(case.filters),
    )


def _check(case: ContributorCase, session: Session, team_keys: list[str]) -> CaseResult:
    expected_label = " / ".join(case.expected_segment.values())
    expected = f"{expected_label} within top {case.top_k} of {case.family_key}"
    analysis = analyze(session, _transient_snapshot(case), team_keys)
    family = next(f for f in analysis.families if f.family.key == case.family_key)
    top = list(family.ranking.ranked[: case.top_k])
    segments = [{str(k): v for k, v in r.delta.segment.items()} for r in top]
    observed = (
        ", ".join(
            f"#{r.rank} {display_label(r.delta.segment)} ({r.contribution_pct.normalize():f}%)"
            for r in top
        )
        or f"no ranked contributors ({family.ranking.status.value})"
    )
    return verdict(
        case.case_id,
        case.title,
        CATEGORY,
        passed=case.expected_segment in segments,
        expected=expected,
        observed=observed,
        failure_reason=f"Expected segment not in top {case.top_k}: {observed}",
    )


def run(ctx: EvalContext) -> list[CaseResult]:
    golden = load_contributor_golden(ctx.cases_dir)
    expected = "expected segment in top-k"
    reason = seed_gate(ctx, golden.seed_version)
    session = ctx.session
    if reason is not None or session is None:
        why = reason or "database_unavailable"
        return [not_run(c.case_id, c.title, CATEGORY, expected, why) for c in golden.cases]
    team_keys = ContributorRepository(session).support_team_keys()
    return [
        guarded(c.case_id, c.title, CATEGORY, expected, partial(_check, c, session, team_keys))
        for c in golden.cases
    ]
