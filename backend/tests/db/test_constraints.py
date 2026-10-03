"""Uniqueness, CHECK, enum and foreign-key behaviour enforced by the database."""

from datetime import timedelta
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    AnomalyContributor,
    Approval,
    BriefClaim,
    LLMTrace,
)
from app.models.enums import (
    ApprovalDecision,
    ClaimType,
    ClaimValidationStatus,
    TraceStatus,
)
from tests.db import factories
from tests.db.factories import T0

pytestmark = pytest.mark.db


def assert_rejected(session: Session, *objs: Any) -> None:
    with pytest.raises(IntegrityError), session.begin_nested():
        session.add_all(objs)
        session.flush()


@pytest.fixture
def base(db_session: Session) -> tuple[int, int]:
    c, t = factories.customer(), factories.team()
    db_session.add_all([c, t])
    db_session.flush()
    return c.id, t.id


def test_duplicate_customer_ref_rejected(db_session: Session) -> None:
    first = factories.customer()
    db_session.add(first)
    db_session.flush()
    assert_rejected(db_session, factories.customer(customer_ref=first.customer_ref))


def test_duplicate_team_key_rejected(db_session: Session) -> None:
    first = factories.team()
    db_session.add(first)
    db_session.flush()
    assert_rejected(db_session, factories.team(team_key=first.team_key))


def test_duplicate_ticket_ref_rejected(db_session: Session, base: tuple[int, int]) -> None:
    first = factories.ticket(*base)
    db_session.add(first)
    db_session.flush()
    assert_rejected(db_session, factories.ticket(*base, ticket_ref=first.ticket_ref))


@pytest.mark.parametrize("score", [Decimal("1.5"), Decimal("-1.01"), Decimal("1.001")])
def test_impossible_sentiment_rejected(
    db_session: Session, base: tuple[int, int], score: Decimal
) -> None:
    assert_rejected(db_session, factories.ticket(*base, sentiment_score=score))


@pytest.mark.parametrize("score", [Decimal("-1"), Decimal("0"), Decimal("1")])
def test_boundary_sentiment_accepted(
    db_session: Session, base: tuple[int, int], score: Decimal
) -> None:
    db_session.add(factories.ticket(*base, sentiment_score=score))
    db_session.flush()


def test_resolved_before_created_rejected(db_session: Session, base: tuple[int, int]) -> None:
    assert_rejected(db_session, factories.ticket(*base, resolved_at=T0 - timedelta(minutes=1)))


def test_resolved_at_created_accepted(db_session: Session, base: tuple[int, int]) -> None:
    db_session.add(factories.ticket(*base, resolved_at=T0))
    db_session.flush()


def test_ticket_requires_created_at(db_session: Session, base: tuple[int, int]) -> None:
    t = factories.ticket(*base)
    t.created_at = None  # type: ignore[assignment]
    assert_rejected(db_session, t)


def test_ticket_event_time_round_trips_tz_aware(db_session: Session, base: tuple[int, int]) -> None:
    t = factories.ticket(*base)
    db_session.add(t)
    db_session.flush()
    db_session.expire(t)
    assert t.created_at == T0
    assert t.created_at.utcoffset() == timedelta(0)


@pytest.mark.parametrize(
    "overrides",
    [
        {"sla_target_minutes": 0},
        {"first_response_minutes": -1},
        {"resolution_minutes": -5},
    ],
)
def test_ticket_numeric_checks(
    db_session: Session, base: tuple[int, int], overrides: dict[str, Any]
) -> None:
    assert_rejected(db_session, factories.ticket(*base, **overrides))


def test_ticket_foreign_keys_enforced(db_session: Session) -> None:
    assert_rejected(db_session, factories.ticket(999_999, 999_999))


def test_ticket_enum_rejects_invalid_value_at_database(
    db_session: Session, base: tuple[int, int]
) -> None:
    db_session.add(factories.ticket(*base))
    db_session.flush()
    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.execute(text("UPDATE tickets SET priority = 'p9'"))


def test_invalid_action_status_rejected_at_database(db_session: Session) -> None:
    b = factories.brief()
    db_session.add(b)
    db_session.flush()
    a = factories.action(b.id)
    db_session.add(a)
    db_session.flush()
    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.execute(text("UPDATE proposed_actions SET status = 'teleported'"))


def test_unknown_action_type_rejected_at_database(db_session: Session) -> None:
    b = factories.brief()
    db_session.add(b)
    db_session.flush()
    db_session.add(factories.action(b.id))
    db_session.flush()
    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.execute(text("UPDATE proposed_actions SET action_type = 'delete_everything'"))


