"""Evidence Bundle assembly against persisted evidence."""

import json
import re
from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AnomalyContributor, Ticket
from app.models.enums import AnomalyStatus
from app.repositories.anomaly_repository import AnomalyRepository
from app.schemas.evidence import EvidenceBundle, ExclusionReason
from app.services.evidence import assembler as assembler_module
from app.services.evidence.assembler import EvidenceBundleAssembler
from app.services.evidence.resolver import EvidenceResolver
from app.services.metrics.definitions import METRIC_REGISTRY
from tests.contributors.test_language import CAUSAL, strings
from tests.db import factories
from tests.evidence.conftest import END, detect_billing_volume
from tests.metrics.conftest import World

pytestmark = pytest.mark.db


def assemble(session: Session) -> EvidenceBundle:
    return EvidenceBundleAssembler(session, event_lookback_hours=72).assemble()


def reasons(bundle: EvidenceBundle) -> dict[str, ExclusionReason]:
    return {e.evidence_id: e.reason for e in bundle.excluded}


def add_event(session: Session, **kw: Any) -> str:
    row = factories.incident(session, **kw)
    session.add(row)
    session.flush()
    return row.evidence_id


def test_bundle_holds_metrics_anomalies_contributors_and_events(
    volume_world: World, no_incidents: Session
) -> None:
    session = volume_world.session
    anomaly_id = detect_billing_volume(volume_world)
    event_id = add_event(session, occurred_at=END - timedelta(hours=30))

    bundle = assemble(session)

    assert bundle.analysis_window is not None
    assert bundle.analysis_window.current.end == END
    assert {m.metric_key for m in bundle.metrics if m.role == "overview"} <= {
        m.metric_key for m in bundle.metrics
    }
    anomaly = next(a for a in bundle.anomalies if a.evidence_id == anomaly_id)
    assert anomaly.contributor_status == "available"
    assert anomaly.contributor_evidence_ids
    assert {c.anomaly_evidence_id for c in bundle.contributors} >= {anomaly_id}
    assert [e.evidence_id for e in bundle.related_events] == [event_id]
    top = next(c for c in bundle.contributors if c.family_key == "region+customer_tier")
    assert top.segment == {"region": "emea", "customer_tier": "enterprise"}
    assert top.rank == 1 and top.evidence_id.startswith("SEG-")
    # The allow-list is exactly the item IDs, sorted and unique.
    item_ids = [
        i.evidence_id
        for i in (*bundle.metrics, *bundle.anomalies, *bundle.contributors, *bundle.related_events)
    ]
    assert bundle.allowed_evidence_ids == sorted(set(item_ids)) and len(item_ids) == len(
        set(item_ids)
    )


def test_assembly_is_deterministic_and_read_only(
    volume_world: World, no_incidents: Session
) -> None:
    session = volume_world.session
    detect_billing_volume(volume_world)
    add_event(session, occurred_at=END - timedelta(hours=30))
    before = session.scalar(select(AnomalyContributor.id).limit(1))

    first, second = assemble(session), assemble(session)

    assert first == second
    assert first.signature == second.signature
    assert first.model_dump_json() == second.model_dump_json()
    assert session.scalar(select(AnomalyContributor.id).limit(1)) == before


def test_every_allowed_id_resolves_to_persisted_evidence(
    volume_world: World, no_incidents: Session
) -> None:
    session = volume_world.session
    detect_billing_volume(volume_world)
    add_event(session, occurred_at=END - timedelta(hours=30))

    bundle = assemble(session)

    assert bundle.allowed_evidence_ids
    assert EvidenceResolver(session).existing(bundle.allowed_evidence_ids) == set(
        bundle.allowed_evidence_ids
    )
    assert EvidenceResolver(session).existing(["MTR-999999", "nonsense", "SEG-000000"]) == set()


def test_empty_database_gives_an_empty_bundle(clean_db: Session, no_incidents: Session) -> None:
    bundle = assemble(clean_db)

    assert bundle.analysis_window is None
    assert bundle.allowed_evidence_ids == []
    assert bundle.excluded == []


