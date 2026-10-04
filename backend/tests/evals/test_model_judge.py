"""The optional model judge: gated, mockable, and never silently counted as passed."""

import pytest

from app.evals.run import run_evaluation
from app.evals.suites import model_judge
from app.integrations.llm import openai_client
from app.integrations.llm.base import CitationJudgeResult, LLMError, LLMTimeoutError
from app.schemas.evaluations import (
    CitationJudgeRequest,
    CitationSupportJudgement,
    CitationSupportVerdict,
)
from tests.evals.conftest import offline_context

CONFIGURED = {"openai_api_key": "test-key-not-real", "openai_model": "judge-model"}


class FakeJudge:
    def __init__(
        self, verdict: CitationSupportVerdict = "supported", error: LLMError | None = None
    ) -> None:
        self.verdict = verdict
        self.error = error
        self.requests: list[CitationJudgeRequest] = []

    def judge_citation_support(self, request: CitationJudgeRequest) -> CitationJudgeResult:
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        return CitationJudgeResult(
            output=CitationSupportJudgement(verdict=self.verdict, rationale="fake rationale"),
            model_name="judge-model-2026",
            latency_ms=3,
        )


@pytest.fixture(autouse=True)
def _no_real_client(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(settings: object) -> object:
        raise AssertionError("the real OpenAI client must not be constructed in tests")

    monkeypatch.setattr(model_judge, "get_citation_judge_client", forbidden)
    monkeypatch.setattr(openai_client, "get_citation_judge_client", forbidden)


def test_disabled_by_default_reports_not_run() -> None:
    section = model_judge.run(offline_context(**CONFIGURED))
    assert section.status == "not_run" and "disabled" in (section.reason or "")
    assert section.cases == []


def test_enabled_without_credentials_reports_not_run() -> None:
    section = model_judge.run(offline_context(eval_model_enabled=True))
    assert section.status == "not_run" and "llm_not_configured" in (section.reason or "")


def test_not_run_judge_does_not_make_an_otherwise_passing_ai_suite_fail_or_pass_it() -> None:
    report = run_evaluation(offline_context(), "ai")
    assert report.model_based.status == "not_run"
    assert all(c.case_id.startswith("model.") is False for c in report.cases)


def test_supported_verdicts_pass_and_record_model_metadata() -> None:
    ctx = offline_context(eval_model_enabled=True, **CONFIGURED)
    judge = FakeJudge()
    ctx.judge_factory = lambda: judge
    section = model_judge.run(ctx)
    assert section.status == "completed"
    assert section.model_name == "judge-model-2026" and section.prompt_version
    assert section.cases and all(c.status == "pass" for c in section.cases)
    # Only accepted claims are judged, each with just the evidence it cites.
    first = judge.requests[0]
    assert {e.evidence_id for e in first.cited_evidence} <= {"MTR-000001", "ANOM-000001"}


def test_unsupported_verdict_fails() -> None:
    ctx = offline_context(eval_model_enabled=True, **CONFIGURED)
    ctx.judge_factory = lambda: FakeJudge("unsupported")
    section = model_judge.run(ctx)
    assert section.cases and all(c.status == "fail" for c in section.cases)


def test_partial_support_is_not_a_pass() -> None:
    ctx = offline_context(eval_model_enabled=True, **CONFIGURED)
    ctx.judge_factory = lambda: FakeJudge("partially_supported")
    assert all(c.status == "fail" for c in model_judge.run(ctx).cases)


def test_provider_errors_are_errors_and_flag_partial_failure() -> None:
    ctx = offline_context(eval_model_enabled=True, **CONFIGURED)
    ctx.judge_factory = lambda: FakeJudge(error=LLMTimeoutError("timed out"))
    section = model_judge.run(ctx)
    assert section.status == "error"
    assert {c.status for c in section.cases} == {"error"}
    report = run_evaluation(ctx, "ai")
    assert report.partial_failure


def test_judge_calls_emit_log_only_traces(caplog: pytest.LogCaptureFixture) -> None:
    import logging  # noqa: PLC0415

    caplog.set_level(logging.INFO)
    ctx = offline_context(eval_model_enabled=True, **CONFIGURED)
    ctx.judge_factory = lambda: FakeJudge()
    section = model_judge.run(ctx)

    calls = [r for r in caplog.records if r.getMessage() == "llm.call"]
    assert len(calls) == len(section.cases) > 0
    assert {r.__dict__["operation"] for r in calls} == {"citation_judge_eval"}
    assert all(r.__dict__["persisted"] is False for r in calls)


def test_failed_judge_calls_emit_error_traces(caplog: pytest.LogCaptureFixture) -> None:
    import logging  # noqa: PLC0415

    caplog.set_level(logging.INFO)
    ctx = offline_context(eval_model_enabled=True, **CONFIGURED)
    ctx.judge_factory = lambda: FakeJudge(error=LLMTimeoutError("timed out", latency_ms=12))
    model_judge.run(ctx)
    calls = [r for r in caplog.records if r.getMessage() == "llm.call"]
    assert calls and all(r.__dict__["error_code"] == "LLM_TIMEOUT" for r in calls)
    assert all(r.__dict__["latency_ms"] == 12 for r in calls)
