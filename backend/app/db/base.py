"""Declarative base and shared column helpers for SQLAlchemy models.

Timestamps are deliberately *not* applied to every model: many tables carry
domain timestamps (``tickets.created_at`` is the ticket event time) that must
not receive a generic row-creation default. ``RowTimestampsMixin`` is opt-in
and used only by tables the spec says carry row-lifecycle timestamps.
"""

from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import DateTime, Enum, MetaData, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

UTCDateTime = DateTime(timezone=True)
JSONBType = JSONB(none_as_null=False)
# For optional JSON columns: Python None must become SQL NULL, not JSON 'null'.
OptionalJSONBType = JSONB(none_as_null=True)


class Base(DeclarativeBase):
    """Base class for all OpsPilot ORM models."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class RowTimestampsMixin:
    """Row lifecycle timestamps (UTC). Opt-in; never added to event tables."""

    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )


def str_enum(enum_cls: type[StrEnum], name: str) -> Enum:
    """VARCHAR column constrained by a named CHECK to the enum's values."""
    return Enum(
        enum_cls,
        name=name,
        native_enum=False,
        create_constraint=True,
        validate_strings=True,
        length=max(len(member.value) for member in enum_cls),
        values_callable=lambda cls: [member.value for member in cls],
    )


JSONDict = dict[str, Any]
