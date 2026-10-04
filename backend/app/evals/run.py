"""CLI: run the OpsPilot evaluation suites and write ``evals/reports/latest.json``.

    python -m app.evals.run --suite all            # deterministic + AI guardrails (default)
    python -m app.evals.run --suite deterministic  # metrics, anomalies, contributors,
                                                   # approval boundary, replay
    python -m app.evals.run --suite ai             # citation, causation, action grounding,
                                                   # optional model judge
    python -m app.evals.run --replay-days 7 --no-markdown

Deterministic and AI-guardrail suites never call a model or the network; they read the
configured database inside a transaction that is always rolled back. The optional
model-based judge runs only with ``EVAL_MODEL_ENABLED=true`` and a configured LLM.

Exit codes: 0 every executed case passed and nothing was skipped; 1 a case failed or
errored; 2 refused (non-demo environment); 3 incomplete (some cases did not run).
"""

import argparse
import logging
import sys
from collections.abc import Callable, Iterator, Sequence
from contextlib import ExitStack, contextmanager
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.evals.cases import load_anomaly_golden
from app.evals.context import (
    EvalContext,
    inspect_seed,
    rollback_session,
    unavailable_seed,
)
from app.evals.replay import DEFAULT_REPLAY_DAYS, MAX_REPLAY_DAYS, replay
from app.evals.report import build_report, render_markdown
from app.evals.results import guarded
from app.evals.store import write_report
from app.evals.suites import (
    actions,
    anomalies,
    approval,
    brief_guardrails,
    contributors,
    metrics,
    model_judge,
)
from app.integrations.investigations.mock import get_investigation_adapters
from app.schemas.evaluations import (
    CaseResult,
    EvalCategory,
    EvaluationReport,
    ModelBasedSection,
    ReplaySummary,
    SuiteName,
)

logger = logging.getLogger(__name__)

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_REFUSED = 2
EXIT_INCOMPLETE = 3

Suite = tuple[str, Callable[[EvalContext], list[CaseResult]], EvalCategory]

DETERMINISTIC_SUITES: tuple[Suite, ...] = (
    ("metrics", metrics.run, EvalCategory.METRIC_CORRECTNESS),
    ("anomalies", anomalies.run, EvalCategory.ANOMALY_DETECTION),
    ("contributors", contributors.run, EvalCategory.CONTRIBUTOR_ATTRIBUTION),
    ("approval", approval.run, EvalCategory.APPROVAL_BOUNDARY),
)
AI_SUITES: tuple[Suite, ...] = (
    ("brief_guardrails", brief_guardrails.run, EvalCategory.CITATION_VALIDITY),
    ("actions", actions.run, EvalCategory.ACTION_GROUNDING),
)


def _run_suite(suite: Suite, ctx: EvalContext) -> list[CaseResult]:
    """A suite that crashes as a whole is recorded as one error; the run continues."""
    name, run, category = suite
    results: list[CaseResult] = []

    def whole() -> CaseResult:
        results.extend(run(ctx))
        return CaseResult(
            case_id=f"suite.{name}", title=name, category=category, status="pass", expected=""
        )

    outcome = guarded(f"suite.{name}", f"{name} suite", category, "suite completes", whole)
    return results if outcome.status == "pass" else [*results, outcome]


def run_evaluation(
    ctx: EvalContext,
    suite: SuiteName = "all",
    replay_days: int = DEFAULT_REPLAY_DAYS,
    *,
    now: datetime | None = None,
) -> EvaluationReport:
    """Run the selected suites against ``ctx`` and build (not write) the report."""
    cases: list[CaseResult] = []
    replay_summary: ReplaySummary | None = None
    model_based = ModelBasedSection(status="not_run", reason="not part of the deterministic suite")

    if suite in {"all", "deterministic"}:
        for item in DETERMINISTIC_SUITES:
            cases.extend(_run_suite(item, ctx))
        replay_summary = _replay(ctx, replay_days)
    if suite in {"all", "ai"}:
        for item in AI_SUITES:
            cases.extend(_run_suite(item, ctx))
        try:
            model_based = model_judge.run(ctx)
        except Exception as exc:  # noqa: BLE001 - reported, never counted as a pass
            model_based = ModelBasedSection(
                status="error", reason=f"{type(exc).__name__}: {exc}"[:500]
            )

    return build_report(
        suite=suite,
        generated_at=now or datetime.now(UTC),
        seed=ctx.seed,
        cases=cases,
        replay=replay_summary,
        model_based=model_based,
    )


