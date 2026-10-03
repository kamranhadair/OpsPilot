"""Persistence and read paths for anomaly contributors. No business rules live here."""

from collections.abc import Mapping
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import AnomalyContributor, SupportTeam


class ContributorRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_for_anomaly(self, anomaly_id: int) -> list[AnomalyContributor]:
        stmt = (
            select(AnomalyContributor)
            .where(AnomalyContributor.anomaly_id == anomaly_id)
            .order_by(AnomalyContributor.dimension_key, AnomalyContributor.rank)
        )
        return list(self.session.execute(stmt).scalars())

    def insert_if_absent(self, values: Mapping[str, Any]) -> bool:
        """Insert unless (anomaly, dimension, segment) already exists. True if inserted."""
        stmt = (
            insert(AnomalyContributor)
            .values(**values)
            .on_conflict_do_nothing(
                index_elements=[
                    AnomalyContributor.anomaly_id,
                    AnomalyContributor.dimension_key,
                    AnomalyContributor.segment_value,
                ]
            )
            .returning(AnomalyContributor.id)
        )
        return self.session.execute(stmt).scalar() is not None

    def support_team_keys(self) -> list[str]:
        stmt = select(SupportTeam.team_key).order_by(SupportTeam.team_key)
        return list(self.session.execute(stmt).scalars())
