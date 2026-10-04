"""Typed contracts for the demo analysis run and demo status endpoints (Spec 15)."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.models.enums import AnomalySeverity, BriefStatus


class AnalysisAnomalyOut(BaseModel):
    evidence_id: str = Field(description="ANOM- evidence ID.")
    metric_evidence_id: str
    metric_key: str
    display_name: str
    dimensions: dict[str, str]
    severity: AnomalySeverity
    contributor_status: Literal["computed", "reused", "not_supported"] = Field(
        description="not_supported: the metric is not additive, so it has no segment ranking."
    )
    contributor_evidence_ids: list[str] = Field(description="SEG- IDs, ranked per family.")


class AnalysisEvidenceOut(BaseModel):
    allowed_evidence_ids: list[str] = Field(description="Every citable ID in the bundle.")
    metric_count: int
    anomaly_count: int
    contributor_count: int
    related_event_count: int
    signature: str = Field(description="sha256 of the bundle; equal bundles share it.")


class AnalysisBriefOut(BaseModel):
    state: Literal["generated", "not_configured", "failed"] = Field(
        description=(
            "generated: a brief was written and validated; not_configured: no API key/model, "
            "nothing was called; failed: the model call failed (see error_code)."
        )
    )
    brief_id: int | None
    status: BriefStatus | None = Field(description="valid or invalid when generated.")
    error_code: str | None
    message: str | None


class AnalysisRunResponse(BaseModel):
    window_start: datetime
    window_end: datetime
    metric_windows_computed: int = Field(description="Overall daily windows computed for trends.")
    metric_evidence_ids: list[str] = Field(description="MTR- IDs of the final window.")
    anomalies: list[AnalysisAnomalyOut] = Field(description="Most severe first.")
    evidence: AnalysisEvidenceOut
    brief: AnalysisBriefOut


class DemoStatusResponse(BaseModel):
    enabled: bool = Field(description="False outside demo/development/test environments.")
    dataset_seeded: bool
    analysis_window_end: datetime | None = Field(
        description="End of the latest computed window; null before the first analysis."
    )
    llm_configured: bool
