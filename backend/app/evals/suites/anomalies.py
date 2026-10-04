"""Planted-anomaly recall and designated normal-case false positives on the demo seed."""

from collections.abc import Callable
from datetime import datetime
from functools import partial

from sqlalchemy.orm import Session

from app.evals.cases import NormalCase, PlantedAnomalyCase, load_anomaly_golden
from app.evals.context import EvalContext, seed_gate
from app.evals.pipeline import SliceOutcome, data_range, evaluate_slice, window_in_range
from app.evals.results import guarded, not_run, verdict
from app.models.enums import AnomalySeverity
from app.schemas.evaluations import CaseResult, CaseTally, EvalCategory
from app.services.anomalies.detector import Detection
from app.services.metrics.engine import analysis_window

ESCALATED = frozenset({AnomalySeverity.HIGH, AnomalySeverity.CRITICAL})


class OutOfRangeError(Exception):
    """The case window lies outside the available data."""


def _slice_loader(session: Session) -> Callable[[datetime, dict[str, str]], list[SliceOutcome]]:
    bounds = data_range(session)
    cache: dict[tuple[datetime, tuple[tuple[str, str], ...]], list[SliceOutcome]] = {}

    def load(window_end: datetime, filters: dict[str, str]) -> list[SliceOutcome]:
        if bounds is None or not window_in_range(analysis_window(window_end), bounds):
            raise OutOfRangeError(f"window ending {window_end.isoformat()} is outside the data")
        key = (window_end, tuple(sorted(filters.items())))
        if key not in cache:
            cache[key] = evaluate_slice(session, window_end, filters)
        return cache[key]

    return load


def slice_label(filters: dict[str, str]) -> str:
    return ", ".join(filters.values()) or "overall"


def _describe(outcome: SliceOutcome) -> str:
    if isinstance(outcome.outcome, Detection):
        score = outcome.outcome.score
        return f"{outcome.outcome.severity.value} (score {score.normalize():f})"
    return f"not flagged ({outcome.outcome.reason.value})"


def _planted(case: PlantedAnomalyCase, load: Callable[..., list[SliceOutcome]]) -> CaseResult:
    expected = f"{case.metric_key} flagged as {'/'.join(s.value for s in case.expected_severities)}"
    outcomes = load(case.window_end, case.filters)
    outcome = next(o for o in outcomes if o.metric_key == case.metric_key)
    detected = (
        isinstance(outcome.outcome, Detection)
        and outcome.outcome.severity in case.expected_severities
    )
    return verdict(
        case.case_id,
        case.title,
        EvalCategory.ANOMALY_DETECTION,
        passed=detected,
        expected=expected,
        observed=f"{case.metric_key}: {_describe(outcome)}",
        failure_reason=f"Planted anomaly not at the expected severity: {_describe(outcome)}",
    )


def _normal(case: NormalCase, load: Callable[..., list[SliceOutcome]]) -> CaseResult:
    outcomes = [o for filters in case.slices for o in load(case.window_end, filters)]
    checked = [o for o in outcomes if o.result.is_defined]
    flagged = [
        o for o in checked if isinstance(o.outcome, Detection) and o.outcome.severity in ESCALATED
    ]
    observed = (
        "; ".join(f"{o.metric_key} [{slice_label(o.filters)}]: {_describe(o)}" for o in flagged)
        or f"no high/critical anomaly across {len(checked)} metrics"
    )
    if not checked:
        reason = "No metric had data to check; a normal case cannot pass without evidence."
    else:
        reason = f"{len(flagged)} high/critical false positive(s): {observed}"
    return verdict(
        case.case_id,
        case.title,
        EvalCategory.FALSE_POSITIVE,
        passed=bool(checked) and not flagged,
        expected="no high/critical anomaly",
        observed=observed,
        failure_reason=reason,
        tally=CaseTally(flagged=len(flagged), checked=len(checked)),
    )


def run(ctx: EvalContext) -> list[CaseResult]:
    golden = load_anomaly_golden(ctx.cases_dir)
    planted_expected = "planted anomaly detected"
    normal_expected = "no high/critical anomaly"
    reason = seed_gate(ctx, golden.seed_version)
    if reason is not None or ctx.session is None:
        why = reason or "database_unavailable"
        return [
            *(
                not_run(c.case_id, c.title, EvalCategory.ANOMALY_DETECTION, planted_expected, why)
                for c in golden.planted
            ),
            *(
                not_run(c.case_id, c.title, EvalCategory.FALSE_POSITIVE, normal_expected, why)
                for c in golden.normal
            ),
        ]

    load = _slice_loader(ctx.session)
    results = [
        guarded(
            c.case_id,
            c.title,
            EvalCategory.ANOMALY_DETECTION,
            planted_expected,
            partial(_planted, c, load),
        )
        for c in golden.planted
    ]
    results.extend(
        guarded(
            c.case_id,
            c.title,
            EvalCategory.FALSE_POSITIVE,
            normal_expected,
            partial(_normal, c, load),
        )
        for c in golden.normal
    )
    return results
