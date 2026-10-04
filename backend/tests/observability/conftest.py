"""Fixtures for Spec 14 observability tests: the action/brief world plus trace helpers."""

from collections.abc import Iterator
from datetime import datetime
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.models import LLMTrace
from app.models.enums import TraceStatus
from tests.actions.conftest import (  # noqa: F401  (re-exported fixtures)
    FakeActionClient,
    _no_external_network,
    api,
    breach_world,
    clean_actions,
    clean_db,
    db_client,
    db_session,
    demo_session,
    engine,
    make_settings,
    no_incidents,
    test_db_url,
    valid_brief,
    volume_world,
    world,
)

# Shaped like a real OpenAI key so the redaction patterns, not luck, keep it out.
SECRET_KEY = "sk-test-DO-NOT-LEAK-0123456789abcdef"


def trace(
    operation: str = "brief_generation",
    *,
    status: TraceStatus = TraceStatus.SUCCESS,
    latency_ms: int = 100,
    input_tokens: int | None = 1000,
    output_tokens: int | None = 200,
    cost: Decimal | None = None,
    error_code: str | None = None,
    created_at: datetime | None = None,
) -> LLMTrace:
    row = LLMTrace(
        operation=operation,
        model_name="test-model",
        latency_ms=latency_ms,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        estimated_cost_usd=cost,
        status=status,
        error_code=error_code,
        error_message="safe failure" if status is TraceStatus.ERROR else None,
    )
    if created_at is not None:
        row.created_at = created_at
    return row


@pytest.fixture
def traces_db(clean_actions: Session) -> Iterator[Session]:  # noqa: F811
    """The rolled-back test session with no traces, briefs, actions or executions."""
    yield clean_actions
