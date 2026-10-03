"""Shared evidence-ID allocator.

Externally visible evidence IDs (``EVT-``, ``MTR-``, ``ANOM-``, ``SEG-``) come
from one PostgreSQL sequence per type, never from table primary keys.

Sequences are non-transactional: a rolled-back transaction leaves a gap in the
numbering. Resetting sequences for deterministic seeding belongs to the
controlled reset workflow (Spec 03), not here.
"""

import re

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.enums import EvidenceType

EVIDENCE_SEQUENCES: dict[EvidenceType, str] = {
    EvidenceType.EVENT: "evidence_evt_seq",
    EvidenceType.METRIC: "evidence_mtr_seq",
    EvidenceType.ANOMALY: "evidence_anom_seq",
    EvidenceType.SEGMENT: "evidence_seg_seq",
}

_ID_PATTERN = re.compile(r"^(EVT|MTR|ANOM|SEG)-(\d{6,})$")


def format_evidence_id(evidence_type: EvidenceType, number: int) -> str:
    """Format a sequence value as a prefixed evidence ID, e.g. ``MTR-000042``."""
    return f"{evidence_type.value}-{number:06d}"


def parse_evidence_id(evidence_id: str) -> tuple[EvidenceType, int] | None:
    """Return ``(type, number)`` for a well-formed ID, or ``None``."""
    match = _ID_PATTERN.match(evidence_id)
    if match is None:
        return None
    return EvidenceType(match.group(1)), int(match.group(2))


def allocate_evidence_id(session: Session, evidence_type: EvidenceType) -> str:
    """Allocate the next unique evidence ID of ``evidence_type``."""
    # The sequence name comes from a closed, code-owned mapping, never user input.
    sequence = EVIDENCE_SEQUENCES[evidence_type]
    number = session.execute(text(f"SELECT nextval('{sequence}')")).scalar_one()
    return format_evidence_id(evidence_type, int(number))
