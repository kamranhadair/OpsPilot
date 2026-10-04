"""Fixtures for Spec 15 demo tests: the seeded dataset plus stub-backed fake model clients."""

from collections.abc import Callable, Iterator

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.integrations.llm.base import ActionLLMResult, BriefLLMResult
from app.models import (
    ActionExecution,
    Anomaly,
    AnomalyContributor,
    Approval,
    AuditLog,
    Brief,
    BriefClaim,
    Customer,
    Incident,
    LLMTrace,
    MetricSnapshot,
    ProposedAction,
    SupportTeam,
    Ticket,
)
from app.schemas.actions import ActionProposalContext, ActionProposalOutput
from app.schemas.briefs import BriefDraftOutput
from app.schemas.evidence import EvidenceBundle
from app.services.demo_data.seeder import seed_demo_data
from tests.dashboard.conftest import (  # noqa: F401  (re-exported fixtures)
    clean_db,
    connection_session_factory,
    db_client,
    db_session,
    engine,
    test_db_url,
)
from tests.e2e.openai_stub import draft_action, draft_brief

DERIVED_MODELS = (
    ActionExecution,
    Approval,
    LLMTrace,
    ProposedAction,
    BriefClaim,
    Brief,
    AuditLog,
    AnomalyContributor,
    Anomaly,
    MetricSnapshot,
)


def make_settings(**overrides: object) -> Settings:
    """Settings that ignore any local .env so tests never see a real key."""
    values: dict[str, object] = {"environment": "development", **overrides}
    return Settings(_env_file=None, **values)  # type: ignore[arg-type]


LLM_SETTINGS = make_settings(openai_api_key="test-key-not-real", openai_model="test-model")
NO_LLM_SETTINGS = make_settings()
PROD_SETTINGS = make_settings(environment="production")


class StubBriefClient:
    """Answers like the offline e2e stub: a grounded brief built from the bundle."""

    def __init__(self) -> None:
        self.calls = 0

    def generate_brief(self, bundle: EvidenceBundle) -> BriefLLMResult:
        self.calls += 1
        output = BriefDraftOutput.model_validate(draft_brief(bundle.model_dump(mode="json")))
        return BriefLLMResult(
            output=output, model_name="test-model", input_tokens=10, output_tokens=5, latency_ms=1
        )


class StubActionClient:
    def propose_action(self, context: ActionProposalContext) -> ActionLLMResult:
        output = ActionProposalOutput.model_validate(draft_action(context.model_dump(mode="json")))
        return ActionLLMResult(
            output=output, model_name="test-model", input_tokens=10, output_tokens=5, latency_ms=1
        )


def count(session: Session, model: type) -> int:
    return session.execute(select(func.count()).select_from(model)).scalar_one()


@pytest.fixture
def seeded(db_session: Session) -> Session:  # noqa: F811
    """Empty every demo/derived table, then seed the deterministic dataset."""
    for model in (*DERIVED_MODELS, Ticket, Customer, Incident, SupportTeam):
        db_session.execute(model.__table__.delete())  # type: ignore[attr-defined]
    db_session.flush()
    seed_demo_data(db_session, settings=make_settings())
    return db_session


SessionFactory = Callable[[], Session]


@pytest.fixture
def stub_brief() -> Iterator[StubBriefClient]:
    yield StubBriefClient()
