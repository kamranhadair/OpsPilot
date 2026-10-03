"""Fixtures for dashboard tests: one rolled-back connection shared by every session."""

from collections.abc import Callable, Iterator

import pytest
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from tests.anomalies.conftest import (  # noqa: F401  (re-exported fixtures)
    clean_db,
    db_client,
    demo_session,
    engine,
    spike_world,
    test_db_url,
    world,
)


@pytest.fixture
def connection_session_factory(engine: Engine) -> Iterator[Callable[[], Session]]:  # noqa: F811
    """Sessions share one outer transaction that is always rolled back (CLI tests)."""
    connection = engine.connect()
    outer = connection.begin()

    def factory() -> Session:
        return Session(bind=connection, join_transaction_mode="create_savepoint")

    try:
        yield factory
    finally:
        outer.rollback()
        connection.close()


@pytest.fixture
def db_session(connection_session_factory: Callable[[], Session]) -> Iterator[Session]:
    session = connection_session_factory()
    try:
        yield session
    finally:
        session.close()
