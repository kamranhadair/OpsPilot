"""Repository round-trips: JSONB arrays/provenance, tz-aware UTC, append-only audit log."""

import inspect
from datetime import timedelta

import pytest
from sqlalchemy.orm import Session

from app.models import Approval
from app.models.enums import ActorType, ApprovalDecision
from app.repositories.action import ActionRepository
from app.repositories.audit_log import AuditLogRepository
from app.repositories.brief import BriefRepository
from app.repositories.evidence import (
    AnomalyContributorRepository,
    AnomalyRepository,
    IncidentRepository,
    MetricSnapshotRepository,
)
from tests.db import factories
from tests.db.factories import T0

pytestmark = pytest.mark.db


def test_metric_snapshot_provenance_round_trip(db_session: Session) -> None:
    repo = MetricSnapshotRepository(db_session)
    provenance = {
        "source": "tickets",
        "filters": [{"product": "billing_api"}],
        "nested": {"window": ["2026-01-15", "2026-01-16"], "n": 3},
    }
    snap = repo.add(
        factories.metric_snapshot(
            db_session, provenance_json=provenance, dimensions_json={"product": "billing_api"}
        )
    )
    db_session.expire(snap)

    found = repo.get_by_evidence_id(snap.evidence_id)
    assert found is not None
    assert found.provenance_json == provenance
    assert found.dimensions_json == {"product": "billing_api"}
    assert found.window_end.utcoffset() == timedelta(0)
    assert found.computed_at.tzinfo is not None


def test_zero_baseline_is_representable_without_change_pct(db_session: Session) -> None:
    repo = MetricSnapshotRepository(db_session)
    snap = repo.add(factories.metric_snapshot(db_session, baseline_value=None, change_pct=None))
    db_session.expire(snap)
    found = repo.get(snap.id)
    assert found is not None
    assert found.baseline_value is None
    assert found.change_pct is None


def test_evidence_lookup_misses_return_none(db_session: Session) -> None:
    assert IncidentRepository(db_session).get_by_evidence_id("EVT-999999") is None
    assert AnomalyRepository(db_session).get_by_evidence_id("ANOM-999999") is None


def test_incident_and_contributor_round_trip(db_session: Session) -> None:
    incidents = IncidentRepository(db_session)
    inc = incidents.add(factories.incident(db_session, metadata_json={"tags": ["a", "b"]}))
    db_session.expire(inc)
    assert incidents.get_by_evidence_id(inc.evidence_id).metadata_json == {  # type: ignore[union-attr]
        "tags": ["a", "b"]
    }

    snap = MetricSnapshotRepository(db_session).add(factories.metric_snapshot(db_session))
    an = AnomalyRepository(db_session).add(factories.anomaly(db_session, snap.id))
    seg = AnomalyContributorRepository(db_session).add(
        factories.contributor(db_session, an.id, provenance_json={"formula": "x", "inputs": [1, 2]})
    )
    db_session.expire(seg)
    found = AnomalyContributorRepository(db_session).get_by_evidence_id(seg.evidence_id)
    assert found is not None
    assert found.provenance_json == {"formula": "x", "inputs": [1, 2]}


def test_brief_claim_and_action_evidence_arrays_round_trip(db_session: Session) -> None:
    from app.models import BriefClaim
    from app.models.enums import ClaimType, ClaimValidationStatus

    brief = factories.brief(validation_errors_json=[{"code": "none"}])
    db_session.add(brief)
    db_session.flush()
    ids = ["MTR-000001", "ANOM-000002", "SEG-000003"]
    claim = BriefClaim(
        brief_id=brief.id,
        ordinal=1,
        claim_type=ClaimType.OBSERVATION,
        text="Backlog grew.",
        evidence_ids_json=ids,
        validation_status=ClaimValidationStatus.VALID,
        validation_errors_json=[],
    )
    action = factories.action(brief.id, evidence_ids_json=ids)
    db_session.add_all([claim, action])
    db_session.flush()
    db_session.expire_all()

    assert db_session.get(BriefClaim, claim.id).evidence_ids_json == ids  # type: ignore[union-attr]
    stored = ActionRepository(db_session).get(action.id)
    assert stored is not None
    assert stored.evidence_ids_json == ids
    assert stored.created_at.utcoffset() == timedelta(0)
    assert stored.updated_at.tzinfo is not None
    assert BriefRepository(db_session).get(brief.id).validation_errors_json == [{"code": "none"}]  # type: ignore[union-attr]


def test_optional_json_none_is_sql_null(db_session: Session) -> None:
    brief = factories.brief()
    db_session.add(brief)
    db_session.flush()
    action = factories.action(brief.id)
    db_session.add(action)
    db_session.flush()
    approval = Approval(
        action_id=action.id,
        decision=ApprovalDecision.APPROVED,
        reviewer="Operations Manager",
        decided_at=T0,
        edited_payload_json=None,
    )
    db_session.add(approval)
    db_session.flush()
    from sqlalchemy import text

    is_null = db_session.execute(
        text("SELECT edited_payload_json IS NULL FROM approvals WHERE id = :id"),
        {"id": approval.id},
    ).scalar_one()
    assert is_null is True


def test_audit_log_append_and_list(db_session: Session) -> None:
    repo = AuditLogRepository(db_session)
    repo.append(
        actor_type=ActorType.HUMAN,
        actor_id="Operations Manager",
        event_type="action.approved",
        entity_type="proposed_action",
        entity_id="7",
        payload={"from": "pending_approval", "to": "approved"},
    )
    repo.append(
        actor_type=ActorType.SYSTEM,
        event_type="action.executed",
        entity_type="proposed_action",
        entity_id="7",
    )
    repo.append(
        actor_type=ActorType.SYSTEM,
        event_type="other",
        entity_type="proposed_action",
        entity_id="8",
    )

    entries = repo.list_for_entity("proposed_action", "7")
    assert [e.event_type for e in entries] == ["action.approved", "action.executed"]
    assert entries[0].payload_json == {"from": "pending_approval", "to": "approved"}
    assert entries[1].payload_json == {}
    assert entries[0].created_at.utcoffset() == timedelta(0)


def test_audit_log_repository_is_append_only() -> None:
    public = {n for n, _ in inspect.getmembers(AuditLogRepository, inspect.isfunction)}
    public = {n for n in public if not n.startswith("_")}
    assert public == {"append", "list_for_entity"}
