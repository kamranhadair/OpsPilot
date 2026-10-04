"""The single analysis path for the final window (Spec 15).

``AnalysisOrchestrator.run`` calls the existing services in order and adds no analytics
of its own:

    metric history -> anomaly detection -> contributors -> evidence bundle
    -> brief generation + validation (only when the LLM is configured)

Every deterministic stage is idempotent and committed by its own service, so a rerun
reuses the same evidence IDs and a model failure leaves the computed facts in place.
The orchestrator never proposes, approves or executes an action.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.observability import stage_timer
from app.integrations.llm.base import BriefLLMClient, LLMError
from app.models.enums import AnomalySeverity
from app.schemas.analysis import (
    AnalysisAnomalyOut,
    AnalysisBriefOut,
    AnalysisEvidenceOut,
    AnalysisRunResponse,
)
from app.schemas.anomalies import AnomalyOut
from app.schemas.metrics import MetricFilters
from app.services.anomalies.service import AnomalyService
from app.services.briefs.errors import BriefError
from app.services.briefs.generator import BriefService
from app.services.contributors.errors import SegmentationNotSupportedError
from app.services.contributors.service import ContributorService
from app.services.evidence.assembler import EvidenceBundleAssembler
from app.services.metrics.errors import WindowOutOfRangeError
from app.services.metrics.service import MetricsService

DEFAULT_HISTORY_DAYS = 14

ContributorRunStatus = Literal["computed", "reused", "not_supported"]

_SEVERITY_RANK = {
    AnomalySeverity.CRITICAL: 0,
    AnomalySeverity.HIGH: 1,
    AnomalySeverity.MEDIUM: 2,
    AnomalySeverity.LOW: 3,
}


@dataclass(frozen=True)
class MetricHistoryResult:
    latest_window_end: datetime
    computed: int
    skipped: int


def compute_metric_history(session: Session, days: int) -> MetricHistoryResult:
    """Overall snapshots for the latest ``days`` daily windows (dashboard trends).

    Windows whose baseline would start before the data are skipped, not failed.

    Raises:
        NoSourceDataError: there are no tickets at all.
    """
    metrics = MetricsService(session)
    latest = metrics.compute(None, MetricFilters()).window_end
    computed, skipped = 1, 0
    for offset in range(1, days):
        try:
            metrics.compute(latest - timedelta(days=offset), MetricFilters())
            computed += 1
        except WindowOutOfRangeError:
            skipped += 1
    return MetricHistoryResult(latest, computed, skipped)


class AnalysisOrchestrator:
    def __init__(
        self,
        session: Session,
        settings: Settings,
        brief_client_factory: Callable[[], BriefLLMClient] | None = None,
        history_days: int = DEFAULT_HISTORY_DAYS,
    ) -> None:
        self.session = session
        self.settings = settings
        self.brief_client_factory = brief_client_factory
        self.history_days = history_days

    def run(self) -> AnalysisRunResponse:
        """Analyse the latest window end to end.

        Raises:
            NoSourceDataError: the dataset is not seeded.
        """
        with stage_timer("analysis_run") as stage:
            response = self._run()
            stage.update(
                anomaly_count=len(response.anomalies),
                brief_state=response.brief.state,
                brief_id=response.brief.brief_id,
            )
            return response

    def _run(self) -> AnalysisRunResponse:
        history = compute_metric_history(self.session, self.history_days)
        detected = AnomalyService(self.session).detect(None)

        metric_ids = sorted(
            {i.metric_evidence_id for i in detected.items if i.metric_evidence_id is not None}
        )
        unique: dict[str, AnomalyOut] = {}
        for item in detected.items:
            if item.anomaly is not None:
                unique.setdefault(item.anomaly.evidence_id, item.anomaly)
        anomalies = sorted(
            (self._with_contributors(a) for a in unique.values()),
            key=lambda a: (_SEVERITY_RANK[a.severity], a.evidence_id),
        )

        bundle = EvidenceBundleAssembler(
            self.session, event_lookback_hours=self.settings.evidence_event_lookback_hours
        ).assemble(None)
        evidence = AnalysisEvidenceOut(
            allowed_evidence_ids=bundle.allowed_evidence_ids,
            metric_count=len(bundle.metrics),
            anomaly_count=len(bundle.anomalies),
            contributor_count=len(bundle.contributors),
            related_event_count=len(bundle.related_events),
            signature=bundle.signature,
        )

        return AnalysisRunResponse(
            window_start=detected.window_start,
            window_end=detected.window_end,
            metric_windows_computed=history.computed,
            metric_evidence_ids=metric_ids,
            anomalies=anomalies,
            evidence=evidence,
            brief=self._brief(),
        )

    def _with_contributors(self, anomaly: AnomalyOut) -> AnalysisAnomalyOut:
        status: ContributorRunStatus
        segment_ids: list[str] = []
        try:
            result = ContributorService(self.session).compute(anomaly.evidence_id)
        except SegmentationNotSupportedError:
            status = "not_supported"
        else:
            status = result.status
            segment_ids = [c.evidence_id for g in result.groups for c in g.contributors]
        return AnalysisAnomalyOut(
            evidence_id=anomaly.evidence_id,
            metric_evidence_id=anomaly.metric_evidence_id,
            metric_key=anomaly.metric_key,
            display_name=anomaly.display_name,
            dimensions=anomaly.dimensions,
            severity=anomaly.severity,
            contributor_status=status,
            contributor_evidence_ids=segment_ids,
        )

    def _brief(self) -> AnalysisBriefOut:
        if not self.settings.llm_configured or self.brief_client_factory is None:
            return AnalysisBriefOut(
                state="not_configured",
                brief_id=None,
                status=None,
                error_code="LLM_NOT_CONFIGURED",
                message="OPENAI_API_KEY and OPENAI_MODEL are not configured; no brief generated.",
            )
        try:
            brief = BriefService(self.session, self.settings, self.brief_client_factory).generate()
        except (LLMError, BriefError) as exc:
            # The deterministic stages are already committed; report the failure explicitly.
            return AnalysisBriefOut(
                state="failed", brief_id=None, status=None, error_code=exc.code, message=exc.message
            )
        return AnalysisBriefOut(
            state="generated", brief_id=brief.id, status=brief.status, error_code=None, message=None
        )
