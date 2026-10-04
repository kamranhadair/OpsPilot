"""Demo reset: clear derived artifacts and the synthetic dataset, then reseed (Spec 15).

The caller owns the transaction, as with the seeder: a failure at any step rolls the
database back to its pre-reset state. Only demo/development/test environments may run
it, and there is deliberately no HTTP endpoint for it.

After a reset the database is in the known pre-analysis state: the seeded tickets,
customers, teams and one ``EVT-`` deployment event; no snapshots, anomalies,
contributors, briefs, actions, approvals, executions, LLM traces or audit rows. Every
evidence-ID sequence restarts, so a fresh analysis allocates the same IDs every time.
"""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.enums import EvidenceType
from app.repositories.demo_data import DemoDataRepository
from app.services.demo_data.config import SEED_LOCK_KEY
from app.services.demo_data.seeder import (
    EnvironmentRefusedError,
    ResetResult,
    SeedResult,
    reset_demo_data,
    seed_demo_data,
)


@dataclass(frozen=True)
class DemoResetResult:
    derived_deleted: dict[str, int]
    reset: ResetResult
    sequences_restarted: list[EvidenceType]
    seed: SeedResult


def reset_and_seed(session: Session, settings: Settings) -> DemoResetResult:
    """Return the database to the deterministic pre-analysis demo state.

    Raises:
        EnvironmentRefusedError: outside a demo/development environment; nothing is touched.
    """
    if not settings.is_demo_environment:
        raise EnvironmentRefusedError(
            f"Refusing to reset the demo: ENVIRONMENT={settings.environment!r} is not a "
            "demo/development environment."
        )
    repo = DemoDataRepository(session)
    repo.acquire_lock(SEED_LOCK_KEY)
    derived = repo.delete_derived_artifacts()
    reset = reset_demo_data(session, settings=settings)
    restarted = repo.restart_evidence_sequences_if_empty()
    seed = seed_demo_data(session, settings=settings)
    return DemoResetResult(
        derived_deleted=derived, reset=reset, sequences_restarted=restarted, seed=seed
    )
