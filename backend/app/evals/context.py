"""Evaluation run context: the rollback-only session, settings and seed-state check.

The evaluator never changes the canonical dataset. Every database read and the few
approval-boundary writes happen inside one outer transaction that is always rolled
back; services that ``commit()`` only release a SAVEPOINT inside it. The one lasting
side effect is that rolled-back inserts leave gaps in the ``briefs`` and
``proposed_actions`` primary-key sequences (PostgreSQL sequences are not transactional).
"""

from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.integrations.investigations.base import InvestigationAdapter
from app.integrations.llm.base import CitationJudgeClient
from app.models.enums import ActionType
from app.repositories.demo_data import DemoDataRepository
from app.schemas.evaluations import SeedInfo
from app.services.demo_data.config import DEFAULT_CONFIG, SEED_VERSION
from app.services.demo_data.generator import generate_dataset
from app.services.demo_data.seeder import detect_seed_state

# Not-run reasons for cases that depend on the seeded demo dataset.
SEED_MISSING = "seed_missing"
SEED_VERSION_MISMATCH = "seed_version_mismatch"
CASES_STALE = "case_seed_version_mismatch"


@dataclass
class EvalContext:
    settings: Settings
    seed: SeedInfo
    # Bound to a connection inside an outer transaction the caller rolls back, or None
    # when the database is unavailable (database-backed cases then report not_run).
    session: Session | None
    rollback_only: bool
    adapters: Mapping[ActionType, InvestigationAdapter] = field(default_factory=dict)
    judge_factory: Callable[[], CitationJudgeClient] | None = None
    cases_dir: Path | None = None
    db_unavailable_reason: str | None = None


@contextmanager
def rollback_session(engine: Engine) -> Iterator[Session]:
    """A session whose work is always discarded, even when a service commits."""
    connection = engine.connect()
    outer = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        outer.rollback()
        connection.close()


def unavailable_seed(case_version: str) -> SeedInfo:
    """Seed info when the database could not be inspected."""
    return SeedInfo(
        expected_version=SEED_VERSION,
        case_version=case_version,
        observed_state="unavailable",
        observed_version=None,
        matches=False,
    )


def inspect_seed(session: Session, case_version: str) -> SeedInfo:
    """Compare the database's demo seed with the code's and the cases' seed version."""
    state, incidents = detect_seed_state(
        DemoDataRepository(session), DEFAULT_CONFIG, generate_dataset(DEFAULT_CONFIG)
    )
    observed_version = None
    if incidents:
        raw = incidents[0].metadata_json.get("seed_version")
        observed_version = None if raw is None else str(raw)
    return SeedInfo(
        expected_version=SEED_VERSION,
        case_version=case_version,
        observed_state=state.value,
        observed_version=observed_version,
        matches=state.value == "complete" and case_version == SEED_VERSION,
    )


def seed_gate(ctx: EvalContext, case_seed_version: str) -> str | None:
    """Why seeded golden cases cannot run, or None when they can."""
    if ctx.session is None:
        return ctx.db_unavailable_reason or "database_unavailable"
    if case_seed_version != SEED_VERSION:
        return (
            f"{CASES_STALE}: cases were written for seed {case_seed_version!r}, "
            f"code generates seed {SEED_VERSION!r}"
        )
    if ctx.seed.observed_state == "empty":
        return f"{SEED_MISSING}: the demo dataset is not seeded"
    if ctx.seed.observed_state != "complete":
        return (
            f"{SEED_VERSION_MISMATCH}: database seed is {ctx.seed.observed_state} "
            f"(version {ctx.seed.observed_version!r}, expected {SEED_VERSION!r})"
        )
    return None
