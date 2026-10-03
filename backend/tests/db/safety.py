"""Hard safety guard for destructive database tests.

Downgrade/reset tests drop every table. They must only ever run against a
dedicated test database, so every destructive helper calls
``assert_safe_test_database`` first and refuses (it never skips) otherwise.
"""

from sqlalchemy.engine import URL, make_url

_LOCAL_HOSTS = {"", "localhost", "127.0.0.1", "::1"}
_TEST_DB_SUFFIX = "_test"


class UnsafeTestDatabaseError(Exception):
    """Raised when a destructive test would target a non-test database."""


def _identity(url: URL) -> tuple[str, int, str]:
    """(host, port, database) ignoring driver, credentials and query options."""
    host = (url.host or "").lower()
    if host in _LOCAL_HOSTS:
        host = "localhost"
    return host, url.port or 5432, url.database or ""


def _safe(url: URL) -> str:
    return url.render_as_string(hide_password=True)


def assert_safe_test_database(test_url: str | None, app_url: str) -> URL:
    """Return the parsed test URL, or raise ``UnsafeTestDatabaseError``."""
    if not test_url or not test_url.strip():
        raise UnsafeTestDatabaseError("TEST_DATABASE_URL is not set.")

    test = make_url(test_url)
    app = make_url(app_url)

    if _identity(test) == _identity(app):
        raise UnsafeTestDatabaseError(
            f"TEST_DATABASE_URL ({_safe(test)}) targets the same database as DATABASE_URL."
        )
    if not (test.database or "").endswith(_TEST_DB_SUFFIX):
        raise UnsafeTestDatabaseError(
            f"Test database name must end in '{_TEST_DB_SUFFIX}'; got {_safe(test)}."
        )
    return test
