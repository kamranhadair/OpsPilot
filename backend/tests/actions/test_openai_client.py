"""``propose_action`` through the real OpenAI client against a mocked HTTP transport."""

import json
from datetime import UTC, datetime

import httpx2
import pytest

from app.integrations.llm.base import LLMMalformedOutputError
from app.integrations.llm.prompts import ACTION_SYSTEM_PROMPT
from app.models.enums import ActionType
from app.schemas.actions import ActionProposalContext
from app.schemas.evidence import WindowOut
from tests.briefs.test_openai_client import _client, _response

PAYLOAD = {
    "action_type": "open_investigation",
    "title": "Investigate billing spike",
    "description": "d",
    "rationale": "r",
    "investigation_steps": ["s"],
    "evidence_ids": ["ANOM-000001"],
}


@pytest.fixture(autouse=True)
def _no_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("time.sleep", lambda _seconds: None)


def _context() -> ActionProposalContext:
    return ActionProposalContext(
        brief_id=1,
        analysis_window=WindowOut(
            start=datetime(2026, 10, 1, tzinfo=UTC), end=datetime(2026, 10, 2, tzinfo=UTC)
        ),
        headline="h",
        summary="s",
        claims=[],
        allowed_action_types=[ActionType.OPEN_INVESTIGATION],
        allowed_evidence_ids=["ANOM-000001"],
        evidence=[],
    )


def test_propose_action_sends_exact_context_and_parses_output() -> None:
    seen: list[dict[str, object]] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(json.loads(request.content))
        return httpx2.Response(200, json=_response(json.dumps(PAYLOAD)))

    context = _context()
    result = _client(handler, openai_model="configured-model").propose_action(context)

    assert result.output.evidence_ids == ["ANOM-000001"]
    assert result.output.action_type == "open_investigation"
    assert (result.input_tokens, result.output_tokens) == (10, 5)
    assert seen[0]["model"] == "configured-model"
    assert seen[0]["input"] == [
        {"role": "system", "content": ACTION_SYSTEM_PROMPT},
        {"role": "user", "content": context.model_dump_json()},
    ]


def test_unknown_action_type_parses_so_policy_can_reject_it() -> None:
    body = json.dumps({**PAYLOAD, "action_type": "open_jira_ticket"})
    result = _client(lambda _r: httpx2.Response(200, json=_response(body))).propose_action(
        _context()
    )
    assert result.output.action_type == "open_jira_ticket"


@pytest.mark.parametrize(
    "payload",
    [
        {**PAYLOAD, "evidence_ids": []},
        {**PAYLOAD, "status": "approved"},
        {k: v for k, v in PAYLOAD.items() if k != "investigation_steps"},
    ],
)
def test_malformed_proposal_is_rejected(payload: dict[str, object]) -> None:
    text = json.dumps(payload)
    with pytest.raises(LLMMalformedOutputError):
        _client(lambda _r: httpx2.Response(200, json=_response(text))).propose_action(_context())
