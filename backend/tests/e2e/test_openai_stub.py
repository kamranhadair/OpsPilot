"""The offline e2e stub speaks the Responses API well enough for the real OpenAI client.

Guards against SDK drift: if an ``openai`` upgrade changes the wire shape, this fails
here instead of inside the Playwright run.
"""

import threading
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest

from app.core.config import Settings
from app.integrations.llm.openai_client import OpenAILLMClient
from app.models.enums import ActionType, ClaimType
from app.schemas.actions import ActionProposalContext, ContextClaim
from app.schemas.evidence import BundleLimits, EvidenceBundle, WindowOut
from tests.e2e.openai_stub import draft_brief, make_server


@pytest.fixture
def stub_settings() -> Iterator[Settings]:
    server = make_server(0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    yield Settings(
        _env_file=None,
        openai_api_key="e2e-dummy",
        openai_model="e2e-stub",
        openai_base_url=f"http://127.0.0.1:{port}/v1",
        openai_max_retries=0,
    )
    server.shutdown()
    server.server_close()


BUNDLE = {
    "anomalies": [
        {
            "evidence_id": "ANOM-000002",
            "metric_evidence_id": "MTR-000010",
            "label": "Ticket volume (category=billing)",
            "explanation": "Ticket volume is 80% above baseline.",
            "severity": "high",
        },
        {
            "evidence_id": "ANOM-000001",
            "metric_evidence_id": "MTR-000009",
            "label": "Backlog",
            "explanation": "Backlog rose.",
            "severity": "medium",
        },
    ],
    "contributors": [
        {
            "evidence_id": "SEG-000003",
            "anomaly_evidence_id": "ANOM-000002",
            "family_key": "region+customer_tier",
            "rank": 1,
            "statement": "EMEA / Enterprise accounts for 70% of the increase.",
        }
    ],
    "related_events": [{"evidence_id": "EVT-000001", "title": "Billing API deployment"}],
}


def test_brief_draft_cites_only_bundle_ids_and_avoids_causation() -> None:
    draft = draft_brief(BUNDLE)
    cited = {i for c in draft["claims"] for i in c["evidence_ids"]}
    assert cited == {"ANOM-000002", "MTR-000010", "SEG-000003", "EVT-000001"}
    event_claim = draft["claims"][-1]["text"]
    assert "coincided" in event_claim and "caused" not in event_claim


def test_real_client_parses_the_stub_brief_and_action(stub_settings: Settings) -> None:
    client = OpenAILLMClient(stub_settings)

    empty = EvidenceBundle.create(
        analysis_window=None,
        metrics=[],
        anomalies=[],
        contributors=[],
        related_events=[],
        excluded=[],
        limits=BundleLimits(
            max_anomalies=5,
            contributors_per_family=3,
            max_related_events=3,
            event_lookback_hours=72,
        ),
    )
    brief = client.generate_brief(empty)
    assert brief.output.claims == []
    assert brief.input_tokens is not None and brief.output_tokens is not None

    window = WindowOut(
        start=datetime(2026, 10, 3, tzinfo=UTC), end=datetime(2026, 10, 4, tzinfo=UTC)
    )
    context = ActionProposalContext(
        brief_id=1,
        analysis_window=window,
        headline="h",
        summary="s",
        claims=[ContextClaim(claim_type=ClaimType.OBSERVATION, text="t", evidence_ids=["ANOM-1"])],
        allowed_action_types=[ActionType.OPEN_INVESTIGATION],
        allowed_evidence_ids=["ANOM-000001", "EVT-000001", "SEG-000001"],
        evidence=[],
    )
    action = client.propose_action(context)
    assert action.output.action_type == "open_investigation"
    assert action.output.evidence_ids == ["ANOM-000001", "SEG-000001", "EVT-000001"]
    assert action.model_name == "e2e-stub"
