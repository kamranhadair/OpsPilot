"""Thin generic persistence primitives. No business rules live here."""

from collections.abc import Collection
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.base import Base


class BaseRepository[ModelT: Base]:
    model: type[ModelT]

    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, entity: ModelT) -> ModelT:
        self.session.add(entity)
        self.session.flush()
        return entity

    def get(self, entity_id: int) -> ModelT | None:
        return self.session.get(self.model, entity_id)

    def get_by(self, **filters: Any) -> ModelT | None:
        stmt = select(self.model).filter_by(**filters)
        return self.session.execute(stmt).scalars().first()


class EvidenceRepositoryMixin:
    """Lookup by the externally visible evidence ID for evidence-bearing models."""

    session: Session
    model: Any

    def get_by_evidence_id(self, evidence_id: str) -> Any | None:
        stmt = select(self.model).where(self.model.evidence_id == evidence_id)
        return self.session.execute(stmt).scalars().first()

    def existing_evidence_ids(self, evidence_ids: Collection[str]) -> set[str]:
        """The subset of ``evidence_ids`` that exist in this model's table."""
        if not evidence_ids:
            return set()
        stmt = select(self.model.evidence_id).where(self.model.evidence_id.in_(evidence_ids))
        return set(self.session.execute(stmt).scalars())
