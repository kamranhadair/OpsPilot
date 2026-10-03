"""DB fixtures for seeder/CLI tests; reuse the guarded engine from tests/db."""

from collections.abc import Callable, Iterator

import pytest
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.core.config import Settings
from tests.db.conftest import engine, test_db_url  # noqa: F401  (re-exported fixtures)


@pytest.fixture
def connection_session_factory(engine: Engine) -> Iterator[Callable[[], Session]]:  # noqa: F811
    """Sessions share one outer transaction that is always rolled back."""
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


@pytest.fixture
def dev_settings() -> Settings:
    return Settings(environment="development")


@pytest.fixture
def prod_settings() -> Settings:
    return Settings(environment="production")