def test_no_anomalies_still_yields_overview_metrics(
    volume_world: World, no_incidents: Session
) -> None:
    session = volume_world.session
    detect_billing_volume(volume_world)
    rows, _ = AnomalyRepository(session).list_with_snapshots(
        severity=None,
        status=AnomalyStatus.ACTIVE,
        metric_key=None,
        start=None,
        end=None,
        limit=200,
        offset=0,
    )
    for anomaly, _snapshot in rows:
        anomaly.status = AnomalyStatus.RESOLVED
    session.flush()

    bundle = assemble(session)

    assert bundle.anomalies == [] and bundle.contributors == []
    assert bundle.metrics and all(m.role == "overview" for m in bundle.metrics)


def test_no_related_events_in_range(volume_world: World, no_incidents: Session) -> None:
    session = volume_world.session
    detect_billing_volume(volume_world)
    add_event(session, occurred_at=END - timedelta(hours=24 + 72 + 1))  # just too early
    add_event(session, occurred_at=END)  # window end is exclusive
    add_event(session, occurred_at=END + timedelta(hours=1))

    assert assemble(session).related_events == []


def test_contributors_not_computed_are_flagged_not_computed(
    volume_world: World, no_incidents: Session
) -> None:
    session = volume_world.session
    anomaly_id = detect_billing_volume(volume_world, compute_contributors=False)

    bundle = assemble(session)

    anomaly = next(a for a in bundle.anomalies if a.evidence_id == anomaly_id)
    assert anomaly.contributor_status == "not_computed"
    assert anomaly.contributor_evidence_ids == []
    assert not any(c.anomaly_evidence_id == anomaly_id for c in bundle.contributors)
    assert session.scalar(select(AnomalyContributor.id).limit(1)) is None  # nothing was written


def test_anomaly_from_a_mismatched_window_is_excluded(
    volume_world: World, no_incidents: Session
) -> None:
    session = volume_world.session
    anomaly_id = detect_billing_volume(volume_world)
    found = AnomalyRepository(session).get_with_snapshot(anomaly_id)
    assert found is not None
    found[1].window_start = found[1].window_start + timedelta(hours=1)
    session.flush()

    bundle = assemble(session)

    assert anomaly_id not in bundle.allowed_evidence_ids
    assert reasons(bundle)[anomaly_id] is ExclusionReason.WINDOW_MISMATCH
    assert not any(c.anomaly_evidence_id == anomaly_id for c in bundle.contributors)


def test_contributor_with_mismatched_provenance_is_excluded(
    volume_world: World, no_incidents: Session
) -> None:
    session = volume_world.session
    anomaly_id = detect_billing_volume(volume_world)
    row = session.scalars(
        select(AnomalyContributor).order_by(AnomalyContributor.evidence_id).limit(1)
    ).one()
    row.provenance_json = {**row.provenance_json, "metric_evidence_id": "MTR-999999"}
    session.flush()

    bundle = assemble(session)

    assert row.evidence_id not in bundle.allowed_evidence_ids
    assert reasons(bundle)[row.evidence_id] is ExclusionReason.WINDOW_MISMATCH
    anomaly = next(a for a in bundle.anomalies if a.evidence_id == anomaly_id)
    assert row.evidence_id not in anomaly.contributor_evidence_ids


def test_stale_metric_definition_version_is_excluded(
    volume_world: World, no_incidents: Session
) -> None:
    session = volume_world.session
    anomaly_id = detect_billing_volume(volume_world)
    found = AnomalyRepository(session).get_with_snapshot(anomaly_id)
    assert found is not None
    provenance = json.loads(json.dumps(found[1].provenance_json))
    provenance["definition"]["version"] += 1
    found[1].provenance_json = provenance
    session.flush()

    bundle = assemble(session)

    assert reasons(bundle)[anomaly_id] is ExclusionReason.STALE_DEFINITION_VERSION
    assert anomaly_id not in bundle.allowed_evidence_ids


