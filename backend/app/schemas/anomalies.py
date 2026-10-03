"""Typed API contracts for the anomaly endpoints."""

from datetime import datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from app.models.enums import AnomalySeverity, AnomalyStatus
from app.schemas.metrics import MetricSnapshotOut
from app.services.anomalies.detector import SkipReason, ThresholdDetails


class AnomalyDetectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    window_end: AwareDatetime | None = Field(
        default=None,
        description="End of the 24h current window. Defaults to the end of available data.",
    )


class AnomalyOut(BaseModel):
    evidence_id: str = Field(description="Evidence ID with the ANOM- prefix.")
    metric_evidence_id: str = Field(description="MTR- evidence ID of the triggering snapshot.")
    metric_key: str
    display_name: str
    dimensions: dict[str, str]
    severity: AnomalySeverity
    status: AnomalyStatus
    score: float | None = Field(description="The triggering change: percent or percentage points.")
    detector_key: str
    window_start: datetime
    window_end: datetime
    detected_at: datetime
    explanation: str = Field(description="Deterministic, template-built; never model-written.")


class AnomalyDetailOut(AnomalyOut):
    threshold: ThresholdDetails
    snapshot: MetricSnapshotOut


DetectStatus = Literal["detected", "reused", "skipped"]


class AnomalyDetectItem(BaseModel):
    metric_key: str
    filters: dict[str, str]
    status: DetectStatus = Field(
        description=(
            "detected: new anomaly persisted; reused: identical anomaly already persisted; "
            "skipped: nothing flagged, see skip_reason."
        )
    )
    metric_evidence_id: str | None
    anomaly: AnomalyOut | None
    skip_reason: SkipReason | None
    skip_detail: str | None


class AnomalyDetectResponse(BaseModel):
    window_start: datetime
    window_end: datetime
    items: list[AnomalyDetectItem]
    detected_count: int
    reused_count: int
    skipped_count: int


class AnomalyListResponse(BaseModel):
    items: list[AnomalyOut]
    total: int
    limit: int
    offset: int
