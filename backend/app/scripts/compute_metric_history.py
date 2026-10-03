"""CLI: compute overall metric snapshots for the last N daily windows (dashboard trends).

    python -m app.scripts.compute_metric_history             # last 14 daily windows
    python -m app.scripts.compute_metric_history --days 30 --detect

Development/demo stopgap until the Spec 15 analysis orchestrator exists. It only calls
the existing idempotent services: re-running reuses snapshots (same MTR- IDs).
``--detect`` additionally runs anomaly detection for the latest window.

Exit codes: 0 success, 2 refused (environment or no source data), 1 unexpected error.
"""

import argparse
import sys
from collections.abc import Callable, Sequence
from datetime import timedelta

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import SessionLocal
from app.schemas.metrics import MetricFilters
from app.services.anomalies.service import AnomalyService
from app.services.metrics.errors import NoSourceDataError, WindowOutOfRangeError
from app.services.metrics.service import MetricsService

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_REFUSED = 2

DEFAULT_DAYS = 14
MAX_DAYS = 60


def _days(value: str) -> int:
    days = int(value)
    if not 1 <= days <= MAX_DAYS:
        raise argparse.ArgumentTypeError(f"--days must be between 1 and {MAX_DAYS}")
    return days


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.scripts.compute_metric_history",
        description="Compute overall metric snapshots for recent daily windows (dev/demo only).",
    )
    parser.add_argument("--days", type=_days, default=DEFAULT_DAYS, help="daily windows to compute")
    parser.add_argument(
        "--detect", action="store_true", help="also detect anomalies for the latest window"
    )
    return parser


def main(
    argv: Sequence[str] | None = None,
    session_factory: Callable[[], Session] = SessionLocal,
    settings: Settings | None = None,
) -> int:
    args = _parser().parse_args(argv)
    settings = settings or get_settings()
    if not settings.is_demo_environment:
        print(
            f"Refused: ENVIRONMENT={settings.environment!r} is not a demo/development environment.",
            file=sys.stderr,
        )
        return EXIT_REFUSED
    try:
        with session_factory() as session:
            metrics = MetricsService(session)
            latest = metrics.compute(None, MetricFilters()).window_end
            computed = 1
            skipped = 0
            for offset in range(1, args.days):
                try:
                    metrics.compute(latest - timedelta(days=offset), MetricFilters())
                    computed += 1
                except WindowOutOfRangeError:
                    skipped += 1  # baseline would start before the available data
            print(
                f"Metric history: {computed} window(s) up to {latest.isoformat()}, "
                f"{skipped} skipped (out of range)."
            )
            if args.detect:
                detected = AnomalyService(session).detect(None)
                print(
                    f"Detection: {detected.detected_count} detected, "
                    f"{detected.reused_count} reused, {detected.skipped_count} skipped."
                )
    except NoSourceDataError as exc:
        print(f"Refused: {exc.message}", file=sys.stderr)
        return EXIT_REFUSED
    except Exception as exc:  # report without a traceback that could echo connection details
        print(f"Metric history failed: {type(exc).__name__}", file=sys.stderr)
        return EXIT_ERROR
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
