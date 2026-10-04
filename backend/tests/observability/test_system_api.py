"""System endpoints: safe health, paginated traces, server-side summary (Spec 14)."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.main import app
from app.models import ActionExecution
from app.models.enums import ActionStatus, ExecutionStatus, TraceStatus
from app.schemas.system import LLMTraceListOut, SystemHealthResponse, SystemSummaryOut
from tests.db import factories
from tests.observability.conftest import SECRET_KEY, make_settings, trace

pytestmark = pytest.mark.db

OLD = datetime.now(UTC) - timedelta(days=10)


def _use_settings(**overrides: object) -> None:
    app.dependency_overrides[get_settings] = lambda: make_settings(**overrides)


def _seed(session: Session) -> None:
    session.add_all(
        [
            trace("brief_generation", latency_ms=100, cost=Decimal("0.010000")),
            trace("brief_generation", latency_ms=300, cost=Decimal("0.020000")),
            trace(
                "brief_generation",
                status=TraceStatus.ERROR,
                latency_ms=500,
                input_tokens=None,
                output_tokens=None,
                error_code="LLM_TIMEOUT",
            ),
            trace("action_proposal", latency_ms=200, input_tokens=50, output_tokens=10),
            # Outside the default 7-day window.
            trace("brief_generation", latency_ms=9000, created_at=OLD),
        ]
    )
    session.flush()


def _execution(session: Session, status: ExecutionStatus, error_code: str | None) -> int:
    brief = factories.brief()
    session.add(brief)
    session.flush()
    action = factories.action(brief.id, status=ActionStatus(status.value))
    session.add(action)
    session.flush()
    now = datetime.now(UTC)
    row = ActionExecution(
        action_id=action.id,
        adapter_key="mock_investigation",
        status=status,
        request_json={},
        response_json={"error_code": error_code} if error_code else {"ok": True},
        error_message="The investigation adapter failed." if error_code else None,
        started_at=now,
        finished_at=now,
    )
    session.add(row)
    session.flush()
    return action.id


# --- summary ---------------------------------------------------------------------------


def test_summary_aggregates_calls_errors_latency_tokens_and_cost(
    api: TestClient, traces_db: Session
) -> None:
    _seed(traces_db)
    response = api.get("/api/system/summary")

    assert response.status_code == 200, response.text
    body = SystemSummaryOut.model_validate(response.json())
    assert body.period == "7d" and body.window_start is not None
    llm = body.llm
    assert (llm.total_calls, llm.success_count, llm.error_count) == (4, 3, 1)
    assert llm.error_rate == 0.25
    assert llm.latency_ms is not None
    assert llm.latency_ms.avg == 275.0
    assert llm.latency_ms.max == 500
    assert llm.latency_ms.p50 == 250.0
    assert llm.input_tokens_total == 1000 + 1000 + 50
    assert llm.output_tokens_total == 200 + 200 + 10
    assert llm.calls_missing_usage == 1
    assert llm.estimated_cost_usd == pytest.approx(0.03)
    assert llm.calls_missing_cost == 2
    assert llm.cost_configured is False
    by_op = {o.operation: o for o in llm.by_operation}
    assert by_op["brief_generation"].total_calls == 3
    assert by_op["brief_generation"].error_rate == pytest.approx(0.3333)
    assert by_op["action_proposal"].estimated_cost_usd is None


def test_period_all_includes_older_traces(api: TestClient, traces_db: Session) -> None:
    _seed(traces_db)
    body = SystemSummaryOut.model_validate(api.get("/api/system/summary?period=all").json())
    assert body.window_start is None
    assert body.llm.total_calls == 5
    assert body.llm.latency_ms is not None and body.llm.latency_ms.max == 9000


def test_empty_summary_has_null_rates_and_cost(api: TestClient, traces_db: Session) -> None:
    body = SystemSummaryOut.model_validate(api.get("/api/system/summary").json())
    assert body.llm.total_calls == 0
    assert body.llm.error_rate is None
    assert body.llm.latency_ms is None
    assert body.llm.estimated_cost_usd is None
    assert body.llm.by_operation == []
    assert body.executions.total == 0 and body.executions.recent_failures == []


def test_summary_reports_cost_configuration(api: TestClient, traces_db: Session) -> None:
    _use_settings(openai_input_cost_per_1m="1", openai_output_cost_per_1m="2")
    body = SystemSummaryOut.model_validate(api.get("/api/system/summary").json())
    assert body.llm.cost_configured is True


def test_summary_lists_recent_execution_failures(api: TestClient, traces_db: Session) -> None:
    _execution(traces_db, ExecutionStatus.SUCCEEDED, None)
    failed_action = _execution(traces_db, ExecutionStatus.FAILED, "ADAPTER_UNAVAILABLE")

    body = SystemSummaryOut.model_validate(api.get("/api/system/summary").json())
    executions = body.executions
    assert (executions.total, executions.succeeded, executions.failed) == (2, 1, 1)
    (failure,) = executions.recent_failures
    assert failure.action_id == failed_action
    assert failure.error_code == "ADAPTER_UNAVAILABLE"


def test_invalid_period_is_rejected(api: TestClient, traces_db: Session) -> None:
    assert api.get("/api/system/summary?period=1y").status_code == 422


# --- trace list ------------------------------------------------------------------------


def test_trace_list_is_paginated_newest_first(api: TestClient, traces_db: Session) -> None:
    _seed(traces_db)
    first = LLMTraceListOut.model_validate(api.get("/api/system/llm-traces?limit=2").json())
    second = LLMTraceListOut.model_validate(
        api.get("/api/system/llm-traces?limit=2&offset=2").json()
    )

    assert first.total == second.total == 5
    assert (first.limit, first.offset, len(first.items)) == (2, 0, 2)
    ids = [t.id for t in first.items + second.items]
    assert len(set(ids)) == 4
    assert first.items[0].created_at >= second.items[-1].created_at
    # The 10-day-old trace is last overall.
    last = LLMTraceListOut.model_validate(api.get("/api/system/llm-traces?limit=1&offset=4").json())
    assert last.items[0].latency_ms == 9000


def test_trace_list_filters(api: TestClient, traces_db: Session) -> None:
    _seed(traces_db)
    errors = LLMTraceListOut.model_validate(api.get("/api/system/llm-traces?status=error").json())
    assert errors.total == 1
    item = errors.items[0]
    assert item.error_code == "LLM_TIMEOUT"
    assert item.input_tokens is None and item.estimated_cost_usd is None

    actions = LLMTraceListOut.model_validate(
        api.get("/api/system/llm-traces?operation=action_proposal").json()
    )
    assert actions.total == 1

    since = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    recent = LLMTraceListOut.model_validate(
        api.get("/api/system/llm-traces", params={"since": since}).json()
    )
    assert recent.total == 4


@pytest.mark.parametrize(
    "query",
    ["limit=0", "limit=101", "offset=-1", "status=maybe", "since=not-a-date"],
)
def test_invalid_trace_filters_are_rejected(
    api: TestClient, traces_db: Session, query: str
) -> None:
    assert api.get(f"/api/system/llm-traces?{query}").status_code == 422


def test_since_after_until_is_a_typed_error(api: TestClient, traces_db: Session) -> None:
    now = datetime.now(UTC)
    response = api.get(
        "/api/system/llm-traces",
        params={"since": now.isoformat(), "until": (now - timedelta(days=1)).isoformat()},
    )
    assert response.status_code == 422
    assert response.json()["code"] == "INVALID_TRACE_FILTER"


# --- health ----------------------------------------------------------------------------


def test_health_reports_readiness_without_secrets(api: TestClient, traces_db: Session) -> None:
    _use_settings(openai_api_key=SECRET_KEY, openai_model="test-model")
    response = api.get("/api/system/health")

    assert response.status_code == 200, response.text
    body = SystemHealthResponse.model_validate(response.json())
    assert body.status == "ok"
    assert body.database.status == "ok"
    assert body.database.migration_revision == "0007"
    assert body.llm.configured is True and body.llm.model == "test-model"
    assert body.cost_estimation.configured is False
    assert SECRET_KEY not in response.text
    assert "opspilot_local_dev" not in response.text  # no connection string / password


def test_health_is_degraded_without_llm_configuration(api: TestClient, traces_db: Session) -> None:
    _use_settings(openai_api_key=None, openai_model=None)
    body = SystemHealthResponse.model_validate(api.get("/api/system/health").json())
    assert body.status == "degraded"
    assert body.llm.configured is False and body.llm.model is None


# --- demo gating -----------------------------------------------------------------------


@pytest.mark.parametrize(
    "path", ["/api/system/health", "/api/system/llm-traces", "/api/system/summary"]
)
def test_system_endpoints_are_disabled_outside_demo_environments(
    api: TestClient, traces_db: Session, path: str
) -> None:
    _use_settings(environment="production")
    response = api.get(path)
    assert response.status_code == 404
    assert response.json()["code"] == "SYSTEM_ENDPOINTS_DISABLED"
