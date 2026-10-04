"""Every LLM operation records safe trace metadata (Spec 14)."""

import json
import logging
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import JsonFormatter, request_id_var
from app.integrations.llm.base import (
    LLMError,
    LLMProviderError,
    LLMRateLimitedError,
    LLMTimeoutError,
)
from app.main import app
from app.models import Brief, LLMTrace
from app.models.enums import BriefStatus, LLMOperation, TraceStatus
from app.services.briefs.generator import BriefService
from app.services.observability.traces import LLMTraceRecorder
from tests.actions.conftest import (
    FakeActionClient,
    install_action_client,
    observation,
    proposal,
)
from tests.briefs.conftest import FakeBriefClient, draft_output, install_client
from tests.evidence.conftest import detect_billing_volume
from tests.metrics.conftest import World
from tests.observability.conftest import SECRET_KEY, make_settings

pytestmark = pytest.mark.db

PRICES = {"openai_input_cost_per_1m": "2.50", "openai_output_cost_per_1m": "10"}


def _traces(session: Session) -> list[LLMTrace]:
    return list(session.execute(select(LLMTrace).order_by(LLMTrace.id)).scalars())


def _use_settings(**overrides: object) -> None:
    app.dependency_overrides[get_settings] = lambda: make_settings(**overrides)


def _formatted(caplog: pytest.LogCaptureFixture) -> str:
    formatter = JsonFormatter()
    return "\n".join(formatter.format(r) for r in caplog.records)


def _llm_calls(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.getMessage() == "llm.call"]


# --- brief generation ------------------------------------------------------------------


