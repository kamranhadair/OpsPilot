"""Pure, persistence-free records produced by the generator.

Records refer to customers/teams by ref/key, never by database id, so the whole
dataset can be generated and verified without a database.
"""

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from app.models.enums import (
    CustomerTier,
    Product,
    Region,
    TicketCategory,
    TicketChannel,
    TicketPriority,
    TicketStatus,
)


@dataclass(frozen=True)
class TeamRecord:
    team_key: str
    name: str


@dataclass(frozen=True)
class CustomerRecord:
    customer_ref: str
    name: str
    tier: CustomerTier
    region: Region


@dataclass(frozen=True)
class TicketRecord:
    ticket_ref: str
    customer_ref: str
    team_key: str
    created_at: datetime
    resolved_at: datetime | None
    priority: TicketPriority
    status: TicketStatus
    channel: TicketChannel
    category: TicketCategory
    product: Product
    first_response_minutes: int | None
    resolution_minutes: int | None
    sla_target_minutes: int
    sla_breached: bool
    sentiment_score: Decimal
    escalated: bool
    subject: str


@dataclass(frozen=True)
class IncidentRecord:
    event_type: str
    title: str
    occurred_at: datetime
    product: Product | None
    metadata: dict[str, Any]


@dataclass(frozen=True)
class DemoDataset:
    teams: tuple[TeamRecord, ...]
    customers: tuple[CustomerRecord, ...]
    tickets: tuple[TicketRecord, ...]
    incident: IncidentRecord


def _json_default(value: object) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return format(value, "f")
    raise TypeError(f"Unserialisable value in dataset checksum: {type(value)!r}")


def dataset_checksum(dataset: DemoDataset) -> str:
    """SHA-256 over a canonical serialisation of every record, in order."""
    digest = hashlib.sha256()
    parts: tuple[Any, ...] = (
        *dataset.teams,
        *dataset.customers,
        *dataset.tickets,
        dataset.incident,
    )
    for record in parts:
        line = json.dumps(asdict(record), sort_keys=True, default=_json_default)
        digest.update(line.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()
