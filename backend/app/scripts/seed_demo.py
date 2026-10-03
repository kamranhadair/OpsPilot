"""CLI: seed (or reset and reseed) the deterministic synthetic demo dataset.

    python -m app.scripts.seed_demo            # idempotent seed
    python -m app.scripts.seed_demo --reset    # delete demo rows, then reseed

Exit codes: 0 success / already seeded, 2 refused (environment or conflicting data),
1 unexpected error.
"""

import argparse
import sys
from collections.abc import Callable, Sequence

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import SessionLocal
from app.services.demo_data.seeder import (
    DemoDataError,
    reset_demo_data,
    seed_demo_data,
)

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_REFUSED = 2


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.scripts.seed_demo",
        description="Seed the deterministic synthetic OpsPilot demo dataset.",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="delete known demo/synthetic rows first (demo/development environments only)",
    )
    return parser


def main(
    argv: Sequence[str] | None = None,
    session_factory: Callable[[], Session] = SessionLocal,
    settings: Settings | None = None,
) -> int:
    args = _parser().parse_args(argv)
    settings = settings or get_settings()
    try:
        with session_factory() as session, session.begin():
            if args.reset:
                reset = reset_demo_data(session, settings=settings)
                print(
                    f"Reset: removed {reset.tickets} tickets, {reset.customers} customers, "
                    f"{reset.incidents} events, {reset.teams} teams."
                )
            result = seed_demo_data(session, settings=settings)
    except DemoDataError as exc:
        print(f"Refused: {exc}", file=sys.stderr)
        return EXIT_REFUSED
    except Exception as exc:  # report without a traceback that could echo connection details
        print(f"Seed failed: {type(exc).__name__}", file=sys.stderr)
        return EXIT_ERROR

    print(
        f"{result.action}: {result.teams} teams, {result.customers} customers, "
        f"{result.tickets} tickets, {result.incidents} event(s); checksum {result.checksum[:16]}"
    )
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
