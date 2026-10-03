"""Contributor output describes share of observed change and never asserts a cause."""

import re
from typing import Any

import pytest
from sqlalchemy.orm import Session

from app.schemas.contributors import ContributorAnalysisResponse
from app.services.contributors.service import ContributorService
from tests.contributors.conftest import billing_anomaly_id
from tests.contributors.test_demo_scenario import billing_contributors
from tests.metrics.conftest import World

pytestmark = pytest.mark.db

CAUSAL = re.compile(
    r"\b(cause[sd]?|causing|causation|causal|because|due to|driven by|drove|driving|"
    r"led to|leads to|root cause|result of|resulted|responsible for|blame)\b",
    re.IGNORECASE,
)


def strings(value: Any) -> list[str]:
    """Every string value in a JSON-like structure (keys are schema names, not prose)."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for v in value.values() for s in strings(v)]
    if isinstance(value, list):
        return [s for v in value for s in strings(v)]
    return []


def assert_non_causal(response: ContributorAnalysisResponse) -> None:
    texts = strings(response.model_dump(mode="json"))
    assert texts
    offenders = [t for t in texts if CAUSAL.search(t)]
    assert offenders == []


def test_causal_detector_catches_causal_wording() -> None:
    for sentence in ("EMEA caused the spike", "driven by EMEA", "due to the deploy", "Root cause"):
        assert CAUSAL.search(sentence)
    assert not CAUSAL.search("accounts for 85.0% of the observed positive change")


def test_count_output_uses_no_causal_language(volume_world: World) -> None:
    session = volume_world.session
    response = ContributorService(session).compute(billing_anomaly_id(session, "ticket_volume"))
    assert_non_causal(response)


def test_rate_output_uses_no_causal_language(breach_world: World) -> None:
    session = breach_world.session
    response = ContributorService(session).compute(billing_anomaly_id(session, "sla_breach_rate"))
    assert_non_causal(response)


def test_demo_output_uses_no_causal_language(demo_session: Session) -> None:
    assert_non_causal(billing_contributors(demo_session, "ticket_volume"))
    assert_non_causal(billing_contributors(demo_session, "sla_breach_rate"))
