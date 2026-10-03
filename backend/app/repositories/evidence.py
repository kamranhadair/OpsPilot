"""Repositories for evidence-bearing tables."""

from app.models.evidence import Anomaly, AnomalyContributor, Incident, MetricSnapshot
from app.repositories.base import BaseRepository, EvidenceRepositoryMixin


class IncidentRepository(EvidenceRepositoryMixin, BaseRepository[Incident]):
    model = Incident


class MetricSnapshotRepository(EvidenceRepositoryMixin, BaseRepository[MetricSnapshot]):
    model = MetricSnapshot


class AnomalyRepository(EvidenceRepositoryMixin, BaseRepository[Anomaly]):
    model = Anomaly


class AnomalyContributorRepository(EvidenceRepositoryMixin, BaseRepository[AnomalyContributor]):
    model = AnomalyContributor
