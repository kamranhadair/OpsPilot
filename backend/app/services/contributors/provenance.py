"""Typed provenance stored with every contributor row.

It records the formula, windows, filters and the raw integers used, so a reviewer
can recompute the delta and share without rerunning any query.
"""

from decimal import Decimal
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict

from app.services.contributors.formulas import Flag, Method
from app.services.metrics.provenance import WindowProvenance


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ContributorProvenance(_Frozen):
    schema_version: Literal[1] = 1
    analysis_version: str
    anomaly_evidence_id: str
    metric_evidence_id: str
    metric_key: str
    family_key: str
    segment: dict[str, str]
    # Dimensions already fixed by the anomaly's slice (e.g. category=billing).
    base_filters: dict[str, str]
    method: Method
    formula: str
    current_window: WindowProvenance
    baseline_window: WindowProvenance
    baseline_days: list[WindowProvenance]
    # Count: current count. Rate: current events (numerator).
    current_events: int
    # Rate only: current records (denominator).
    current_denominator: int | None
    # Count only: normalised (mean daily) baseline count.
    baseline_value: Decimal | None
    # Rate only: summed baseline numerator/denominator, the rate used, and its source.
    baseline_numerator: int | None
    baseline_denominator: int | None
    baseline_rate: Decimal | None
    baseline_rate_source: Literal["segment", "parent_slice"] | None
    expected_events: Decimal | None
    delta: Decimal
    # Family totals the share was computed against.
    family_positive_delta_total: Decimal
    family_suppressed_contribution_pct: Decimal
    sample: int
    min_sample: int
    sample_sufficient: bool
    flags: list[Flag]
    computed_at: AwareDatetime
