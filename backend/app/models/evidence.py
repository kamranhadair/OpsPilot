"""Evidence-bearing tables: incidents/events, metric snapshots, anomalies, contributors.

Every row carries a unique, type-prefixed ``evidence_id`` allocated by
``app.services.evidence_ids``; it is never derived from the primary key.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, JSONBType, RowTimestampsMixin, UTCDateTime, str_enum
from app.models.enums import AnomalySeverity, AnomalyStatus, Product


class Incident(RowTimestampsMixin, Base):
    __tablename__ = "incidents"
    __table_args__ = (CheckConstraint("evidence_id ~ '^EVT-[0-9]+$'", name="evidence_prefix"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    evidence_id: Mapped[str] = mapped_column(String(32), unique=True)
    event_type: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(300))
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime)
    product: Mapped[Product | None] = mapped_column(str_enum(Product, "incident_product"))
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONBType)


class MetricSnapshot(Base):
    __tablename__ = "metric_snapshots"
    __table_args__ = (
        CheckConstraint("evidence_id ~ '^MTR-[0-9]+$'", name="evidence_prefix"),
        CheckConstraint("window_end > window_start", name="window_order"),
        CheckConstraint(
            "(baseline_start IS NULL AND baseline_end IS NULL) "
            "OR (baseline_start IS NOT NULL AND baseline_end IS NOT NULL "
            "AND baseline_end > baseline_start)",
            name="baseline_order",
        ),
        CheckConstraint("sample_size >= 0", name="sample_size_nonneg"),
        Index("ix_metric_snapshots_metric_key_window_end", "metric_key", "window_end"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    evidence_id: Mapped[str] = mapped_column(String(32), unique=True)
    metric_key: Mapped[str] = mapped_column(String(100))
    window_start: Mapped[datetime] = mapped_column(UTCDateTime)
    window_end: Mapped[datetime] = mapped_column(UTCDateTime)
    baseline_start: Mapped[datetime | None] = mapped_column(UTCDateTime)
    baseline_end: Mapped[datetime | None] = mapped_column(UTCDateTime)
    dimensions_json: Mapped[dict[str, Any]] = mapped_column(JSONBType)
    value: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    baseline_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    change_pct: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    sample_size: Mapped[int] = mapped_column(Integer)
    provenance_json: Mapped[dict[str, Any]] = mapped_column(JSONBType)
    computed_at: Mapped[datetime] = mapped_column(UTCDateTime)


class Anomaly(Base):
    __tablename__ = "anomalies"
    __table_args__ = (
        CheckConstraint("evidence_id ~ '^ANOM-[0-9]+$'", name="evidence_prefix"),
        Index("ix_anomalies_status_detected_at", "status", "detected_at"),
        Index("ix_anomalies_metric_snapshot_id", "metric_snapshot_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    evidence_id: Mapped[str] = mapped_column(String(32), unique=True)
    metric_snapshot_id: Mapped[int] = mapped_column(
        ForeignKey("metric_snapshots.id", ondelete="RESTRICT")
    )
    detector_key: Mapped[str] = mapped_column(String(100))
    severity: Mapped[AnomalySeverity] = mapped_column(str_enum(AnomalySeverity, "anomaly_severity"))
    score: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    threshold_json: Mapped[dict[str, Any]] = mapped_column(JSONBType)
    status: Mapped[AnomalyStatus] = mapped_column(str_enum(AnomalyStatus, "anomaly_status"))
    detected_at: Mapped[datetime] = mapped_column(UTCDateTime)


class AnomalyContributor(Base):
    __tablename__ = "anomaly_contributors"
    __table_args__ = (
        CheckConstraint("evidence_id ~ '^SEG-[0-9]+$'", name="evidence_prefix"),
        CheckConstraint("rank >= 1", name="rank_positive"),
        Index("ix_anomaly_contributors_anomaly_id", "anomaly_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    evidence_id: Mapped[str] = mapped_column(String(32), unique=True)
    anomaly_id: Mapped[int] = mapped_column(ForeignKey("anomalies.id", ondelete="CASCADE"))
    dimension_key: Mapped[str] = mapped_column(String(100))
    segment_value: Mapped[str] = mapped_column(String(200))
    current_value: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    baseline_value: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    delta_value: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    contribution_pct: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    rank: Mapped[int] = mapped_column(Integer)
    provenance_json: Mapped[dict[str, Any]] = mapped_column(JSONBType)
