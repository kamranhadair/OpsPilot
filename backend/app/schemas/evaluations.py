"""Evaluation report contract (Spec 13): written by the eval runner, served by the API.

Deterministic case results and the optional model-based section are kept apart: a
model-based result never contributes to a deterministic pass rate. A rate whose
denominator is zero is ``None`` (nothing was measured), never 0% or 100%.
"""

from enum import StrEnum
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from app.models.enums import AnomalySeverity
from app.schemas.evidence import (
    AnomalyEvidence,
    ContributorEvidence,
    MetricEvidence,
    RelatedEventEvidence,
)

REPORT_SCHEMA_VERSION: Literal[1] = 1

CaseStatus = Literal["pass", "fail", "not_run", "error"]
SuiteName = Literal["all", "deterministic", "ai"]
OverallStatus = Literal["pass", "fail", "incomplete"]
SeedState = Literal["complete", "empty", "inconsistent", "unavailable"]

STATISTICAL_NOTE = (
    "Small synthetic demo dataset: these results show expected behaviour on planted "
    "scenarios and fixtures. They are not statistically significant performance estimates."
)


class EvalCategory(StrEnum):
    METRIC_CORRECTNESS = "metric_correctness"
    ANOMALY_DETECTION = "anomaly_detection"
    FALSE_POSITIVE = "false_positive"
    CONTRIBUTOR_ATTRIBUTION = "contributor_attribution"
    CITATION_VALIDITY = "citation_validity"
    CAUSAL_GUARDRAIL = "causal_guardrail"
    ACTION_GROUNDING = "action_grounding"
    APPROVAL_BOUNDARY = "approval_boundary"


DETERMINISTIC_CATEGORIES: tuple[EvalCategory, ...] = (
    EvalCategory.METRIC_CORRECTNESS,
    EvalCategory.ANOMALY_DETECTION,
    EvalCategory.FALSE_POSITIVE,
    EvalCategory.CONTRIBUTOR_ATTRIBUTION,
    EvalCategory.APPROVAL_BOUNDARY,
)
AI_CATEGORIES: tuple[EvalCategory, ...] = (
    EvalCategory.CITATION_VALIDITY,
    EvalCategory.CAUSAL_GUARDRAIL,
    EvalCategory.ACTION_GROUNDING,
)


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CaseTally(_Model):
    """A count measured inside one case, e.g. high/critical flags among checked metrics."""

    flagged: int = Field(ge=0)
    checked: int = Field(ge=0)


class CaseResult(_Model):
    case_id: str
    title: str
    category: EvalCategory
    status: CaseStatus
    expected: str
    observed: str | None = None
    failure_reason: str | None = Field(
        default=None, description="Why the case failed, errored or did not run."
    )
    evidence: list[str] = Field(default_factory=list, description="Codes/IDs backing the result.")
    tally: CaseTally | None = None


class CategorySummary(_Model):
    category: EvalCategory
    total: int
    passed: int
    failed: int
    errored: int
    not_run: int
    pass_rate: float | None = Field(
        description="passed / (passed + failed + errored); null when nothing was executed."
    )


class RatioMetric(_Model):
    key: str
    label: str
    numerator: int
    denominator: int
    value: float | None = Field(description="numerator / denominator; null when denominator is 0.")
    description: str


class CountMetric(_Model):
    key: str
    label: str
    passed: int
    failed: int
    errored: int
    not_run: int
    description: str


class SeedInfo(_Model):
    expected_version: str
    case_version: str
    observed_state: SeedState
    observed_version: str | None
    matches: bool


class ReplayAnomaly(_Model):
    metric_key: str
    display_name: str
    filters: dict[str, str]
    severity: AnomalySeverity
    score: float | None


class ReplayDay(_Model):
    window_start: AwareDatetime
    window_end: AwareDatetime
    status: Literal["ok", "no_data"]
    detail: str | None = None
    anomalies: list[ReplayAnomaly] = Field(default_factory=list)
    high_or_critical_count: int = 0


class ReplaySummary(_Model):
    status: Literal["completed", "not_run", "error"]
    reason: str | None = None
    days_requested: int
    days: list[ReplayDay] = Field(default_factory=list)
    note: str = (
        "Read-only replay: each day uses the production 24h window and its 7-day baseline; "
        "nothing is persisted."
    )


class ModelBasedSection(_Model):
    """Optional semantic citation-support judgement. Never part of deterministic totals."""

    label: Literal["model_based"] = "model_based"
    status: Literal["completed", "not_run", "error"]
    reason: str | None = None
    model_name: str | None = None
    prompt_version: str | None = None
    cases: list[CaseResult] = Field(default_factory=list)


class EvaluationReport(_Model):
    schema_version: Literal[1] = REPORT_SCHEMA_VERSION
    run_id: str
    suite: SuiteName
    generated_at: AwareDatetime
    overall_status: OverallStatus
    partial_failure: bool = Field(description="True when any case, replay or judge errored.")
    seed: SeedInfo
    cases: list[CaseResult]
    categories: list[CategorySummary]
    ratios: list[RatioMetric]
    counts: list[CountMetric]
    replay: ReplaySummary | None
    model_based: ModelBasedSection
    notes: list[str]


CitationSupportVerdict = Literal["supported", "partially_supported", "unsupported"]


class CitationJudgeRequest(_Model):
    """Everything the optional judge sees: one claim and only the evidence it cites."""

    claim_text: str
    cited_evidence: list[
        MetricEvidence | AnomalyEvidence | ContributorEvidence | RelatedEventEvidence
    ] = Field(description="The cited Evidence Bundle items; never raw rows.")


class CitationSupportJudgement(_Model):
    """Structured output required from the optional model judge."""

    verdict: CitationSupportVerdict
    rationale: str = Field(max_length=1000)


class EvaluationLatestResponse(_Model):
    state: Literal["available", "not_run"]
    report: EvaluationReport | None
    message: str | None = None
