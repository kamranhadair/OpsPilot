"""Seed / reset orchestration for the synthetic demo dataset.

The caller owns the transaction: functions here never commit, so a failure at any
point rolls back to the pre-run state. A transaction-scoped advisory lock
serialises concurrent runs.

Seeding only writes raw operational data and one ``EVT-*`` deployment event. It
never writes metric snapshots, anomalies, contributors, briefs, or actions.
"""

from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models import Incident
from app.models.enums import EvidenceType
from app.repositories.demo_data import DemoDataRepository
from app.repositories.evidence import IncidentRepository
from app.services.demo_data.config import DEFAULT_CONFIG, SEED_LOCK_KEY, TEAMS, DemoDataConfig
from app.services.demo_data.generator import generate_dataset
from app.services.demo_data.records import DemoDataset, dataset_checksum
from app.services.evidence_ids import allocate_evidence_id


class DemoDataError(Exception):
    """Base class for expected, user-facing seed/reset refusals."""


class EnvironmentRefusedError(DemoDataError):
    """Seeding/reset attempted outside a demo/development environment."""


class SeedRefusedError(DemoDataError):
    """Existing data conflicts with the requested seed; ``--reset`` is required."""


class SeedState(StrEnum):
    EMPTY = "empty"
    COMPLETE = "complete"
    INCONSISTENT = "inconsistent"


@dataclass(frozen=True)
class SeedResult:
    action: str  # "seeded" | "already_seeded"
    teams: int
    customers: int
    tickets: int
    incidents: int
    checksum: str


@dataclass(frozen=True)
class ResetResult:
    tickets: int
    customers: int
    incidents: int
    teams: int
    event_sequence_restarted: bool


def _require_demo_environment(settings: Settings, operation: str) -> None:
    if not settings.is_demo_environment:
        raise EnvironmentRefusedError(
            f"Refusing to {operation} demo data: ENVIRONMENT={settings.environment!r} is not a "
            "demo/development environment."
        )


def _expected_counts(dataset: DemoDataset) -> tuple[int, int]:
    return len(dataset.customers), len(dataset.tickets)


def detect_seed_state(
    repo: DemoDataRepository, config: DemoDataConfig, dataset: DemoDataset
) -> tuple[SeedState, list[Incident]]:
    customers = repo.count_customers(config.customer_ref_prefix)
    tickets = repo.count_tickets(config.ticket_ref_prefix)
    incidents = repo.seed_incidents(config.seed_key)

    if customers == 0 and tickets == 0 and not incidents:
        return SeedState.EMPTY, incidents
    expected_customers, expected_tickets = _expected_counts(dataset)
    if (
        customers == expected_customers
        and tickets == expected_tickets
        and len(incidents) == 1
        and incidents[0].metadata_json.get("seed_version") == config.seed_version
    ):
        return SeedState.COMPLETE, incidents
    return SeedState.INCONSISTENT, incidents


def seed_demo_data(
    session: Session,
    config: DemoDataConfig = DEFAULT_CONFIG,
    settings: Settings | None = None,
) -> SeedResult:
    """Seed the demo dataset. Idempotent for an already-complete same-version seed."""
    _require_demo_environment(settings or get_settings(), "seed")
    repo = DemoDataRepository(session)
    repo.acquire_lock(SEED_LOCK_KEY)

    dataset = generate_dataset(config)
    checksum = dataset_checksum(dataset)
    state, existing = detect_seed_state(repo, config, dataset)

    if state is SeedState.COMPLETE:
        stored = str(existing[0].metadata_json.get("dataset_checksum", checksum))
        return SeedResult(
            "already_seeded",
            teams=len(dataset.teams),
            customers=len(dataset.customers),
            tickets=len(dataset.tickets),
            incidents=1,
            checksum=stored,
        )
    if state is SeedState.INCONSISTENT:
        raise SeedRefusedError(
            "Demo data already exists but does not match this seed version "
            f"({config.seed_version!r}) or is incomplete. Run with --reset to rebuild it."
        )

    team_ids = repo.team_ids_by_key([t.team_key for t in dataset.teams])
    repo.add_teams(
        [
            {"team_key": team.team_key, "name": team.name}
            for team in dataset.teams
            if team.team_key not in team_ids
        ]
    )
    team_ids = repo.team_ids_by_key([t.team_key for t in dataset.teams])

    repo.add_customers(
        [
            {
                "customer_ref": c.customer_ref,
                "name": c.name,
                "tier": c.tier,
                "region": c.region,
                "active": True,
            }
            for c in dataset.customers
        ]
    )
    customer_ids = repo.customer_ids_by_prefix(config.customer_ref_prefix)

    repo.add_tickets(
        [
            {
                "ticket_ref": t.ticket_ref,
                "customer_id": customer_ids[t.customer_ref],
                "support_team_id": team_ids[t.team_key],
                "created_at": t.created_at,
                "resolved_at": t.resolved_at,
                "priority": t.priority,
                "status": t.status,
                "channel": t.channel,
                "category": t.category,
                "product": t.product,
                "first_response_minutes": t.first_response_minutes,
                "resolution_minutes": t.resolution_minutes,
                "sla_target_minutes": t.sla_target_minutes,
                "sla_breached": t.sla_breached,
                "sentiment_score": t.sentiment_score,
                "escalated": t.escalated,
                "subject": t.subject,
            }
            for t in dataset.tickets
        ]
    )

    event = dataset.incident
    IncidentRepository(session).add(
        Incident(
            evidence_id=allocate_evidence_id(session, EvidenceType.EVENT),
            event_type=event.event_type,
            title=event.title,
            occurred_at=event.occurred_at,
            product=event.product,
            metadata_json={
                **event.metadata,
                "dataset_checksum": checksum,
                "ticket_count": len(dataset.tickets),
                "customer_count": len(dataset.customers),
            },
        )
    )
    return SeedResult(
        "seeded",
        teams=len(dataset.teams),
        customers=len(dataset.customers),
        tickets=len(dataset.tickets),
        incidents=1,
        checksum=checksum,
    )


def reset_demo_data(
    session: Session,
    config: DemoDataConfig = DEFAULT_CONFIG,
    settings: Settings | None = None,
) -> ResetResult:
    """Delete only known demo rows. Refuses outside demo/development environments."""
    _require_demo_environment(settings or get_settings(), "reset")
    repo = DemoDataRepository(session)
    repo.acquire_lock(SEED_LOCK_KEY)

    tickets = repo.delete_tickets(config.ticket_ref_prefix)
    customers = repo.delete_customers(config.customer_ref_prefix)
    incidents = repo.delete_seed_incidents(config.seed_key)
    teams = repo.delete_unreferenced_teams([t.team_key for t in TEAMS])
    restarted = repo.restart_event_sequence_if_no_incidents()
    return ResetResult(
        tickets=tickets,
        customers=customers,
        incidents=incidents,
        teams=teams,
        event_sequence_restarted=restarted,
    )
