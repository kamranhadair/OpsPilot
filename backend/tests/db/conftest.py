"""Fixtures for tests that need a live PostgreSQL test database.

Skips (with a reason) only when TEST_DATABASE_URL is unset or the server is
unreachable. An unsafe URL fails the run instead.
"""

from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from tests.db import migrations
from tests.db.safety import UnsafeTestDatabaseError, assert_safe_test_database


@pytest.fixture(scope="session")
def test_db_url() -> str:
    settings = get_settings()
    if not settings.test_database_url:
        pytest.skip("TEST_DATABASE_URL is not set; database tests need a dedicated test database.")
    try:
        url = assert_safe_test_database(settings.test_database_url, settings.database_url)
    except UnsafeTestDatabaseError as exc:
        pytest.fail(f"Refusing to run destructive database tests: {exc}", pytrace=False)

    maintenance = url.set(database="postgres")
    admin = create_engine(maintenance, isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            exists = conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"),
                {"name": url.database},
            ).scalar()
            if not exists:
                quoted = conn.dialect.identifier_preparer.quote(str(url.database))
                conn.execute(text(f"CREATE DATABASE {quoted}"))
    except OperationalError:
        pytest.skip("PostgreSQL is not reachable; start it with `docker compose up -d db`.")
    finally:
        admin.dispose()
    return url.render_as_string(hide_password=False)


@pytest.fixture(scope="session")
def engine(test_db_url: str) -> Iterator[Engine]:
    migrations.upgrade(test_db_url)
    eng = create_engine(make_url(test_db_url))
    yield eng
    eng.dispose()


@pytest.fixture
def db_session(engine: Engine) -> Iterator[Session]:
    """Session inside an outer transaction that is always rolled back."""
    connection = engine.connect()
    outer = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        outer.rollback()
        connection.close()
