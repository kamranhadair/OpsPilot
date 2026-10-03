"""Evidence-ID allocation. Never assumes sequence start values or rollback resets."""

import re

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.enums import EvidenceType
from app.services.evidence_ids import allocate_evidence_id, parse_evidence_id
from tests.db import factories

pytestmark = pytest.mark.db


@pytest.mark.parametrize("evidence_type", list(EvidenceType))
def test_allocated_ids_are_prefixed_distinct_and_increasing(
    db_session: Session, evidence_type: EvidenceType
) -> None:
    ids = [allocate_evidence_id(db_session, evidence_type) for _ in range(5)]

    assert all(re.fullmatch(rf"{evidence_type.value}-\d{{6,}}", i) for i in ids)
    assert len(set(ids)) == 5
    numbers = []
    for evidence_id in ids:
        parsed = parse_evidence_id(evidence_id)
        assert parsed is not None
        assert parsed[0] is evidence_type
        numbers.append(parsed[1])
    assert numbers == sorted(numbers)
    assert len(set(numbers)) == 5


def test_duplicate_evidence_id_is_rejected(db_session: Session) -> None:
    first = factories.incident(db_session)
    db_session.add(first)
    db_session.flush()

    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.add(factories.incident(db_session, evidence_id=first.evidence_id))


def test_wrong_prefix_is_rejected(db_session: Session) -> None:
    snapshot = factories.metric_snapshot(db_session)
    db_session.add(snapshot)
    db_session.flush()

    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.add(factories.anomaly(db_session, snapshot.id, evidence_id="MTR-000999"))


@pytest.mark.parametrize("bad", ["EVT-", "evt-000001", "MTR-000001"])
def test_incident_rejects_non_event_prefix(db_session: Session, bad: str) -> None:
    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.add(factories.incident(db_session, evidence_id=bad))
