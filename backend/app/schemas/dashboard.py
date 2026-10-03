"""Typed API contract for the operations dashboard overview endpoint."""

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.anomalies import AnomalyOut
from app.schemas.metrics import MetricDefinitionOut, MetricSnapshotOut


class TrendPoint(BaseModel):
    """One persisted overall snapshot, slimmed for charting (provenance stays on the MTR- ID)."""

    evidence_id: str = Field(description="Evidence ID with the MTR- prefix.")
    window_end: datetime
    value: float
    baseline_value: float | None
    change_pct: float | None = Field(description="Null when the baseline is zero or empty.")
    sample_size: int


class DashboardTrend(BaseModel):
    definition: MetricDefinitionOut
    points: list[TrendPoint] = Field(description="Oldest first; may hold fewer than two points.")


class DashboardOverviewResponse(BaseModel):
    window_end: datetime | None = Field(description="Null when no metrics have been computed.")
    cards: list[MetricSnapshotOut] = Field(description="Overall snapshots in display order.")
    missing_metric_keys: list[str]
    trends: list[DashboardTrend]
    active_anomalies: list[AnomalyOut] = Field(
        description="Active anomalies, newest window first, then by severity."
    )
    active_anomaly_total: int