def test_orphan_contributor_rejected(db_session: Session) -> None:
    assert_rejected(db_session, factories.contributor(db_session, anomaly_id=999_999))


def test_orphan_action_rejected(db_session: Session) -> None:
    assert_rejected(db_session, factories.action(999_999))


def test_orphan_approval_rejected(db_session: Session) -> None:
    assert_rejected(
        db_session,
        Approval(
            action_id=999_999,
            decision=ApprovalDecision.APPROVED,
            reviewer="Operations Manager",
            decided_at=T0,
        ),
    )


def test_contributor_rank_must_be_positive(db_session: Session) -> None:
    snap = factories.metric_snapshot(db_session)
    db_session.add(snap)
    db_session.flush()
    an = factories.anomaly(db_session, snap.id)
    db_session.add(an)
    db_session.flush()
    assert_rejected(db_session, factories.contributor(db_session, an.id, rank=0))


def test_metric_window_and_sample_size_checks(db_session: Session) -> None:
    assert_rejected(
        db_session, factories.metric_snapshot(db_session, window_end=T0 - timedelta(hours=1))
    )
    assert_rejected(db_session, factories.metric_snapshot(db_session, sample_size=-1))


def test_deleting_anomaly_cascades_to_contributors(db_session: Session) -> None:
    snap = factories.metric_snapshot(db_session)
    db_session.add(snap)
    db_session.flush()
    an = factories.anomaly(db_session, snap.id)
    db_session.add(an)
    db_session.flush()
    db_session.add(factories.contributor(db_session, an.id))
    db_session.flush()

    db_session.execute(text("DELETE FROM anomalies WHERE id = :id"), {"id": an.id})
    db_session.expire_all()

    assert db_session.scalars(select(AnomalyContributor)).all() == []


def test_deleting_referenced_metric_snapshot_is_blocked(db_session: Session) -> None:
    snap = factories.metric_snapshot(db_session)
    db_session.add(snap)
    db_session.flush()
    db_session.add(factories.anomaly(db_session, snap.id))
    db_session.flush()

    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.execute(text("DELETE FROM metric_snapshots WHERE id = :id"), {"id": snap.id})


def test_deleting_brief_with_action_is_blocked(db_session: Session) -> None:
    b = factories.brief()
    db_session.add(b)
    db_session.flush()
    db_session.add(factories.action(b.id))
    db_session.flush()

    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.execute(text("DELETE FROM briefs WHERE id = :id"), {"id": b.id})


def test_deleting_brief_cascades_claims_and_nulls_traces(db_session: Session) -> None:
    b = factories.brief()
    db_session.add(b)
    db_session.flush()
    db_session.add(
        BriefClaim(
            brief_id=b.id,
            ordinal=1,
            claim_type=ClaimType.OBSERVATION,
            text="Volume rose.",
            evidence_ids_json=["MTR-000001"],
            validation_status=ClaimValidationStatus.PENDING,
            validation_errors_json=[],
        )
    )
    trace = LLMTrace(
        brief_id=b.id,
        operation="generate_brief",
        model_name="test-model",
        latency_ms=10,
        status=TraceStatus.SUCCESS,
    )
    db_session.add(trace)
    db_session.flush()

    db_session.execute(text("DELETE FROM briefs WHERE id = :id"), {"id": b.id})
    db_session.expire_all()

    assert db_session.scalars(select(BriefClaim)).all() == []
    assert db_session.get(LLMTrace, trace.id).brief_id is None  # type: ignore[union-attr]


def test_claim_ordinal_unique_per_brief(db_session: Session) -> None:
    b = factories.brief()
    db_session.add(b)
    db_session.flush()

    def claim() -> BriefClaim:
        return BriefClaim(
            brief_id=b.id,
            ordinal=1,
            claim_type=ClaimType.INFERENCE,
            text="x",
            evidence_ids_json=[],
            validation_status=ClaimValidationStatus.PENDING,
            validation_errors_json=[],
        )

    db_session.add(claim())
    db_session.flush()
    assert_rejected(db_session, claim())


def test_llm_trace_negative_latency_rejected(db_session: Session) -> None:
    assert_rejected(
        db_session,
        LLMTrace(
            operation="op",
            model_name="m",
            latency_ms=-1,
            status=TraceStatus.ERROR,
        ),
    )
