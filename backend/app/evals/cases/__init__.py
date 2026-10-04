"""Version-controlled evaluation cases and their typed loaders.

Each JSON file is validated on load, so a malformed case file fails loudly instead of
silently shrinking the suite. Cases that depend on the seeded demo dataset carry the
``seed_version`` their expected facts were written for.
"""

from decimal import Decimal
from pathlib import Path
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from app.models.enums import AnomalySeverity, BriefStatus
from app.schemas.actions import ActionProposalOutput
from app.schemas.briefs import DraftClaim
from app.schemas.evaluations import EvalCategory
from app.schemas.evidence import (
    AnalysisWindowOut,
    AnomalyEvidence,
    BundleLimits,
    ContributorEvidence,
    EvidenceBundle,
    ExcludedEvidence,
    MetricEvidence,
    RelatedEventEvidence,
)
from app.services.metrics.definitions import METRIC_REGISTRY, AggregateField

CASES_DIR = Path(__file__).resolve().parent


class _Case(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- metric fixtures ---------------------------------------------------------------------


class MetricExpectation(_Case):
    value: Decimal | None
    baseline_value: Decimal | None
    change_pct: Decimal | None
    baseline_zero: bool


class MetricFixtureCase(_Case):
    case_id: str
    title: str
    metric_key: str
    baseline: list[dict[AggregateField, int]] = Field(min_length=7, max_length=7)
    current: dict[AggregateField, int]
    expected: MetricExpectation

    def buckets(self) -> list[dict[AggregateField, int]]:
        """Seven baseline days then the current window, unspecified aggregates zero."""
        days = (*self.baseline, self.current)
        return [{f: day.get(f, 0) for f in AggregateField} for day in days]


class MetricFixtureFile(_Case):
    suite: Literal["metric_correctness"]
    description: str
    cases: list[MetricFixtureCase] = Field(min_length=1)


# --- seeded golden cases ---------------------------------------------------------------


class PlantedAnomalyCase(_Case):
    case_id: str
    title: str
    window_end: AwareDatetime
    filters: dict[str, str]
    metric_key: str
    expected_severities: list[AnomalySeverity] = Field(min_length=1)


class NormalCase(_Case):
    """A designated quiet day; every listed slice is checked. ``{}`` is the overall slice."""

    case_id: str
    title: str
    window_end: AwareDatetime
    slices: list[dict[str, str]] = Field(min_length=1)


class AnomalyGoldenFile(_Case):
    suite: Literal["anomaly_detection"]
    seed_version: str
    description: str
    planted: list[PlantedAnomalyCase] = Field(min_length=1)
    normal: list[NormalCase] = Field(min_length=1)


class ContributorCase(_Case):
    case_id: str
    title: str
    window_end: AwareDatetime
    filters: dict[str, str]
    metric_key: str
    family_key: str
    expected_segment: dict[str, str]
    top_k: int = Field(ge=1)


class ContributorGoldenFile(_Case):
    suite: Literal["contributor_attribution"]
    seed_version: str
    description: str
    cases: list[ContributorCase] = Field(min_length=1)


# --- AI guardrail cases ----------------------------------------------------------------


class BriefGuardrailCase(_Case):
    case_id: str
    title: str
    category: Literal[EvalCategory.CITATION_VALIDITY, EvalCategory.CAUSAL_GUARDRAIL]
    headline: str = "Billing ticket volume is elevated"
    summary: str = "Billing ticket volume rose against its seven-day baseline."
    claims: list[DraftClaim] = Field(min_length=1)
    persisted_ids: list[str] | None = None
    expected_status: BriefStatus
    expected_codes: list[str]


class BundleFixture(_Case):
    """Evidence Bundle items; the allow-list and signature are derived on build."""

    analysis_window: AnalysisWindowOut
    metrics: list[MetricEvidence]
    anomalies: list[AnomalyEvidence]
    contributors: list[ContributorEvidence]
    related_events: list[RelatedEventEvidence]
    excluded: list[ExcludedEvidence]
    limits: BundleLimits


class BriefGuardrailFile(_Case):
    suite: Literal["brief_guardrails"]
    description: str
    bundle: BundleFixture
    cases: list[BriefGuardrailCase] = Field(min_length=1)

    def evidence_bundle(self) -> EvidenceBundle:
        """Build through ``EvidenceBundle.create`` so the fixture is self-consistent."""
        return EvidenceBundle.create(
            analysis_window=self.bundle.analysis_window,
            metrics=self.bundle.metrics,
            anomalies=self.bundle.anomalies,
            contributors=self.bundle.contributors,
            related_events=self.bundle.related_events,
            excluded=self.bundle.excluded,
            limits=self.bundle.limits,
        )


class ActionGuardrailCase(_Case):
    case_id: str
    title: str
    proposal: ActionProposalOutput
    expected_rejected: bool
    expected_codes: list[str]


class ActionGuardrailFile(_Case):
    suite: Literal["action_guardrails"]
    description: str
    brief_evidence_ids: list[str]
    persisted_ids: list[str]
    cases: list[ActionGuardrailCase] = Field(min_length=1)


ApprovalScenario = Literal[
    "execute_without_approval",
    "execute_without_approval_record",
    "system_reviewer_approves",
    "approve_then_execute_twice",
]


class ApprovalCase(_Case):
    case_id: str
    title: str
    scenario: ApprovalScenario
    reviewer: str | None = None
    expected: Literal["blocked", "executed_once"]


class ApprovalFile(_Case):
    suite: Literal["approval_boundary"]
    description: str
    cases: list[ApprovalCase] = Field(min_length=1)


# --- loaders ---------------------------------------------------------------------------


def _read(name: str, directory: Path | None) -> str:
    return ((directory or CASES_DIR) / name).read_text(encoding="utf-8")


def load_metric_fixtures(directory: Path | None = None) -> MetricFixtureFile:
    loaded = MetricFixtureFile.model_validate_json(_read("metric_fixtures.json", directory))
    unknown = {c.metric_key for c in loaded.cases} - set(METRIC_REGISTRY)
    if unknown:
        raise ValueError(f"Metric fixtures reference unknown metrics: {sorted(unknown)}")
    return loaded


def load_anomaly_golden(directory: Path | None = None) -> AnomalyGoldenFile:
    return AnomalyGoldenFile.model_validate_json(_read("anomaly_golden.json", directory))


def load_contributor_golden(directory: Path | None = None) -> ContributorGoldenFile:
    return ContributorGoldenFile.model_validate_json(_read("contributor_golden.json", directory))


def load_brief_guardrails(directory: Path | None = None) -> BriefGuardrailFile:
    return BriefGuardrailFile.model_validate_json(_read("brief_guardrails.json", directory))


def load_action_guardrails(directory: Path | None = None) -> ActionGuardrailFile:
    return ActionGuardrailFile.model_validate_json(_read("action_guardrails.json", directory))


def load_approval_cases(directory: Path | None = None) -> ApprovalFile:
    return ApprovalFile.model_validate_json(_read("approval_boundary.json", directory))


__all__ = [
    "CASES_DIR",
    "load_action_guardrails",
    "load_anomaly_golden",
    "load_approval_cases",
    "load_brief_guardrails",
    "load_contributor_golden",
    "load_metric_fixtures",
]
