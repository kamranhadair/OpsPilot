"""Check that evidence IDs exist in their persisted sources.

Only the existence check lives here (Spec 08). The typed resolution envelope and its
API belong to Spec 10.
"""

from collections.abc import Iterable

from sqlalchemy.orm import Session

from app.models.enums import EvidenceType
from app.repositories.evidence import (
    AnomalyContributorRepository,
    AnomalyRepository,
    IncidentRepository,
    MetricSnapshotRepository,
)
from app.services.evidence_ids import parse_evidence_id


class EvidenceResolver:
    def __init__(self, session: Session) -> None:
        self._repos = {
            EvidenceType.EVENT: IncidentRepository(session),
            EvidenceType.METRIC: MetricSnapshotRepository(session),
            EvidenceType.ANOMALY: AnomalyRepository(session),
            EvidenceType.SEGMENT: AnomalyContributorRepository(session),
        }

    def existing(self, evidence_ids: Iterable[str]) -> set[str]:
        """The IDs that are well formed and present in persisted evidence."""
        grouped: dict[EvidenceType, set[str]] = {}
        for evidence_id in evidence_ids:
            parsed = parse_evidence_id(evidence_id)
            if parsed is not None:
                grouped.setdefault(parsed[0], set()).add(evidence_id)
        found: set[str] = set()
        for evidence_type, ids in grouped.items():
            found |= self._repos[evidence_type].existing_evidence_ids(ids)
        return found
