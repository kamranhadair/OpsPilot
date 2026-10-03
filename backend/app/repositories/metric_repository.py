"""Persistence and read paths for metric snapshots. No business rules live here."""

from collections.abc import Collection, Mapping
from datetime import datetime
from typing import Any

from sqlalchemy import exists, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import MetricSnapshot, SupportTeam, Ticket


class MetricRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    # --- source data -----------------------------------------------------------------

    def ticket_time_bounds(self) -> tuple[datetime, datetime] | None:
        """``(min, max)`` of ``tickets.created_at``, or None when there are no tickets."""
        row = self.session.execute(
            select(func.min(Ticket.created_at), func.max(Ticket.created_at))
        ).one()
        if row[0] is None or row[1] is None:
            return None
        return row[0], row[1]

    def team_key_exists(self, team_key: str) -> bool:
        stmt = select(exists().where(SupportTeam.team_key == team_key))
        return bool(self.session.execute(stmt).scalar())

    # --- snapshots -------------------------------------------------------------------

    def get_by_signature(self, signature: str) -> MetricSnapshot | None:
        stmt = select(MetricSnapshot).where(MetricSnapshot.analysis_signature == signature)
        return self.session.execute(stmt).scalars().first()

    def insert_if_absent(self, values: Mapping[str, Any]) -> bool:
        """Insert unless the analysis signature already exists. Returns True if inserted."""
        stmt = (
            insert(MetricSnapshot)
            .values(**values)
            .on_conflict_do_nothing(index_elements=[MetricSnapshot.analysis_signature])
            .returning(MetricSnapshot.id)
        )
        return self.session.execute(stmt).scalar() is not None

    def latest_window_end(
        self, dimensions: Mapping[str, str], metric_keys: Collection[str]
    ) -> datetime | None:
        stmt = select(func.max(MetricSnapshot.window_end)).where(
            MetricSnapshot.dimensions_json == dict(dimensions),
            MetricSnapshot.metric_key.in_(metric_keys),
        )
        return self.session.execute(stmt).scalar()

    def list_at_window(
        self, window_end: datetime, dimensions: Mapping[str, str], metric_keys: Collection[str]
    ) -> list[MetricSnapshot]:
        stmt = (
            select(MetricSnapshot)
            .where(
                MetricSnapshot.window_end == window_end,
                MetricSnapshot.dimensions_json == dict(dimensions),
                MetricSnapshot.metric_key.in_(metric_keys),
            )
            .order_by(MetricSnapshot.metric_key, MetricSnapshot.id)
        )
        return list(self.session.execute(stmt).scalars())

    def series(
        self,
        metric_key: str,
        definition_version: int,
        dimensions: Mapping[str, str],
        start: datetime | None,
        end: datetime | None,
        limit: int,
    ) -> list[MetricSnapshot]:
        """The most recent ``limit`` snapshots in range, returned oldest first."""
        version = MetricSnapshot.provenance_json[("definition", "version")].as_integer()
        stmt = select(MetricSnapshot).where(
            MetricSnapshot.metric_key == metric_key,
            MetricSnapshot.dimensions_json == dict(dimensions),
            version == definition_version,
        )
        if start is not None:
            stmt = stmt.where(MetricSnapshot.window_end >= start)
        if end is not None:
            stmt = stmt.where(MetricSnapshot.window_end <= end)
        stmt = stmt.order_by(MetricSnapshot.window_end.desc()).limit(limit)
        rows = list(self.session.execute(stmt).scalars())
        rows.reverse()
        return rows
