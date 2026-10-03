"""Valid-by-default model builders for tests."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from itertools import count
from typing import Any

from sqlalchemy.orm import Session

from app.models import (
    Anomaly,
    AnomalyContributor,
    Brief,
    Customer,
    Incident,
    MetricSnapshot,
    ProposedAction,
    SupportTeam,
    Ticket,
)
from app.models.enums import (
    ActionStatus,
    ActionType,
    AnomalySeverity,
    AnomalyStatus,
    BriefStatus,
    CustomerTier,
    EvidenceType,
    Product,
    Region,
    TicketCategory,
    TicketChannel,
    TicketPriority,
    TicketStatus,
)
from app.services.evidence_ids import allocate_evidence_id

T0 = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)
_seq = count(1)


def _n() -> int:
    return next(_seq)


def customer(**kw: Any) -> Customer:
    n = _n()
    defaults: dict[str, Any] = {
        "customer_ref": f"CUST-T{n:04d}",
        "name": f"Test Customer {n}",
        "tier": CustomerTier.BUSINESS,
        "region": Region.EMEA,
        "active": True,
    }
    return Customer(**{**defaults, **kw})


def team(**kw: Any) -> SupportTeam:
    n = _n()
    defaults: dict[str, Any] = {"team_key": f"team-t{n}", "name": f"Team {n}"}
    return SupportTeam(**{**defaults, **kw})


def ticket(customer_id: int, support_team_id: int, **kw: Any) -> Ticket:
    n = _n()
    defaults: dict[str, Any] = {
        "ticket_ref": f"TCK-T{n:05d}",
        "customer_id": customer_id,
        "support_team_id": support_team_id,
        "created_at": T0,
        "priority": TicketPriority.P2,
        "status": TicketStatus.OPEN,
        "channel": TicketChannel.EMAIL,
        "category": TicketCategory.BILLING,
        "product": Product.BILLING_API,
        "sla_target_minutes": 240,
        "sla_breached": False,
        "sentiment_score": Decimal("0.250"),
        "escalated": False,
    }
    return Ticket(**{**defaults, **kw})


def incident(session: Session, **kw: Any) -> Incident:
    defaults: dict[str, Any] = {
        "evidence_id": allocate_evidence_id(session, EvidenceType.EVENT),
        "event_type": "deployment",
        "title": "Synthetic deployment",
        "occurred_at": T0,
        "metadata_json": {"version": "1.2.3"},
    }
    return Incident(**{**defaults, **kw})


def metric_snapshot(session: Session, **kw: Any) -> MetricSnapshot:
    defaults: dict[str, Any] = {
        "evidence_id": allocate_evidence_id(session, EvidenceType.METRIC),
        "metric_key": "ticket_volume",
        "analysis_signature": f"test-signature-{_n():06d}",
        "window_start": T0,
        "window_end": T0 + timedelta(hours=24),
        "baseline_start": T0 - timedelta(days=7),
        "baseline_end": T0,
        "dimensions_json": {"product": "billing_api"},
        "value": Decimal("120"),
        "baseline_value": Decimal("40"),
        "change_pct": Decimal("200"),
        "sample_size": 120,
        "provenance_json": {"source": "tickets", "filters": []},
        "computed_at": T0 + timedelta(hours=25),
    }
    return MetricSnapshot(**{**defaults, **kw})


def anomaly(session: Session, metric_snapshot_id: int, **kw: Any) -> Anomaly:
    defaults: dict[str, Any] = {
        "evidence_id": allocate_evidence_id(session, EvidenceType.ANOMALY),
        "metric_snapshot_id": metric_snapshot_id,
        "detector_key": "baseline_ratio",
        "severity": AnomalySeverity.HIGH,
        "score": Decimal("3.5"),
        "threshold_json": {"ratio": 2.0},
        "status": AnomalyStatus.ACTIVE,
        "detected_at": T0 + timedelta(hours=26),
    }
    return Anomaly(**{**defaults, **kw})


def contributor(session: Session, anomaly_id: int, **kw: Any) -> AnomalyContributor:
    defaults: dict[str, Any] = {
        "evidence_id": allocate_evidence_id(session, EvidenceType.SEGMENT),
        "anomaly_id": anomaly_id,
        "dimension_key": "product",
        "segment_value": "billing_api",
        "current_value": Decimal("100"),
        "baseline_value": Decimal("20"),
        "delta_value": Decimal("80"),
        "contribution_pct": Decimal("100"),
        "rank": 1,
        "provenance_json": {"formula": "delta / total_delta"},
    }
    return AnomalyContributor(**{**defaults, **kw})


def brief(**kw: Any) -> Brief:
    defaults: dict[str, Any] = {
        "analysis_window_start": T0,
        "analysis_window_end": T0 + timedelta(hours=24),
        "headline": "Synthetic headline",
        "summary": "Synthetic summary",
        "status": BriefStatus.VALID,
        "model_name": "test-model",
        "validation_errors_json": [],
    }
    return Brief(**{**defaults, **kw})


def action(brief_id: int, **kw: Any) -> ProposedAction:
    defaults: dict[str, Any] = {
        "brief_id": brief_id,
        "action_type": ActionType.OPEN_INVESTIGATION,
        "title": "Investigate billing_api spike",
        "description": "Open an investigation.",
        "rationale": "Volume coincided with a deployment.",
        "evidence_ids_json": ["MTR-000001", "ANOM-000001"],
        "status": ActionStatus.PROPOSED,
    }
    return ProposedAction(**{**defaults, **kw})
