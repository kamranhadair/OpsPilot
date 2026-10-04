"""Persistence primitives for the synthetic demo dataset. No business rules."""

from collections.abc import Sequence
from itertools import batched
from typing import Any

from sqlalchemy import delete, exists, func, insert, select, text
from sqlalchemy.orm import Session

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
from app.models.enums import EvidenceType
from app.services.evidence_ids import EVIDENCE_SEQUENCES

_INSERT_CHUNK = 1000


class DemoDataRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def acquire_lock(self, key: int) -> None:
        """Transaction-scoped advisory lock serialising concurrent seed/reset runs."""
        self.session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})

    # --- reads ---------------------------------------------------------------------

    def team_ids_by_key(self, keys: Sequence[str]) -> dict[str, int]:
        rows = self.session.execute(
            select(SupportTeam.team_key, SupportTeam.id).where(SupportTeam.team_key.in_(keys))
        )
        return {row[0]: row[1] for row in rows}

    def customer_ids_by_prefix(self, prefix: str) -> dict[str, int]:
        rows = self.session.execute(
            select(Customer.customer_ref, Customer.id).where(
                Customer.customer_ref.startswith(prefix, autoescape=True)
            )
        )
        return {row[0]: row[1] for row in rows}

    def count_customers(self, prefix: str) -> int:
        return self.session.execute(
            select(func.count())
            .select_from(Customer)
            .where(Customer.customer_ref.startswith(prefix, autoescape=True))
        ).scalar_one()

    def count_tickets(self, prefix: str) -> int:
        return self.session.execute(
            select(func.count())
            .select_from(Ticket)
            .where(Ticket.ticket_ref.startswith(prefix, autoescape=True))
        ).scalar_one()

    def seed_incidents(self, seed_key: str) -> list[Incident]:
        marker = func.jsonb_extract_path_text(Incident.metadata_json, "seed_key")
        return list(
            self.session.execute(select(Incident).where(marker == seed_key)).scalars().all()
        )

    # --- writes --------------------------------------------------------------------

    def add_teams(self, rows: Sequence[dict[str, Any]]) -> None:
        if rows:
            self.session.execute(insert(SupportTeam), list(rows))

    def add_customers(self, rows: Sequence[dict[str, Any]]) -> None:
        if rows:
            self.session.execute(insert(Customer), list(rows))

    def add_tickets(self, rows: Sequence[dict[str, Any]]) -> None:
        for chunk in batched(rows, _INSERT_CHUNK):
            self.session.execute(insert(Ticket), list(chunk))

    # --- reset ---------------------------------------------------------------------

    def delete_tickets(self, prefix: str) -> int:
        result = self.session.execute(
            delete(Ticket).where(Ticket.ticket_ref.startswith(prefix, autoescape=True))
        )
        return int(result.rowcount)  # type: ignore[attr-defined]

    def delete_customers(self, prefix: str) -> int:
        result = self.session.execute(
            delete(Customer).where(Customer.customer_ref.startswith(prefix, autoescape=True))
        )
        return int(result.rowcount)  # type: ignore[attr-defined]

    def delete_seed_incidents(self, seed_key: str) -> int:
        marker = func.jsonb_extract_path_text(Incident.metadata_json, "seed_key")
        result = self.session.execute(delete(Incident).where(marker == seed_key))
        return int(result.rowcount)  # type: ignore[attr-defined]

    def delete_unreferenced_teams(self, keys: Sequence[str]) -> int:
        in_use = exists().where(Ticket.support_team_id == SupportTeam.id)
        result = self.session.execute(
            delete(SupportTeam).where(SupportTeam.team_key.in_(keys), ~in_use)
        )
        return int(result.rowcount)  # type: ignore[attr-defined]

    def restart_event_sequence_if_no_incidents(self) -> bool:
        """Restart ``EVT-`` numbering, but only when no incident rows remain."""
        return self._restart_sequence_if_empty(EvidenceType.EVENT)

    # --- derived artifacts (Spec 15 demo reset) --------------------------------------

    def delete_derived_artifacts(self) -> dict[str, int]:
        """Delete every row derived from the operational data, in foreign-key order.

        Returns the deleted row count per table. Callers must have checked the
        demo/development environment guard first.
        """
        deleted: dict[str, int] = {}
        for model in _DERIVED_DELETE_ORDER:
            table = model.__table__
            result = self.session.execute(delete(table))
            deleted[table.name] = int(result.rowcount)  # type: ignore[attr-defined]
        return deleted

    def restart_evidence_sequences_if_empty(self) -> list[EvidenceType]:
        """Restart each evidence-ID sequence whose table is empty; returns the restarted types."""
        return [t for t in EVIDENCE_SEQUENCES if self._restart_sequence_if_empty(t)]

    def _restart_sequence_if_empty(self, evidence_type: EvidenceType) -> bool:
        model = _EVIDENCE_TABLES[evidence_type]
        remaining = self.session.execute(select(func.count()).select_from(model)).scalar_one()
        if remaining:
            return False
        # The sequence name comes from a closed, code-owned mapping, never user input.
        sequence = EVIDENCE_SEQUENCES[evidence_type]
        self.session.execute(text(f"ALTER SEQUENCE {sequence} RESTART WITH 1"))
        return True


# Children before parents so no RESTRICT foreign key blocks a delete.
_DERIVED_DELETE_ORDER: tuple[type[Any], ...] = (
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

_EVIDENCE_TABLES: dict[EvidenceType, type[Any]] = {
    EvidenceType.EVENT: Incident,
    EvidenceType.METRIC: MetricSnapshot,
    EvidenceType.ANOMALY: Anomaly,
    EvidenceType.SEGMENT: AnomalyContributor,
}
