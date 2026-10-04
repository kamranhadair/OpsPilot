"""CLI: the canonical demo workflow (Spec 15). Demo/development/test environments only.

    python -m app.scripts.demo reset      # clear derived artifacts + demo data, then reseed
    python -m app.scripts.demo analyze    # metrics -> anomalies -> contributors -> evidence
                                          # -> brief (only when the LLM is configured)

``reset`` leaves the database in the known pre-analysis state. ``analyze`` never
proposes, approves or executes an action; that stays a human workflow in the UI.

Exit codes: 0 success, 2 refused (environment or no source data), 1 unexpected error.
"""

import argparse
import sys
from collections.abc import Callable, Sequence

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import SessionLocal
from app.integrations.llm.base import BriefLLMClient
from app.integrations.llm.openai_client import get_brief_llm_client
from app.services.analysis.orchestrator import AnalysisOrchestrator
from app.services.demo.reset import reset_and_seed
from app.services.demo_data.seeder import DemoDataError
from app.services.metrics.errors import NoSourceDataError

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_REFUSED = 2


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.scripts.demo",
        description="Reset or analyse the OpsPilot demo (demo/development environments only).",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("reset", help="clear derived artifacts and demo data, then reseed")
    sub.add_parser("analyze", help="run the analysis for the final window")
    return parser


def _reset(session_factory: Callable[[], Session], settings: Settings) -> None:
    with session_factory() as session, session.begin():
        result = reset_and_seed(session, settings)
    derived = sum(result.derived_deleted.values())
    print(
        f"Reset: removed {derived} derived row(s), {result.reset.tickets} tickets, "
        f"{result.reset.customers} customers, {result.reset.incidents} event(s); "
        f"restarted {len(result.sequences_restarted)} evidence sequence(s)."
    )
    print(
        f"{result.seed.action}: {result.seed.tickets} tickets, {result.seed.customers} customers, "
        f"{result.seed.incidents} event(s); checksum {result.seed.checksum[:16]}"
    )


def _analyze(
    session_factory: Callable[[], Session],
    settings: Settings,
    client_factory: Callable[[], BriefLLMClient],
) -> None:
    with session_factory() as session:
        result = AnalysisOrchestrator(session, settings, client_factory).run()
    print(
        f"Window {result.window_start.isoformat()} .. {result.window_end.isoformat()}: "
        f"{len(result.metric_evidence_ids)} metric(s), {len(result.anomalies)} anomaly(ies), "
        f"{result.evidence.contributor_count} bundled contributor(s)."
    )
    for anomaly in result.anomalies:
        scope = ", ".join(f"{k}={v}" for k, v in anomaly.dimensions.items()) or "overall"
        print(f"  {anomaly.evidence_id} {anomaly.severity.value:<8} {anomaly.metric_key} ({scope})")
    brief = result.brief
    if brief.state == "generated":
        print(f"Brief {brief.brief_id}: {brief.status.value if brief.status else '?'}")
    else:
        print(f"Brief {brief.state}: {brief.error_code}")


def main(
    argv: Sequence[str] | None = None,
    session_factory: Callable[[], Session] = SessionLocal,
    settings: Settings | None = None,
    client_factory: Callable[[], BriefLLMClient] | None = None,
) -> int:
    args = _parser().parse_args(argv)
    settings = settings or get_settings()
    if not settings.is_demo_environment:
        print(
            f"Refused: ENVIRONMENT={settings.environment!r} is not a demo/development environment.",
            file=sys.stderr,
        )
        return EXIT_REFUSED
    resolved = settings
    try:
        if args.command == "reset":
            _reset(session_factory, settings)
        else:
            _analyze(
                session_factory,
                settings,
                client_factory or (lambda: get_brief_llm_client(resolved)),
            )
    except DemoDataError as exc:
        print(f"Refused: {exc}", file=sys.stderr)
        return EXIT_REFUSED
    except NoSourceDataError as exc:
        hint = "Run `python -m app.scripts.demo reset` first."
        print(f"Refused: {exc.message} {hint}", file=sys.stderr)
        return EXIT_REFUSED
    except Exception as exc:  # report without a traceback that could echo connection details
        print(f"Demo {args.command} failed: {type(exc).__name__}", file=sys.stderr)
        return EXIT_ERROR
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