def test_successful_brief_records_trace_with_context_and_null_cost_when_unpriced(
    volume_world: World, api: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    anomaly_id = detect_billing_volume(volume_world)
    install_client(FakeBriefClient(draft_output(observation(anomaly_id))))

    response = api.post("/api/briefs/generate", headers={"X-Request-ID": "req-brief-1"})

    assert response.status_code == 201, response.text
    (trace,) = _traces(volume_world.session)
    assert trace.operation == LLMOperation.BRIEF_GENERATION
    assert trace.status is TraceStatus.SUCCESS
    assert trace.brief_id == response.json()["id"]
    assert trace.action_id is None
    assert (trace.input_tokens, trace.output_tokens, trace.latency_ms) == (123, 45, 7)
    assert trace.estimated_cost_usd is None
    assert trace.request_id == "req-brief-1"
    (call,) = _llm_calls(caplog)
    assert call.__dict__["persisted"] is True and call.__dict__["trace_id"] == trace.id


def test_configured_prices_produce_an_estimated_cost(volume_world: World, api: TestClient) -> None:
    _use_settings(**PRICES)
    anomaly_id = detect_billing_volume(volume_world)
    install_client(FakeBriefClient(draft_output(observation(anomaly_id))))

    assert api.post("/api/briefs/generate").status_code == 201
    (trace,) = _traces(volume_world.session)
    # 123 * 2.5 / 1M + 45 * 10 / 1M
    assert trace.estimated_cost_usd == Decimal("0.000758")


def test_failed_call_records_error_code_client_latency_and_no_usage(
    volume_world: World, api: TestClient
) -> None:
    _use_settings(**PRICES)
    detect_billing_volume(volume_world)
    install_client(FakeBriefClient(error=LLMTimeoutError("timed out", latency_ms=1500)))

    assert api.post("/api/briefs/generate").status_code == 504
    (trace,) = _traces(volume_world.session)
    assert trace.status is TraceStatus.ERROR
    assert trace.error_code == "LLM_TIMEOUT"
    assert trace.latency_ms == 1500
    assert trace.input_tokens is None and trace.output_tokens is None
    assert trace.estimated_cost_usd is None  # priced, but no usage was reported


def test_repeated_model_errors_each_record_a_trace(volume_world: World, api: TestClient) -> None:
    detect_billing_volume(volume_world)
    install_client(FakeBriefClient(error=LLMRateLimitedError("slow down")))

    for _ in range(3):
        assert api.post("/api/briefs/generate").status_code == 429

    traces = _traces(volume_world.session)
    assert len(traces) == 3
    assert {t.error_code for t in traces} == {"LLM_RATE_LIMITED"}
    assert all(t.latency_ms >= 0 for t in traces)


def test_secrets_and_model_text_never_reach_traces_or_logs(
    volume_world: World, api: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    _use_settings(openai_api_key=SECRET_KEY)
    anomaly_id = detect_billing_volume(volume_world)
    claim_text = "UNIQUE-CLAIM-TEXT-7f3a billing volume is elevated."

    install_client(FakeBriefClient(draft_output(observation(anomaly_id, text=claim_text))))
    assert api.post("/api/briefs/generate").status_code == 201
    error = LLMProviderError(
        f"upstream rejected key {SECRET_KEY} (Authorization: Bearer {SECRET_KEY})"
    )
    install_client(FakeBriefClient(error=error))
    assert api.post("/api/briefs/generate").status_code == 502

    failed = _traces(volume_world.session)[-1]
    assert failed.error_message is not None
    assert SECRET_KEY not in failed.error_message
    assert "upstream rejected key" in failed.error_message
    output = _formatted(caplog)
    assert SECRET_KEY not in output
    assert claim_text not in output
    assert "UNIQUE-CLAIM-TEXT" not in caplog.text


def test_trace_persistence_failure_does_not_fail_the_brief(
    volume_world: World, clean_actions: Session, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    anomaly_id = detect_billing_volume(volume_world)
    client = FakeBriefClient(draft_output(observation(anomaly_id)))
    service = BriefService(clean_actions, make_settings(), lambda: client)

    # Longer than llm_traces.request_id allows: only the trace insert can fail.
    token = request_id_var.set("r" * 80)
    try:
        response = service.generate()
    finally:
        request_id_var.reset(token)

    assert response.status is BriefStatus.VALID
    assert clean_actions.get(Brief, response.id) is not None
    assert _traces(clean_actions) == []
    failures = [r for r in caplog.records if r.getMessage() == "llm_trace.persist_failed"]
    assert len(failures) == 1
    (call,) = _llm_calls(caplog)
    assert call.__dict__["persisted"] is False


def test_recorder_session_stays_usable_after_a_failed_insert(clean_actions: Session) -> None:
    recorder = LLMTraceRecorder(clean_actions, make_settings())
    token = request_id_var.set("r" * 80)
    try:
        assert (
            recorder.failure(
                LLMOperation.ACTION_PROPOSAL,
                LLMError("boom"),
                model_name="m",
                latency_ms=5,
            )
            is None
        )
    finally:
        request_id_var.reset(token)
    stored = recorder.success(
        LLMOperation.ACTION_PROPOSAL,
        model_name="m",
        latency_ms=5,
        input_tokens=None,
        output_tokens=None,
    )
    assert stored is not None
    count = clean_actions.execute(select(func.count()).select_from(LLMTrace)).scalar_one()
    assert count == 1


# --- action proposal -------------------------------------------------------------------


def test_action_proposal_trace_links_brief_and_created_action(
    valid_brief: tuple[dict[str, object], list[str]],
    api: TestClient,
    volume_world: World,
) -> None:
    brief, (anomaly_id, metric_id) = valid_brief
    install_action_client(FakeActionClient(proposal([anomaly_id, metric_id])))

    response = api.post(f"/api/briefs/{brief['id']}/actions/propose")

    assert response.status_code == 201, response.text
    trace = _traces(volume_world.session)[-1]
    assert trace.operation == LLMOperation.ACTION_PROPOSAL
    assert trace.brief_id == brief["id"]
    assert trace.action_id == response.json()["id"]
    assert (trace.input_tokens, trace.output_tokens) == (200, 60)


def test_failed_action_proposal_trace_has_brief_but_no_action(
    valid_brief: tuple[dict[str, object], list[str]],
    api: TestClient,
    volume_world: World,
) -> None:
    brief, _ = valid_brief
    install_action_client(FakeActionClient(error=LLMProviderError("provider down")))

    assert api.post(f"/api/briefs/{brief['id']}/actions/propose").status_code == 502
    trace = _traces(volume_world.session)[-1]
    assert trace.operation == LLMOperation.ACTION_PROPOSAL
    assert trace.status is TraceStatus.ERROR
    assert trace.brief_id == brief["id"] and trace.action_id is None


# --- log-only traces (evaluation judge) -------------------------------------------------


def test_log_only_trace_writes_nothing_but_logs_metadata(
    clean_actions: Session, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    recorder = LLMTraceRecorder(clean_actions, make_settings(**PRICES))
    assert (
        recorder.success(
            LLMOperation.CITATION_JUDGE_EVAL,
            model_name="judge",
            latency_ms=4,
            input_tokens=10,
            output_tokens=2,
            persist=False,
        )
        is None
    )
    assert _traces(clean_actions) == []
    (call,) = _llm_calls(caplog)
    entry = json.loads(JsonFormatter().format(call))
    assert entry["operation"] == "citation_judge_eval"
    assert entry["persisted"] is False
    assert entry["estimated_cost_usd"] == "0.000045"
