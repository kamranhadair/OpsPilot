"""Typed API contracts for the metrics endpoints."""

from datetime import datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from app.models.enums import CustomerTier, Product, Region, TicketCategory
from app.services.metrics.definitions import (
    Aggregation,
    BaselineMethod,
    Cohort,
    Dimension,
    Direction,
    MetricUnit,
)
from app.services.metrics.provenance import MetricProvenance


class MetricFilters(BaseModel):
    """Optional equality filters, one value per supported dimension."""

    model_config = ConfigDict(extra="forbid")

    category: TicketCategory | None = None
    product: Product | None = None
    region: Region | None = None
    customer_tier: CustomerTier | None = None
    support_team: str | None = Field(default=None, min_length=1, max_length=64)

    def as_dimensions(self) -> dict[Dimension, str]:
        return {
            Dimension(key): str(value) for key, value in self.model_dump(exclude_none=True).items()
        }


class MetricComputeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    window_end: AwareDatetime | None = Field(
        default=None,
        description="End of the 24h current window. Defaults to the end of available data.",
    )
    filters: MetricFilters = Field(default_factory=MetricFilters)


class MetricDefinitionOut(BaseModel):
    key: str
    display_name: str
    description: str
    unit: MetricUnit
    aggregation: Aggregation
    cohort: Cohort
    formula: str
    direction: Direction
    baseline_method: BaselineMethod
    supported_dimensions: list[Dimension]
    min_sample_size: int | None
    version: int


class MetricSnapshotOut(BaseModel):
    evidence_id: str = Field(description="Evidence ID with the MTR- prefix.")
    metric_key: str
    display_name: str
    unit: MetricUnit
    direction: Direction
    window_start: datetime
    window_end: datetime
    baseline_start: datetime | None
    baseline_end: datetime | None
    dimensions: dict[str, str]
    value: float
    baseline_value: float | None
    change_pct: float | None = Field(description="Null when the baseline is zero or empty.")
    change_pp: float | None = Field(
        description="Percentage-point difference; rate metrics only, otherwise null."
    )
    baseline_zero: bool
    baseline_empty: bool
    sample_size: int
    sample_sufficient: bool
    provenance: MetricProvenance
    computed_at: datetime


ComputeStatus = Literal["computed", "reused", "insufficient_data"]


class MetricComputeItem(BaseModel):
    metric_key: str
    status: ComputeStatus = Field(
        description=(
            "computed: new snapshot; reused: identical analysis already persisted; "
            "insufficient_data: no samples in the current window, nothing persisted."
        )
    )
    snapshot: MetricSnapshotOut | None


class MetricComputeResponse(BaseModel):
    window_start: datetime
    window_end: datetime
    baseline_start: datetime
    baseline_end: datetime
    filters: dict[str, str]
    items: list[MetricComputeItem]


class MetricOverviewResponse(BaseModel):
    window_end: datetime | None = Field(description="Null when no metrics have been computed.")
    items: list[MetricSnapshotOut]
    missing_metric_keys: list[str]


class MetricSeriesResponse(BaseModel):
    definition: MetricDefinitionOut
    filters: dict[str, str]
    points: list[MetricSnapshotOut]
