"""Persistence behaviour of the demo seeder and CLI. Needs the PostgreSQL test DB."""

from collections.abc import Callable
from typing import Any

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import (
    Anomaly,
    AnomalyContributor,
    AuditLog,
    Brief,
    BriefClaim,
    Customer,
    Incident,
    MetricSnapshot,
    ProposedAction,
    SupportTeam,
    Ticket,
)
from app.repositories.demo_data import DemoDataRepository
from app.scripts.seed_demo import EXIT_ERROR, EXIT_OK, EXIT_REFUSED, main
from app.services.demo_data.config import DEFAULT_CONFIG, SEED_KEY
from app.services.demo_data.generator import generate_dataset
from app.services.demo_data.records import dataset_checksum
from app.services.demo_data.seeder import (
    EnvironmentRefusedError,
    SeedRefusedError,
    reset_demo_data,
    seed_demo_data,
)
from tests.db import factories

pytestmark = pytest.mark.db


def count(session: Session, model: Any) -> int:
    return session.execute(select(func.count()).select_from(model)).scalar_one()


def demo_counts(session: Session) -> tuple[int, int, int]:
    return (
        count(session, Customer),
        count(session, Ticket),
        count(session, Incident),
    )


@pytest.fixture(autouse=True)
def _clean_demo_tables(db_session: Session) -> None:
    """Start every test from an empty domain (the outer transaction rolls back)."""
    for model in (Ticket, Customer, Incident, SupportTeam):
        db_session.execute(model.__table__.delete())  # type: ignore[attr-defined]
    db_session.flush()


def test_seed_populates_dataset_and_stores_checksum(
    db_session: Session, dev_settings: Settings
) -> None:
    dataset = generate_dataset()
    result = seed_demo_data(db_session, settings=dev_settings)

    assert result.action == "seeded"
    assert count(db_session, Customer) == len(dataset.customers)
    assert count(db_session, Ticket) == len(dataset.tickets)
    assert count(db_session, SupportTeam) == 4
    incident = db_session.execute(select(Incident)).scalar_one()
    assert incident.metadata_json["dataset_checksum"] == dataset_checksum(dataset)
    assert result.checksum == dataset_checksum(dataset)


def test_deployment_event_is_a_single_evt_record(
    db_session: Session, dev_settings: Settings
) -> None:
    seed_demo_data(db_session, settings=dev_settings)
    incident = db_session.execute(select(Incident)).scalar_one()

    assert incident.evidence_id.startswith("EVT-")
    assert incident.event_type == "deployment"
    assert incident.occurred_at == DEFAULT_CONFIG.deployment_at
    assert incident.metadata_json["seed_key"] == SEED_KEY


def test_repeated_seed_is_idempotent(db_session: Session, dev_settings: Settings) -> None:
    first = seed_demo_data(db_session, settings=dev_settings)
    before = demo_counts(db_session)
    second = seed_demo_data(db_session, settings=dev_settings)

    assert second.action == "already_seeded"
    assert second.checksum == first.checksum
    assert demo_counts(db_session) == before


def test_seed_creates_no_derived_records(db_session: Session, dev_settings: Settings) -> None:
    seed_demo_data(db_session, settings=dev_settings)
    for model in (
        MetricSnapshot,
        Anomaly,
        AnomalyContributor,
        Brief,
        BriefClaim,
        ProposedAction,
        AuditLog,
    ):
        assert count(db_session, model) == 0, model.__name__


def test_other_seed_version_is_refused_without_changes(
    db_session: Session, dev_settings: Settings
) -> None:
    seed_demo_data(db_session, settings=dev_settings)
    db_session.execute(
        text(
            "UPDATE incidents SET metadata_json = jsonb_set(metadata_json, '{seed_version}', "
            "'\"0\"')"
        )
    )
    before = demo_counts(db_session)

    with pytest.raises(SeedRefusedError, match="--reset"):
        seed_demo_data(db_session, settings=dev_settings)
    assert demo_counts(db_session) == before


def test_colliding_non_demo_ticket_ref_is_refused(
    db_session: Session, dev_settings: Settings
) -> None:
    customer = factories.customer()
    team = factories.team()
    db_session.add_all([customer, team])
    db_session.flush()
    db_session.add(factories.ticket(customer.id, team.id, ticket_ref="DEMO-TCK-000007"))
    db_session.flush()

    with pytest.raises(SeedRefusedError, match="--reset"):
        seed_demo_data(db_session, settings=dev_settings)
    assert count(db_session, Ticket) == 1


