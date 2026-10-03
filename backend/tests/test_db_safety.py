"""The destructive-test guard (pure unit tests; no database needed)."""

import pytest

from tests.db.safety import UnsafeTestDatabaseError, assert_safe_test_database

APP = "postgresql+psycopg://opspilot:secret@localhost:5432/opspilot"


def test_accepts_dedicated_test_database() -> None:
    url = assert_safe_test_database(
        "postgresql+psycopg://opspilot:secret@localhost:5432/opspilot_test", APP
    )
    assert url.database == "opspilot_test"


@pytest.mark.parametrize("value", [None, "", "   "])
def test_rejects_unset_url(value: str | None) -> None:
    with pytest.raises(UnsafeTestDatabaseError, match="not set"):
        assert_safe_test_database(value, APP)


def test_rejects_identical_url() -> None:
    with pytest.raises(UnsafeTestDatabaseError):
        assert_safe_test_database(APP, APP)


def test_rejects_same_database_with_other_driver_or_credentials() -> None:
    with pytest.raises(UnsafeTestDatabaseError, match="same database"):
        assert_safe_test_database("postgresql://other:pw@127.0.0.1/opspilot", APP)


def test_rejects_same_database_even_if_it_is_named_like_a_test_db() -> None:
    app = "postgresql+psycopg://u:p@localhost:5432/opspilot_test"
    with pytest.raises(UnsafeTestDatabaseError, match="same database"):
        assert_safe_test_database(app, app)


def test_rejects_name_without_test_suffix() -> None:
    with pytest.raises(UnsafeTestDatabaseError, match="_test"):
        assert_safe_test_database("postgresql+psycopg://u:p@localhost:5432/scratch", APP)


def test_failure_message_hides_password() -> None:
    with pytest.raises(UnsafeTestDatabaseError) as info:
        assert_safe_test_database("postgresql+psycopg://u:hunter2@localhost:5432/scratch", APP)
    assert "hunter2" not in str(info.value)


def test_migration_helpers_refuse_unsafe_urls() -> None:
    from tests.db import migrations

    with pytest.raises(UnsafeTestDatabaseError):
        migrations.downgrade(APP)
    with pytest.raises(UnsafeTestDatabaseError):
        migrations.upgrade("postgresql+psycopg://u:p@localhost:5432/scratch")