def test_anomalies_and_contributors_are_bounded(
    volume_world: World, no_incidents: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = volume_world.session
    detect_billing_volume(volume_world)
    unbounded = assemble(session)
    assert len(unbounded.anomalies) >= 2
    monkeypatch.setattr(assembler_module, "MAX_ANOMALIES", 1)
    monkeypatch.setattr(assembler_module, "CONTRIBUTORS_PER_FAMILY", 1)

    bundle = assemble(session)

    assert len(bundle.anomalies) == 1
    assert ExclusionReason.OVER_LIMIT in reasons(bundle).values()
    assert all(c.rank == 1 for c in bundle.contributors)


def test_unresolvable_ids_are_dropped_with_their_dependents(
    volume_world: World, no_incidents: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = volume_world.session
    anomaly_id = detect_billing_volume(volume_world)
    full = assemble(session)
    trigger = next(a for a in full.anomalies if a.evidence_id == anomaly_id).metric_evidence_id
    real = EvidenceResolver.existing
    monkeypatch.setattr(
        EvidenceResolver,
        "existing",
        lambda self, ids: real(self, ids) - {trigger},
    )

    bundle = assemble(session)

    assert trigger not in bundle.allowed_evidence_ids
    assert anomaly_id not in bundle.allowed_evidence_ids
    assert not any(c.anomaly_evidence_id == anomaly_id for c in bundle.contributors)
    assert reasons(bundle)[trigger] is ExclusionReason.UNRESOLVED
    assert reasons(bundle)[anomaly_id] is ExclusionReason.UNRESOLVED


def test_related_event_is_contextual_with_allow_listed_details_only(
    volume_world: World, no_incidents: Session
) -> None:
    session = volume_world.session
    detect_billing_volume(volume_world)
    event_id = add_event(
        session,
        occurred_at=END - timedelta(hours=30),
        title="Billing API v2.14.0 deployed",
        metadata_json={
            "service": "billing-api",
            "version": "2.14.0",
            "summary": "Synthetic rollout.",
            "dataset_checksum": "deadbeef",
            "seed_key": "secret-seed",
            "ticket_count": 12345,
        },
    )

    bundle = assemble(session)

    event = next(e for e in bundle.related_events if e.evidence_id == event_id)
    assert event.evidence_class == "contextual_event"
    assert event.causal is False and event.relationship == "temporal_proximity"
    assert event.details == {
        "service": "billing-api",
        "version": "2.14.0",
        "summary": "Synthetic rollout.",
    }
    assert event.hours_from_window_start == -6.0
    dumped = bundle.model_dump_json()
    assert "deadbeef" not in dumped and "secret-seed" not in dumped
    assert event_id not in {c.evidence_id for c in (*bundle.metrics, *bundle.anomalies)}
    texts = strings(event.model_dump(mode="json"))
    assert not [t for t in texts if CAUSAL.search(t)]


def test_bundle_has_no_raw_ticket_data_secrets_or_large_lists(
    volume_world: World, no_incidents: Session
) -> None:
    session = volume_world.session
    detect_billing_volume(volume_world)
    add_event(session, occurred_at=END - timedelta(hours=30))
    refs = list(session.scalars(select(Ticket.ticket_ref)))
    assert len(refs) >= 100  # the world really holds many tickets

    bundle = assemble(session)
    dumped = bundle.model_dump_json()

    assert not [ref for ref in refs if ref in dumped]
    assert not re.search(r'"(ticket_ref|subject|body|customer_ref|message)"', dumped)
    assert not re.search(r"postgresql|password|api[_-]?key|secret|SELECT ", dumped, re.IGNORECASE)
    assert len(bundle.metrics) <= len(METRIC_REGISTRY) + bundle.limits.max_anomalies
    assert len(bundle.anomalies) <= bundle.limits.max_anomalies
    assert len(bundle.related_events) <= bundle.limits.max_related_events
    assert len(bundle.allowed_evidence_ids) < 100
    assert len(dumped) < 200_000


def test_bundle_text_uses_no_causal_language(volume_world: World, no_incidents: Session) -> None:
    session = volume_world.session
    detect_billing_volume(volume_world)
    add_event(session, occurred_at=END - timedelta(hours=30), title="Billing API deployed")

    bundle = assemble(session)

    prose = [
        text
        for item in (*bundle.anomalies, *bundle.contributors, *bundle.related_events)
        for text in strings(item.model_dump(mode="json"))
    ]
    assert prose
    assert [t for t in prose if CAUSAL.search(t)] == []
