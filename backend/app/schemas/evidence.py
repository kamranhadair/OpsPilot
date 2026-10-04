"""The Evidence Bundle: the only operational evidence the brief model may use in V1.

Every item is a precomputed, persisted fact (``observed_fact``) or a timeline entry
(``contextual_event``). A contextual event is never a causal finding: its ``causal``
flag is the constant ``False``. The bundle is immutable and self-validating, so a
bundle that exists is internally consistent: the allow-list is exactly the set of item
IDs, every cross-reference resolves inside the bundle and every observed fact shares
the analysis window.
"""

import hashlib
from collections import Counter
from collections.abc import Sequence
from enum import StrEnum
from typing import Annotated, Any, Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from app.models.enums import AnomalySeverity, EvidenceType
from app.services.anomalies.detector import ThresholdDetails
from app.services.anomalies.rules import Comparison
from app.services.contributors.provenance import ContributorProvenance
from app.services.metrics.definitions import MetricUnit
from app.services.metrics.provenance import MetricProvenance

EvidenceClass = Literal["observed_fact", "contextual_event"]
MetricRole = Literal["overview", "anomaly_trigger"]
ContributorStatus = Literal["available", "not_computed", "none_ranked"]

EVENT_CONTEXT_NOTE = (
    "Timeline context only. It occurred near the analysis window; "
    "no link to the metric change has been established."
)
CONTRIBUTOR_CONTEXT_NOTE = (
    "Share of the observed change only. A contributing segment locates where the change "
    "happened; it does not establish why."
)


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class WindowOut(_Frozen):
    start: AwareDatetime
    end: AwareDatetime


class AnalysisWindowOut(_Frozen):
    current: WindowOut
    baseline: WindowOut
    event_lookback_hours: int


class BundleLimits(_Frozen):
    """The bounds applied while assembling; they keep the bundle small and reviewable."""

    max_anomalies: int
    contributors_per_family: int
    max_related_events: int
    event_lookback_hours: int


class ExclusionReason(StrEnum):
    WINDOW_MISMATCH = "window_mismatch"
    STALE_DEFINITION_VERSION = "stale_definition_version"
    UNRESOLVED = "unresolved"
    OVER_LIMIT = "over_limit"


class ExcludedEvidence(_Frozen):
    """Evidence considered and deliberately left out; it is not in the allow-list."""

    evidence_id: str
    reason: ExclusionReason


class ProvenanceSummary(_Frozen):
    """Concise source information; the full provenance stays behind the evidence ID."""

    source: str
    formula: str | None = None
    sample_size: int | None = None
    computed_at: AwareDatetime | None = None


class _EvidenceBase(_Frozen):
    evidence_id: str
    label: str
    window: WindowOut | None = Field(description="Null for timeline events.")
    dimensions: dict[str, str]
    provenance: ProvenanceSummary


class MetricEvidence(_EvidenceBase):
    evidence_type: Literal[EvidenceType.METRIC] = EvidenceType.METRIC
    evidence_class: Literal["observed_fact"] = "observed_fact"
    role: MetricRole
    metric_key: str
    unit: MetricUnit
    value: float
    baseline_value: float | None
    change_pct: float | None = Field(description="Null when the baseline is zero or empty.")
    change_pp: float | None = Field(description="Percentage points; rate metrics only.")
    baseline_zero: bool
    baseline_empty: bool
    sample_size: int
    sample_sufficient: bool


class AnomalyEvidence(_EvidenceBase):
    evidence_type: Literal[EvidenceType.ANOMALY] = EvidenceType.ANOMALY
    evidence_class: Literal["observed_fact"] = "observed_fact"
    metric_evidence_id: str
    metric_key: str
    severity: AnomalySeverity
    score: float | None
    score_comparison: Comparison
    detector_key: str
    explanation: str
    contributor_status: ContributorStatus
    contributor_evidence_ids: list[str]


class ContributorEvidence(_EvidenceBase):
    evidence_type: Literal[EvidenceType.SEGMENT] = EvidenceType.SEGMENT
    evidence_class: Literal["observed_fact"] = "observed_fact"
    anomaly_evidence_id: str
    metric_evidence_id: str
    family_key: str
    segment: dict[str, str]
    rank: int
    current_value: float
    baseline_value: float
    delta_value: float
    contribution_pct: float = Field(description="Share of observed change, 0-100; not a cause.")
    method: str
    sample: int
    min_sample: int
    sample_sufficient: bool
    flags: list[str]
    statement: str


class RelatedEventEvidence(_EvidenceBase):
    evidence_type: Literal[EvidenceType.EVENT] = EvidenceType.EVENT
    evidence_class: Literal["contextual_event"] = "contextual_event"
    relationship: Literal["temporal_proximity"] = "temporal_proximity"
    causal: Literal[False] = False
    context_note: str = EVENT_CONTEXT_NOTE
    event_type: str
    title: str
    occurred_at: AwareDatetime
    product: str | None
    hours_from_window_start: float = Field(description="Negative when before the window start.")
    details: dict[str, str] = Field(description="Allow-listed incident fields only.")

    @model_validator(mode="after")
    def _fixed_context_note(self) -> Self:
        if self.context_note != EVENT_CONTEXT_NOTE:
            raise ValueError("A related event must carry the standard non-causal context note.")
        return self


