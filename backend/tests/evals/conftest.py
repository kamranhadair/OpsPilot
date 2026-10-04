"""Fixtures for evaluator tests: offline guard, settings, contexts and the seeded demo DB."""

from collections.abc import Callable

import pytest
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.evals.context import EvalContext, inspect_seed, unavailable_seed
from app.integrations.investigations.mock import MockInvestigationAdapter
from app.models.enums import ActionType
from app.services.demo_data.config import SEED_VERSION
from tests.anomalies.conftest import (  # noqa: F401  (re-exported fixtures)
    clean_db,
    db_session,
    demo_session,
    engine,
    test_db_url,
)


@pytest.fixture(autouse=True)
def _no_external_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Evaluations must run offline: only loopback (the test database) may be reached."""
    import socket  # noqa: PLC0415

    real_connect = socket.socket.connect

    def guarded(self: socket.socket, address: object) -> None:
        host = address[0] if isinstance(address, tuple) else None
        if host not in (None, "localhost", "127.0.0.1", "::1"):
            raise AssertionError(f"Unexpected external network access to {host!r}")
        real_connect(self, address)  # type: ignore[arg-type]

    monkeypatch.setattr(socket.socket, "connect", guarded)


def eval_settings(**overrides: object) -> Settings:
    """Settings that ignore any local .env: no API key unless a test sets one."""
    values: dict[str, object] = {
        "environment": "development",
        "openai_api_key": None,
        "openai_model": None,
        "eval_model_enabled": False,
        **overrides,
    }
    return Settings(_env_file=None, **values)  # type: ignore[arg-type]


def offline_context(**settings_overrides: object) -> EvalContext:
    """No database: dataset/approval cases must report not_run."""
    return EvalContext(
        settings=eval_settings(**settings_overrides),
        seed=unavailable_seed(SEED_VERSION),
        session=None,
        rollback_only=False,
        adapters={ActionType.OPEN_INVESTIGATION: MockInvestigationAdapter()},
        db_unavailable_reason="database_unavailable: test",
    )


ContextFactory = Callable[..., EvalContext]


@pytest.fixture
def demo_context(demo_session: Session) -> ContextFactory:  # noqa: F811
    """Context over the seeded demo dataset inside the rolled-back test transaction."""

    def build(**settings_overrides: object) -> EvalContext:
        return EvalContext(
            settings=eval_settings(**settings_overrides),
            seed=inspect_seed(demo_session, SEED_VERSION),
            session=demo_session,
            rollback_only=True,
            adapters={ActionType.OPEN_INVESTIGATION: MockInvestigationAdapter()},
        )

    return build
