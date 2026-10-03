"""Repositories for evidence-bearing tables."""

from datetime import datetime

from sqlalchemy import select

from app.models.evidence import Anomaly, AnomalyContributor, Incident, MetricSnapshot
from app.repositories.base import BaseRepository, EvidenceRepositoryMixin


class IncidentRepository(EvidenceRepositoryMixin, BaseRepository[Incident]):
    model = Incident

    def list_between(self, start: datetime, end: datetime) -> list[Incident]:
        """Incidents with ``start <= occurred_at < end``, newest first (ties by evidence ID)."""
        stmt = (
            select(Incident)
            .where(Incident.occurred_at >= start, Incident.occurred_at < end)
            .order_by(Incident.occurred_at.desc(), Incident.evidence_id)
        )
        return list(self.session.execute(stmt).scalars())


class MetricSnapshotRepository(EvidenceRepositoryMixin, BaseRepository[MetricSnapshot]):
    model = MetricSnapshot


class AnomalyRepository(EvidenceRepositoryMixin, BaseRepository[Anomaly]):
    model = Anomaly


class AnomalyContributorRepository(EvidenceRepositoryMixin, BaseRepository[AnomalyContributor]):
    model = AnomalyContributor
