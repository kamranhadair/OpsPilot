"""Alembic helpers for tests. Every call re-checks the safety guard."""

from pathlib import Path

from alembic import command
from alembic.config import Config

from app.core.config import get_settings
from tests.db.safety import assert_safe_test_database

BACKEND_DIR = Path(__file__).resolve().parents[2]


def _config(test_url: str) -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.set_main_option("sqlalchemy.url", test_url.replace("%", "%%"))
    return cfg


def upgrade(test_url: str, revision: str = "head") -> None:
    assert_safe_test_database(test_url, get_settings().database_url)
    command.upgrade(_config(test_url), revision)


def downgrade(test_url: str, revision: str = "base") -> None:
    assert_safe_test_database(test_url, get_settings().database_url)
    command.downgrade(_config(test_url), revision)
