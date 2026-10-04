"""Prepare the isolated end-to-end database: create, migrate, reset/seed, evaluate.

    cd backend && E2E_DATABASE_URL=postgresql+psycopg://.../opspilot_e2e \\
        EVAL_REPORTS_DIR=/abs/path .venv/bin/python -m tests.e2e.prepare

Called by Playwright's global setup. It refuses any database whose name does not end
in ``_e2e`` or ``_test`` and any URL equal to ``DATABASE_URL`` from the normal
configuration, so the development database can never be wiped by a browser test run.
"""

import os
import subprocess
import sys

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

SAFE_SUFFIXES = ("_e2e", "_test")


def _fail(message: str) -> None:
    print(f"e2e prepare refused: {message}", file=sys.stderr)
    sys.exit(2)


def main() -> None:
    raw = os.environ.get("E2E_DATABASE_URL")
    if not raw:
        _fail("E2E_DATABASE_URL is not set.")
        return
    url = make_url(raw)
    if not str(url.database).endswith(SAFE_SUFFIXES):
        _fail(f"database {url.database!r} must end in one of {SAFE_SUFFIXES}.")

    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": url.database}
        ).scalar()
        if not exists:
            quoted = conn.dialect.identifier_preparer.quote(str(url.database))
            conn.execute(text(f"CREATE DATABASE {quoted}"))
    admin.dispose()

    env = {
        **os.environ,
        "DATABASE_URL": raw,
        "ENVIRONMENT": "test",
        # The prepare step never calls a model; the evaluation's model judge stays off.
        "OPENAI_API_KEY": "",
        "OPENAI_MODEL": "",
        "EVAL_MODEL_ENABLED": "false",
    }
    python = sys.executable
    # (argv, exit codes accepted). A failing or incomplete evaluation still writes the
    # report the evaluations page renders; the evaluation gate itself runs separately.
    steps: list[tuple[list[str], set[int]]] = [
        ([python, "-m", "alembic", "upgrade", "head"], {0}),
        ([python, "-m", "app.scripts.demo", "reset"], {0}),
        ([python, "-m", "app.evals.run"], {0, 1, 3}),
    ]
    for argv, accepted in steps:
        print(f"e2e prepare: {' '.join(argv[1:])}", flush=True)
        result = subprocess.run(argv, env=env, check=False)  # noqa: S603 - fixed argv
        if result.returncode not in accepted:
            sys.exit(result.returncode)


if __name__ == "__main__":
    main()