class EvidenceBundle(_Frozen):
    analysis_window: AnalysisWindowOut | None = Field(
        description="Null when no metrics have been computed."
    )
    metrics: list[MetricEvidence]
    anomalies: list[AnomalyEvidence]
    contributors: list[ContributorEvidence]
    related_events: list[RelatedEventEvidence]
    allowed_evidence_ids: list[str] = Field(description="Sorted; the only citable IDs.")
    excluded: list[ExcludedEvidence]
    limits: BundleLimits
    signature: str = Field(description="sha256 of the canonical bundle content.")

    @classmethod
    def create(
        cls,
        *,
        analysis_window: AnalysisWindowOut | None,
        metrics: Sequence[MetricEvidence],
        anomalies: Sequence[AnomalyEvidence],
        contributors: Sequence[ContributorEvidence],
        related_events: Sequence[RelatedEventEvidence],
        excluded: Sequence[ExcludedEvidence],
        limits: BundleLimits,
    ) -> Self:
        """Derive the allow-list and signature from the items, then validate."""
        fields: dict[str, Any] = {
            "analysis_window": analysis_window,
            "metrics": list(metrics),
            "anomalies": list(anomalies),
            "contributors": list(contributors),
            "related_events": list(related_events),
            "allowed_evidence_ids": sorted(
                item.evidence_id for item in (*metrics, *anomalies, *contributors, *related_events)
            ),
            "excluded": list(excluded),
            "limits": limits,
        }
        unsigned = cls.model_construct(**fields, signature="")
        return cls(**fields, signature=unsigned.compute_signature())

    def compute_signature(self) -> str:
        body = self.model_dump_json(exclude={"signature"})
        return hashlib.sha256(body.encode()).hexdigest()

    @model_validator(mode="after")
    def _check_consistency(self) -> Self:
        items = (*self.metrics, *self.anomalies, *self.contributors, *self.related_events)
        ids = [item.evidence_id for item in items]

        duplicates = sorted(i for i, n in Counter(ids).items() if n > 1)
        if duplicates:
            raise ValueError(f"Duplicate evidence IDs in the bundle: {duplicates}")
        if self.allowed_evidence_ids != sorted(ids):
            raise ValueError("allowed_evidence_ids must be exactly the sorted item evidence IDs.")
        if set(self.allowed_evidence_ids) & {e.evidence_id for e in self.excluded}:
            raise ValueError("Excluded evidence must not be in the allow-list.")

        if self.analysis_window is None:
            if items:
                raise ValueError("A bundle without an analysis window must hold no evidence.")
        else:
            for fact in (*self.metrics, *self.anomalies, *self.contributors):
                if fact.window != self.analysis_window.current:
                    raise ValueError(f"{fact.evidence_id} is outside the analysis window.")

        metric_ids = {m.evidence_id for m in self.metrics}
        anomaly_ids = {a.evidence_id for a in self.anomalies}
        contributor_ids = {c.evidence_id for c in self.contributors}
        for anomaly in self.anomalies:
            if anomaly.metric_evidence_id not in metric_ids:
                raise ValueError(f"{anomaly.evidence_id} cites a metric outside the bundle.")
            if not set(anomaly.contributor_evidence_ids) <= contributor_ids:
                raise ValueError(f"{anomaly.evidence_id} cites contributors outside the bundle.")
        for contributor in self.contributors:
            if contributor.anomaly_evidence_id not in anomaly_ids:
                raise ValueError(f"{contributor.evidence_id} cites an anomaly outside the bundle.")

        if self.signature != self.compute_signature():
            raise ValueError("signature does not match the bundle content.")
        return self


# --- Evidence resolver envelope (GET /api/evidence/{evidence_id}) ----------------------


class EvidenceValue(_Frozen):
    """One backend-labelled value; the frontend formats it but never derives it."""

    key: str
    label: str
    value: float | int | str | None
    unit: str | None = Field(
        default=None,
        description="count, minutes, percent, percentage_points, or null for text values.",
    )
    note: str | None = Field(default=None, description="Why a value is null, when it is.")


EvidenceMethodKind = Literal[
    "metric_calculation", "anomaly_detector", "contribution", "timeline_event"
]


class EvidenceMethod(_Frozen):
    kind: EvidenceMethodKind
    name: str
    version: str | None = None
    formula: str | None = None
    description: str | None = None


class MetricDetailProvenance(_Frozen):
    evidence_type: Literal[EvidenceType.METRIC] = EvidenceType.METRIC
    computed_at: AwareDatetime
    metric: MetricProvenance


class AnomalyDetailProvenance(_Frozen):
    evidence_type: Literal[EvidenceType.ANOMALY] = EvidenceType.ANOMALY
    detected_at: AwareDatetime
    threshold: ThresholdDetails


class ContributorDetailProvenance(_Frozen):
    evidence_type: Literal[EvidenceType.SEGMENT] = EvidenceType.SEGMENT
    statement: str
    contribution: ContributorProvenance


class EventDetailProvenance(_Frozen):
    evidence_type: Literal[EvidenceType.EVENT] = EvidenceType.EVENT
    source: Literal["incident_timeline"] = "incident_timeline"
    event_type: str
    occurred_at: AwareDatetime
    details: dict[str, str] = Field(description="Allow-listed incident fields only.")


EvidenceDetailProvenance = Annotated[
    MetricDetailProvenance
    | AnomalyDetailProvenance
    | ContributorDetailProvenance
    | EventDetailProvenance,
    Field(discriminator="evidence_type"),
]


class EvidenceDetailOut(_Frozen):
    """Common typed envelope for any persisted MTR/ANOM/SEG/EVT evidence."""

    evidence_id: str
    evidence_type: EvidenceType
    evidence_class: EvidenceClass
    label: str
    window: WindowOut | None = Field(description="Null for timeline events.")
    baseline_window: WindowOut | None
    dimensions: dict[str, str]
    sample_size: int | None
    sample_sufficient: bool | None
    values: list[EvidenceValue]
    method: EvidenceMethod
    related_evidence_ids: list[str]
    contextual_disclaimer: str | None
    provenance: EvidenceDetailProvenance
