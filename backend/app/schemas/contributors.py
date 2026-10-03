"""Typed API contracts for the contributor endpoints."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.services.contributors.formulas import FamilyStatus, Flag, Method
from app.services.contributors.provenance import ContributorProvenance


class ContributorOut(BaseModel):
    evidence_id: str = Field(description="Evidence ID with the SEG- prefix.")
    rank: int
    segment: dict[str, str]
    label: str
    current_value: float = Field(description="Current count, or actual events for a rate metric.")
    baseline_value: float = Field(
        description="Normalised baseline count, or expected events for a rate metric."
    )
    delta_value: float = Field(description="Observed positive change attributed to the segment.")
    contribution_pct: float = Field(description="Share of the family's positive change, 0-100.")
    flags: list[Flag]
    statement: str = Field(description="Deterministic, template-built; never model-written.")
    provenance: ContributorProvenance


class ContributorGroupOut(BaseModel):
    family_key: str
    dimensions: list[str]
    method: Method
    formula: str
    positive_delta_total: float
    contributors: list[ContributorOut]
    other_contribution_pct: float = Field(
        description="Share not covered by the ranked segments (top-N truncation and suppression)."
    )
    suppressed_contribution_pct: float = Field(
        description="Share held by segments below the minimum sample size; not ranked."
    )


class UnrankedFamilyOut(BaseModel):
    family_key: str
    status: FamilyStatus


class ContributorAnalysisResponse(BaseModel):
    anomaly_evidence_id: str
    metric_evidence_id: str
    metric_key: str
    display_name: str
    window_start: datetime
    window_end: datetime
    status: Literal["computed", "reused"] = Field(
        description="computed: calculated by this request; reused: read from stored rows."
    )
    groups: list[ContributorGroupOut]
    unranked_families: list[UnrankedFamilyOut] = Field(
        description=(
            "Families with nothing to rank (fixed by the anomaly slice, or no positive "
            "change). Only populated by the request that computes; nothing is stored for them."
        )
    )
