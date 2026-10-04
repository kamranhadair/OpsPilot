"""Demo reset: clears derived artifacts, reseeds deterministically, refuses outside demo envs."""

from collections.abc import Callable

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.integrations.investigations.mock import get_investigation_adapters
from app.models import Anomaly, AnomalyContributor, Incident, MetricSnapshot, Ticket
from app.schemas.actions import ApproveActionRequest
from app.scripts.demo import EXIT_OK, EXIT_REFUSED, main
from app.services.actions.approval_service import ActionApprovalService
from app.services.actions.execution_service import ActionExecutionService
from app.services.actions.proposer import ActionProposalService
from app.services.analysis.orchestrator import AnalysisOrchestrator
from app.services.demo.reset import reset_and_seed
from app.services.demo_data.seeder import EnvironmentRefusedError
from tests.demo.conftest import (
    DERIVED_MODELS,
    LLM_SETTINGS,
    PROD_SETTINGS,
    StubActionClient,
    StubBriefClient,
    count,
    make_settings,
)

pytestmark = pytest.mark.db


def full_run(session: Session) -> None:
    """Analysis, brief, proposal, human approval and mock execution: every derived table."""
    result = AnalysisOrchestrator(session, LLM_SETTINGS, lambda: StubBriefClient()).run()
    assert result.brief.brief_id is not None
    action = ActionProposalService(session, LLM_SETTINGS, lambda: StubActionClient()).propose(
        result.brief.brief_id
    )
    ActionApprovalService(session).approve(
        action.id, ApproveActionRequest(reviewer="Operations Manager")
    )
    ActionExecutionService(session, get_investigation_adapters(LLM_SETTINGS)).execute(action.id)


def evidence_ids(session: Session) -> list[str]:
    ids: list[str] = []
    for model in (Incident, MetricSnapshot, Anomaly, AnomalyContributor):
        ids += sorted(session.execute(select(model.evidence_id)).scalars())
    return ids


def test_reset_after_a_full_run_leaves_the_pre_analysis_state(seeded: Session) -> None:
    full_run(seeded)
    assert all(count(seeded, m) > 0 for m in DERIVED_MODELS)
    tickets = count(seeded, Ticket)

    result = reset_and_seed(seeded, make_settings())

    assert {m.__tablename__: count(seeded, m) for m in DERIVED_MODELS} == dict.fromkeys(
        (m.__tablename__ for m in DERIVED_MODELS), 0
    )
    assert sum(result.derived_deleted.values()) > 0
    assert result.seed.action == "seeded"
    assert count(seeded, Ticket) == tickets
    assert [i.evidence_id for i in seeded.execute(select(Incident)).scalars()] == ["EVT-000001"]


def test_reset_is_idempotent_and_analysis_ids_are_reproducible(seeded: Session) -> None:
    first = reset_and_seed(seeded, make_settings())
    AnalysisOrchestrator(seeded, make_settings()).run()
    first_ids = evidence_ids(seeded)

    second = reset_and_seed(seeded, make_settings())
    assert second.seed.checksum == first.seed.checksum
    assert second.seed.tickets == first.seed.tickets
    assert second.seed.customers == first.seed.customers
    AnalysisOrchestrator(seeded, make_settings()).run()

    assert evidence_ids(seeded) == first_ids


def test_reset_refuses_outside_demo_environments_and_touches_nothing(seeded: Session) -> None:
    AnalysisOrchestrator(seeded, make_settings()).run()
    before = count(seeded, MetricSnapshot)

    with pytest.raises(EnvironmentRefusedError):
        reset_and_seed(seeded, PROD_SETTINGS)

    assert count(seeded, MetricSnapshot) == before > 0


def test_cli_reset_and_analyze(
    seeded: Session,
    connection_session_factory: Callable[[], Session],
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["reset"], connection_session_factory, make_settings()) == EXIT_OK
    assert "seeded" in capsys.readouterr().out

    assert main(["analyze"], connection_session_factory, make_settings()) == EXIT_OK
    out = capsys.readouterr().out
    assert "ANOM-" in out
    assert "Brief not_configured: LLM_NOT_CONFIGURED" in out


def test_cli_refuses_outside_demo_environments(
    seeded: Session,
    connection_session_factory: Callable[[], Session],
    capsys: pytest.CaptureFixture[str],
) -> None:
    for command in ("reset", "analyze"):
        assert main([command], connection_session_factory, PROD_SETTINGS) == EXIT_REFUSED
        assert "Refused" in capsys.readouterr().err
    assert count(seeded, Ticket) > 0
    assert count(seeded, MetricSnapshot) == 0


def test_cli_analyze_without_data_is_refused(
    clean_db: Session, connection_session_factory: Callable[[], Session]
) -> None:
    assert main(["analyze"], connection_session_factory, make_settings()) == EXIT_REFUSED
