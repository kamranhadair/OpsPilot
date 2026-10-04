"""Shared test fixtures.

The database dependency is overridden, so these tests need no live PostgreSQL.
"""

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.db.session import get_db
from app.main import app


class _StubSession:
    """Minimal stand-in for a SQLAlchemy ``Session``."""

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail

    def execute(self, *args: Any, **kwargs: Any) -> Any:
        if self.fail:
            raise OperationalError("SELECT 1", {}, Exception("connection refused"))
        return None

    def rollback(self) -> None:
        return None


@pytest.fixture
def client() -> Iterator[TestClient]:
    """Client whose database probe succeeds."""
    app.dependency_overrides[get_db] = lambda: _StubSession()
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def client_with_broken_db() -> Iterator[TestClient]:
    """Client whose database probe raises a connectivity error."""
    app.dependency_overrides[get_db] = lambda: _StubSession(fail=True)
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
