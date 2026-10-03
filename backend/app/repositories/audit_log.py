"""Append-only audit log access.

Deliberately exposes no update or delete operation.
"""

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import ActorType
from app.models.observability import AuditLog


class AuditLogRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def append(
        self,
        *,
        actor_type: ActorType,
        event_type: str,
        entity_type: str,
        entity_id: str,
        actor_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> AuditLog:
        entry = AuditLog(
            actor_type=actor_type,
            actor_id=actor_id,
            event_type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            payload_json=payload or {},
        )
        self.session.add(entry)
        self.session.flush()
        return entry

    def list_for_entity(self, entity_type: str, entity_id: str) -> list[AuditLog]:
        stmt = (
            select(AuditLog)
            .where(AuditLog.entity_type == entity_type, AuditLog.entity_id == entity_id)
            .order_by(AuditLog.id)
        )
        return list(self.session.execute(stmt).scalars())
