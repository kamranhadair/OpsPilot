"""Persistence and read paths for anomalies. No business rules live here."""

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from sqlalchemy import case, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import Anomaly, MetricSnapshot
from app.models.enums import AnomalySeverity, AnomalyStatus

# Presentation ordering only (most severe first); severity itself is decided by the rules.
_SEVERITY_ORDER = case(
    {
        AnomalySeverity.CRITICAL: 0,
        AnomalySeverity.HIGH: 1,
        AnomalySeverity.MEDIUM: 2,
        AnomalySeverity.LOW: 3,
    },
    value=Anomaly.severity,
    else_=4,
)


class AnomalyRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_snapshot_and_detector(
        self, metric_snapshot_id: int, detector_key: str
    ) -> Anomaly | None:
        stmt = select(Anomaly).where(
            Anomaly.metric_snapshot_id == metric_snapshot_id,
            Anomaly.detector_key == detector_key,
        )
        return self.session.execute(stmt).scalars().first()

    def insert_if_absent(self, values: Mapping[str, Any]) -> bool:
        """Insert unless (snapshot, detector) already exists. Returns True if inserted."""
        stmt = (
            insert(Anomaly)
            .values(**values)
            .on_conflict_do_nothing(
                index_elements=[Anomaly.metric_snapshot_id, Anomaly.detector_key]
            )
            .returning(Anomaly.id)
        )
        return self.session.execute(stmt).scalar() is not None

    def get_with_snapshot(self, evidence_id: str) -> tuple[Anomaly, MetricSnapshot] | None:
        stmt = (
            select(Anomaly, MetricSnapshot)
            .join(MetricSnapshot, MetricSnapshot.id == Anomaly.metric_snapshot_id)
            .where(Anomaly.evidence_id == evidence_id)
        )
        row = self.session.execute(stmt).first()
        return None if row is None else (row[0], row[1])

    def list_with_snapshots(
        self,
        *,
        severity: AnomalySeverity | None,
        status: AnomalyStatus | None,
        metric_key: str | None,
        start: datetime | None,
        end: datetime | None,
        limit: int,
        offset: int,
    ) -> tuple[list[tuple[Anomaly, MetricSnapshot]], int]:
        """A page of anomalies (newest window first, most severe first) and the total count."""
        conditions = []
        if severity is not None:
            conditions.append(Anomaly.severity == severity)
        if status is not None:
            conditions.append(Anomaly.status == status)
        if metric_key is not None:
            conditions.append(MetricSnapshot.metric_key == metric_key)
        if start is not None:
            conditions.append(MetricSnapshot.window_end >= start)
        if end is not None:
            conditions.append(MetricSnapshot.window_end <= end)

        base = (
            select(Anomaly, MetricSnapshot)
            .join(MetricSnapshot, MetricSnapshot.id == Anomaly.metric_snapshot_id)
            .where(*conditions)
        )
        total = self.session.execute(
            select(func.count())
            .select_from(Anomaly)
            .join(MetricSnapshot, MetricSnapshot.id == Anomaly.metric_snapshot_id)
            .where(*conditions)
        ).scalar_one()
        stmt = (
            base.order_by(MetricSnapshot.window_end.desc(), _SEVERITY_ORDER, Anomaly.evidence_id)
            .limit(limit)
            .offset(offset)
        )
        rows = [(row[0], row[1]) for row in self.session.execute(stmt).all()]
        return rows, int(total)
