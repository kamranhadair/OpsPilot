"""AI operations briefs and their individually validated claims."""

from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, JSONBType, RowTimestampsMixin, UTCDateTime, str_enum
from app.models.enums import BriefStatus, ClaimType, ClaimValidationStatus


class Brief(RowTimestampsMixin, Base):
    __tablename__ = "briefs"
    __table_args__ = (
        CheckConstraint("analysis_window_end > analysis_window_start", name="window_order"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    analysis_window_start: Mapped[datetime] = mapped_column(UTCDateTime)
    analysis_window_end: Mapped[datetime] = mapped_column(UTCDateTime)
    headline: Mapped[str] = mapped_column(String(500))
    summary: Mapped[str] = mapped_column(Text)
    status: Mapped[BriefStatus] = mapped_column(str_enum(BriefStatus, "brief_status"))
    model_name: Mapped[str] = mapped_column(String(100))
    validation_errors_json: Mapped[list[Any] | dict[str, Any]] = mapped_column(JSONBType)


class BriefClaim(Base):
    __tablename__ = "brief_claims"
    __table_args__ = (
        UniqueConstraint("brief_id", "ordinal", name="uq_brief_claims_brief_id_ordinal"),
        Index("ix_brief_claims_brief_id", "brief_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    brief_id: Mapped[int] = mapped_column(ForeignKey("briefs.id", ondelete="CASCADE"))
    ordinal: Mapped[int]
    claim_type: Mapped[ClaimType] = mapped_column(str_enum(ClaimType, "claim_type"))
    text: Mapped[str] = mapped_column(Text)
    evidence_ids_json: Mapped[list[str]] = mapped_column(JSONBType)
    validation_status: Mapped[ClaimValidationStatus] = mapped_column(
        str_enum(ClaimValidationStatus, "claim_validation_status")
    )
    validation_errors_json: Mapped[list[Any] | dict[str, Any]] = mapped_column(JSONBType)
