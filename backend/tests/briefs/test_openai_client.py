"""OpenAIBriefClient against a mocked HTTP transport: no network, no real key."""

import json
import logging

import httpx2
import pytest

from app.integrations.llm.base import (
    LLMMalformedOutputError,
    LLMNotConfiguredError,
    LLMProviderError,
    LLMRateLimitedError,
    LLMTimeoutError,
)
from app.integrations.llm.openai_client import OpenAIBriefClient
from app.integrations.llm.prompts import BRIEF_SYSTEM_PROMPT
from app.schemas.evidence import BundleLimits, EvidenceBundle
from tests.briefs.conftest import make_settings

SECRET = "sk-test-secret-value"
PAYLOAD = {
    "headline": "h",
    "summary": "s",
    "claims": [{"claim_type": "observation", "text": "t", "evidence_ids": ["MTR-000001"]}],
    "attention_items": [],
}


@pytest.fixture(autouse=True)
def _no_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("time.sleep", lambda _seconds: None)


def _bundle() -> EvidenceBundle:
    return EvidenceBundle.create(
        analysis_window=None,
        metrics=[],
        anomalies=[],
        contributors=[],
        related_events=[],
        excluded=[],
        limits=BundleLimits(
            max_anomalies=5,
            contributors_per_family=3,
            max_related_events=5,
            event_lookback_hours=72,
        ),
    )


def _response(text: str, model: str = "served-model") -> dict[str, object]:
    return {
        "id": "resp_1",
        "object": "response",
        "created_at": 0,
        "model": model,
        "status": "completed",
        "output": [
            {
                "type": "message",
                "id": "msg_1",
                "role": "assistant",
                "status": "completed",
                "content": [{"type": "output_text", "text": text, "annotations": []}],
            }
        ],
        "parallel_tool_calls": True,
        "tool_choice": "auto",
        "tools": [],
        "usage": {
            "input_tokens": 10,
            "output_tokens": 5,
            "total_tokens": 15,
            "input_tokens_details": {"cached_tokens": 0},
            "output_tokens_details": {"reasoning_tokens": 0},
        },
    }


def _client(handler: object, **settings: object) -> OpenAIBriefClient:
    transport = httpx2.MockTransport(handler)  # type: ignore[arg-type]
    return OpenAIBriefClient(
        make_settings(openai_api_key=SECRET, **settings),
        http_client=httpx2.Client(transport=transport),
    )


def test_success_parses_output_and_sends_exact_bundle() -> None:
    seen: list[dict[str, object]] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(json.loads(request.content))
        return httpx2.Response(200, json=_response(json.dumps(PAYLOAD)))

    bundle = _bundle()
    result = _client(handler, openai_model="configured-model").generate_brief(bundle)

    assert result.output.claims[0].evidence_ids == ["MTR-000001"]
    assert (result.input_tokens, result.output_tokens) == (10, 5)
    assert result.model_name == "served-model"
    assert len(seen) == 1
    assert seen[0]["model"] == "configured-model"  # model name comes from settings
    messages = seen[0]["input"]
    assert messages == [
        {"role": "system", "content": BRIEF_SYSTEM_PROMPT},
        {"role": "user", "content": bundle.model_dump_json()},
    ]
    assert "text" in seen[0]  # structured-output schema was requested


def test_rate_limit_retries_are_bounded_then_typed() -> None:
    calls = 0

    def handler(_request: httpx2.Request) -> httpx2.Response:
        nonlocal calls
        calls += 1
        return httpx2.Response(429, json={"error": {"message": "slow", "type": "rate_limit"}})

    with pytest.raises(LLMRateLimitedError):
        _client(handler, openai_max_retries=2).generate_brief(_bundle())
    assert calls == 3  # first attempt + 2 retries, never more


def test_zero_retries_means_one_attempt() -> None:
    calls = 0

    def handler(_request: httpx2.Request) -> httpx2.Response:
        nonlocal calls
        calls += 1
        return httpx2.Response(500, json={"error": {"message": "boom"}})

    with pytest.raises(LLMProviderError):
        _client(handler, openai_max_retries=0).generate_brief(_bundle())
    assert calls == 1


def test_timeout_is_typed() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ReadTimeout("slow", request=request)

    with pytest.raises(LLMTimeoutError):
        _client(handler, openai_max_retries=0).generate_brief(_bundle())


@pytest.mark.parametrize(
    "text",
    [
        "not json at all",
        json.dumps(
            {**PAYLOAD, "claims": [{"claim_type": "observation", "text": "t", "evidence_ids": []}]}
        ),
        json.dumps({**PAYLOAD, "surprise": 1}),
    ],
)
def test_malformed_structured_output_is_rejected_without_retry(text: str) -> None:
    calls = 0

    def handler(_request: httpx2.Request) -> httpx2.Response:
        nonlocal calls
        calls += 1
        return httpx2.Response(200, json=_response(text))

    with pytest.raises(LLMMalformedOutputError):
        _client(handler).generate_brief(_bundle())
    assert calls == 1


def test_refusal_is_malformed_output() -> None:
    body = _response("")
    body["output"] = [
        {
            "type": "message",
            "id": "msg_1",
            "role": "assistant",
            "status": "completed",
            "content": [{"type": "refusal", "refusal": "I can't help with that."}],
        }
    ]
    with pytest.raises(LLMMalformedOutputError):
        _client(lambda _r: httpx2.Response(200, json=body)).generate_brief(_bundle())


def test_secret_never_appears_in_errors_or_logs(caplog: pytest.LogCaptureFixture) -> None:
    def handler(_request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(401, json={"error": {"message": "bad key"}})

    with caplog.at_level(logging.DEBUG), pytest.raises(LLMProviderError) as info:
        _client(handler, openai_max_retries=0).generate_brief(_bundle())
    assert SECRET not in info.value.message
    assert SECRET not in caplog.text


@pytest.mark.parametrize("overrides", [{"openai_api_key": None}, {"openai_model": None}])
def test_construction_without_credentials_is_not_configured(overrides: dict[str, object]) -> None:
    with pytest.raises(LLMNotConfiguredError):
        OpenAIBriefClient(make_settings(**overrides))