def test_interrupted_seed_rolls_back_to_zero_demo_rows(
    db_session: Session, dev_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    def explode(self: DemoDataRepository, rows: Any) -> None:
        raise RuntimeError("simulated interruption")

    monkeypatch.setattr(DemoDataRepository, "add_tickets", explode)
    with pytest.raises(RuntimeError), db_session.begin_nested():
        seed_demo_data(db_session, settings=dev_settings)

    assert count(db_session, Customer) == 0
    assert count(db_session, Ticket) == 0
    assert count(db_session, SupportTeam) == 0
    assert count(db_session, Incident) == 0


def test_reset_then_seed_reproduces_dataset_and_keeps_non_demo_rows(
    db_session: Session, dev_settings: Settings
) -> None:
    keeper_customer, keeper_team = factories.customer(), factories.team()
    db_session.add_all([keeper_customer, keeper_team, factories.incident(db_session)])
    db_session.flush()
    db_session.add(factories.ticket(keeper_customer.id, keeper_team.id))
    db_session.flush()

    first = seed_demo_data(db_session, settings=dev_settings)
    reset = reset_demo_data(db_session, settings=dev_settings)
    assert reset.tickets == first.tickets
    assert reset.incidents == 1

    assert count(db_session, Ticket) == 1
    assert count(db_session, Customer) == 1
    assert count(db_session, Incident) == 1  # the non-demo incident survives
    assert db_session.execute(select(SupportTeam.team_key)).scalars().all() == [
        keeper_team.team_key
    ]

    second = seed_demo_data(db_session, settings=dev_settings)
    assert second.checksum == first.checksum


def test_reset_restarts_event_numbering_when_no_incidents_remain(
    db_session: Session, dev_settings: Settings
) -> None:
    seed_demo_data(db_session, settings=dev_settings)
    reset = reset_demo_data(db_session, settings=dev_settings)
    assert reset.event_sequence_restarted is True

    seed_demo_data(db_session, settings=dev_settings)
    assert db_session.execute(select(Incident.evidence_id)).scalar_one() == "EVT-000001"


def test_reset_is_blocked_outside_demo_environments(
    db_session: Session, dev_settings: Settings, prod_settings: Settings
) -> None:
    seed_demo_data(db_session, settings=dev_settings)
    before = demo_counts(db_session)

    with pytest.raises(EnvironmentRefusedError, match="production"):
        reset_demo_data(db_session, settings=prod_settings)
    with pytest.raises(EnvironmentRefusedError):
        seed_demo_data(db_session, settings=prod_settings)
    assert demo_counts(db_session) == before


# --- CLI --------------------------------------------------------------------------


def test_cli_seeds_then_is_a_noop_then_resets(
    db_session: Session,
    connection_session_factory: Callable[[], Session],
    dev_settings: Settings,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main([], connection_session_factory, dev_settings) == EXIT_OK
    assert "seeded" in capsys.readouterr().out
    before = demo_counts(db_session)

    assert main([], connection_session_factory, dev_settings) == EXIT_OK
    assert "already_seeded" in capsys.readouterr().out
    assert demo_counts(db_session) == before

    assert main(["--reset"], connection_session_factory, dev_settings) == EXIT_OK
    assert "Reset: removed" in capsys.readouterr().out
    assert demo_counts(db_session) == before


def test_cli_reset_refuses_in_production_with_exit_2(
    db_session: Session,
    connection_session_factory: Callable[[], Session],
    dev_settings: Settings,
    prod_settings: Settings,
    capsys: pytest.CaptureFixture[str],
) -> None:
    main([], connection_session_factory, dev_settings)
    before = demo_counts(db_session)
    capsys.readouterr()

    assert main(["--reset"], connection_session_factory, prod_settings) == EXIT_REFUSED
    assert "Refused" in capsys.readouterr().err
    assert demo_counts(db_session) == before


def test_cli_reports_unexpected_errors_without_traceback(
    connection_session_factory: Callable[[], Session],
    dev_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def explode(self: DemoDataRepository, rows: Any) -> None:
        raise RuntimeError("secret-connection-detail")

    monkeypatch.setattr(DemoDataRepository, "add_tickets", explode)
    assert main([], connection_session_factory, dev_settings) == EXIT_ERROR
    err = capsys.readouterr().err
    assert "RuntimeError" in err and "secret-connection-detail" not in err
