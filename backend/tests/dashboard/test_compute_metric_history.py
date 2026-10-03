"""The dev/demo metric-history CLI: environment guard and idempotent backfill."""

from collections.abc import Callable

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import Anomaly, MetricSnapshot
from app.scripts.compute_metric_history import EXIT_OK, EXIT_REFUSED, main

pytestmark = pytest.mark.db

DEV = Settings(environment="development")
PROD = Settings(environment="production")


def snapshot_ids(session: Session) -> set[str]:
    return set(session.execute(select(MetricSnapshot.evidence_id)).scalars())


def test_refuses_outside_demo_environments(
    demo_session: Session,
    connection_session_factory: Callable[[], Session],
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["--days", "3"], connection_session_factory, PROD) == EXIT_REFUSED
    assert "Refused" in capsys.readouterr().err
    assert snapshot_ids(demo_session) == set()


def test_refuses_without_source_data(
    clean_db: Session, connection_session_factory: Callable[[], Session]
) -> None:
    assert main([], connection_session_factory, DEV) == EXIT_REFUSED


def test_backfills_daily_windows_idempotently(
    demo_session: Session,
    connection_session_factory: Callable[[], Session],
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["--days", "3"], connection_session_factory, DEV) == EXIT_OK
    assert "3 window(s)" in capsys.readouterr().out
    first = snapshot_ids(demo_session)
    windows = demo_session.execute(
        select(func.count(func.distinct(MetricSnapshot.window_end)))
    ).scalar_one()
    assert windows == 3

    assert main(["--days", "3"], connection_session_factory, DEV) == EXIT_OK
    assert snapshot_ids(demo_session) == first


def test_detect_flag_runs_detection_for_the_latest_window(
    demo_session: Session, connection_session_factory: Callable[[], Session]
) -> None:
    assert main(["--days", "1", "--detect"], connection_session_factory, DEV) == EXIT_OK
    assert demo_session.execute(select(func.count()).select_from(Anomaly)).scalar_one() > 0