def _replay(ctx: EvalContext, days: int) -> ReplaySummary:
    if ctx.session is None:
        return ReplaySummary(
            status="not_run",
            reason=ctx.db_unavailable_reason or "database_unavailable",
            days_requested=days,
        )
    try:
        return replay(ctx.session, days)
    except Exception as exc:  # noqa: BLE001 - a broken replay is reported, not hidden
        ctx.session.rollback()
        return ReplaySummary(
            status="error", reason=f"{type(exc).__name__}: {exc}"[:500], days_requested=days
        )


@contextmanager
def open_context(settings: Settings, engine: Engine) -> Iterator[EvalContext]:
    """Build the run context; a database outage degrades to not_run, not a crash."""
    case_version = load_anomaly_golden().seed_version
    adapters = get_investigation_adapters(settings)
    with ExitStack() as stack:
        try:
            session: Session | None = stack.enter_context(rollback_session(engine))
            assert session is not None
            seed = inspect_seed(session, case_version)
        except OperationalError as exc:
            logger.warning("Database unavailable for evaluation: %s", type(exc).__name__)
            stack.close()
            session, seed = None, unavailable_seed(case_version)
        yield EvalContext(
            settings=settings,
            seed=seed,
            session=session,
            rollback_only=session is not None,
            adapters=adapters,
            db_unavailable_reason=None
            if session is not None
            else "database_unavailable: could not connect to DATABASE_URL",
        )


def _replay_days(value: str) -> int:
    days = int(value)
    if not 1 <= days <= MAX_REPLAY_DAYS:
        raise argparse.ArgumentTypeError(f"--replay-days must be between 1 and {MAX_REPLAY_DAYS}")
    return days


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.evals.run", description="Run the OpsPilot evaluation suites."
    )
    parser.add_argument("--suite", choices=["all", "deterministic", "ai"], default="all")
    parser.add_argument("--replay-days", type=_replay_days, default=DEFAULT_REPLAY_DAYS)
    parser.add_argument("--no-markdown", action="store_true", help="skip latest.md")
    parser.add_argument("--reports-dir", type=Path, default=None, help="override output dir")
    return parser


def exit_code(report: EvaluationReport) -> int:
    return {"pass": EXIT_OK, "fail": EXIT_FAILED, "incomplete": EXIT_INCOMPLETE}[
        report.overall_status
    ]


def main(
    argv: Sequence[str] | None = None,
    settings: Settings | None = None,
    engine: Engine | None = None,
) -> int:
    args = _parser().parse_args(argv)
    settings = settings or get_settings()
    if not settings.is_demo_environment:
        print(
            f"Refusing to evaluate: ENVIRONMENT={settings.environment!r} is not a "
            "demo/development environment.",
            file=sys.stderr,
        )
        return EXIT_REFUSED
    if engine is None:
        from app.db.session import engine as app_engine

        engine = app_engine

    with open_context(settings, engine) as ctx:
        report = run_evaluation(ctx, args.suite, args.replay_days)
    directory = args.reports_dir or Path(settings.eval_reports_dir)
    markdown = None if args.no_markdown else render_markdown(report)
    paths = write_report(directory, report, markdown)

    _print_summary(report, paths)
    return exit_code(report)


def _print_summary(report: EvaluationReport, paths: Sequence[Path]) -> None:
    print(f"Evaluation ({report.suite}): {report.overall_status.upper()}")
    for ratio in report.ratios:
        value = "n/a" if ratio.value is None else f"{ratio.value * 100:.1f}%"
        print(f"  {ratio.label}: {value} ({ratio.numerator}/{ratio.denominator})")
    for count in report.counts:
        print(
            f"  {count.label}: {count.passed} pass, {count.failed} fail, "
            f"{count.errored} error, {count.not_run} not run"
        )
    for case in report.cases:
        if case.status != "pass":
            print(f"  [{case.status.upper()}] {case.case_id}: {case.failure_reason}")
    if report.replay is not None:
        print(f"  Replay: {report.replay.status} ({len(report.replay.days)} days)")
    mb = report.model_based
    print(f"  Model-based: {mb.status.upper()}" + (f" ({mb.reason})" if mb.reason else ""))
    for path in paths:
        print(f"  Wrote {path}")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
