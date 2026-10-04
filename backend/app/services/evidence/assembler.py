"""Assemble the Evidence Bundle from persisted deterministic evidence.

Read-only and deterministic for a fixed database state and window: nothing is computed,
detected or written here. Metrics come from stored snapshots, anomalies from stored
detections, contributors from stored contributor rows (never computed on demand), and
timeline events from stored incidents. Raw ticket rows never enter the bundle.
"""

from collections.abc import Mapping
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Incident, MetricSnapshot
from app.models.enums import AnomalyStatus
from app.repositories.anomaly_repository import AnomalyRepository
from app.repositories.evidence import IncidentRepository
from app.schemas.contributors import ContributorGroupOut, ContributorOut
from app.schemas.evidence import (
    AnalysisWindowOut,
    AnomalyEvidence,
    BundleLimits,
    ContributorEvidence,
    ContributorStatus,
    EvidenceBundle,
    ExcludedEvidence,
    ExclusionReason,
    MetricEvidence,
    MetricRole,
    ProvenanceSummary,
    RelatedEventEvidence,
    WindowOut,
)
from app.schemas.metrics import MetricSnapshotOut
from app.services.anomalies.service import LIST_MAX_LIMIT, anomaly_out
from app.services.contributors.errors import ContributorsNotComputedError
from app.services.contributors.service import ContributorService
from app.services.evidence.events import event_details
from app.services.evidence.resolver import EvidenceResolver
from app.services.metrics.definitions import METRIC_REGISTRY
from app.services.metrics.engine import analysis_window, to_utc
from app.services.metrics.provenance import MetricProvenance
from app.services.metrics.service import MetricsService, snapshot_out

MAX_ANOMALIES = 5
CONTRIBUTORS_PER_FAMILY = 3
MAX_RELATED_EVENTS = 5

_METRIC_ORDER = {key: index for index, key in enumerate(METRIC_REGISTRY)}


def _scope(dimensions: Mapping[str, str]) -> str:
    if not dimensions:
        return "overall"
    return ", ".join(f"{key}={value}" for key, value in sorted(dimensions.items()))


def _metric_evidence(out: MetricSnapshotOut, role: MetricRole) -> MetricEvidence:
    return MetricEvidence(
        evidence_id=out.evidence_id,
        label=f"{out.display_name} ({_scope(out.dimensions)})",
        window=WindowOut(start=out.window_start, end=out.window_end),
        dimensions=dict(out.dimensions),
        provenance=ProvenanceSummary(
            source="metric_snapshot",
            formula=out.provenance.definition.formula,
            sample_size=out.sample_size,
            computed_at=out.computed_at,
        ),
        role=role,
        metric_key=out.metric_key,
        unit=out.unit,
        value=out.value,
        baseline_value=out.baseline_value,
        change_pct=out.change_pct,
        change_pp=out.change_pp,
        baseline_zero=out.baseline_zero,
        baseline_empty=out.baseline_empty,
        sample_size=out.sample_size,
        sample_sufficient=out.sample_sufficient,
    )


def _exclusion(evidence_id: str, reason: ExclusionReason) -> ExcludedEvidence:
    return ExcludedEvidence(evidence_id=evidence_id, reason=reason)


class EvidenceBundleAssembler:
    def __init__(self, session: Session, *, event_lookback_hours: int | None = None) -> None:
        self.session = session
        self.lookback_hours = (
            event_lookback_hours
            if event_lookback_hours is not None
            else get_settings().evidence_event_lookback_hours
        )
        self.metrics = MetricsService(session)
        self.anomalies = AnomalyRepository(session)
        self.contributors = ContributorService(session)
        self.incidents = IncidentRepository(session)
        self.resolver = EvidenceResolver(session)

    def assemble(self, window_end: datetime | None = None) -> EvidenceBundle:
        """The bundle for ``window_end``, or for the latest computed window when omitted."""
        limits = BundleLimits(
            max_anomalies=MAX_ANOMALIES,
            contributors_per_family=CONTRIBUTORS_PER_FAMILY,
            max_related_events=MAX_RELATED_EVENTS,
            event_lookback_hours=self.lookback_hours,
        )
        overview = self.metrics.overview(None if window_end is None else to_utc(window_end))
        if overview.window_end is None:
            return EvidenceBundle.create(
                analysis_window=None,
                metrics=[],
                anomalies=[],
                contributors=[],
                related_events=[],
                excluded=[],
                limits=limits,
            )

        window = analysis_window(overview.window_end)
        current = WindowOut(start=window.current.start, end=window.current.end)
        excluded: list[ExcludedEvidence] = []

        anomalies, contributors, triggers = self._anomaly_evidence(current, excluded)
        metrics = self._metric_evidence(overview.items, triggers, current, excluded)
        events = self._event_evidence(current, excluded)

        metrics, anomalies, contributors, events = self._resolved(
            metrics, anomalies, contributors, events, excluded
        )
        unique_excluded = {(e.evidence_id, e.reason): e for e in excluded}
        return EvidenceBundle.create(
            analysis_window=AnalysisWindowOut(
                current=current,
                baseline=WindowOut(start=window.baseline.start, end=window.baseline.end),
                event_lookback_hours=self.lookback_hours,
            ),
            metrics=metrics,
            anomalies=anomalies,
            contributors=contributors,
            related_events=events,
            excluded=[unique_excluded[key] for key in sorted(unique_excluded)],
            limits=limits,
        )

    # --- metrics ---------------------------------------------------------------------

    def _metric_evidence(
        self,
        overview: list[MetricSnapshotOut],
        triggers: dict[str, MetricSnapshotOut],
        current: WindowOut,
        excluded: list[ExcludedEvidence],
    ) -> list[MetricEvidence]:
        by_id: dict[str, MetricEvidence] = {}
        for out in overview:
            if WindowOut(start=out.window_start, end=out.window_end) != current:
                excluded.append(_exclusion(out.evidence_id, ExclusionReason.WINDOW_MISMATCH))
                continue
            role: MetricRole = "anomaly_trigger" if out.evidence_id in triggers else "overview"
            by_id[out.evidence_id] = _metric_evidence(out, role)
        for evidence_id, out in triggers.items():
            by_id.setdefault(evidence_id, _metric_evidence(out, "anomaly_trigger"))
        return sorted(
            by_id.values(),
            key=lambda m: (
                _METRIC_ORDER.get(m.metric_key, len(_METRIC_ORDER)),
                sorted(m.dimensions.items()),
                m.evidence_id,
            ),
        )

    # --- anomalies and their contributors -------------------------------------------

    def _anomaly_evidence(
        self, current: WindowOut, excluded: list[ExcludedEvidence]
    ) -> tuple[list[AnomalyEvidence], list[ContributorEvidence], dict[str, MetricSnapshotOut]]:
        rows, _ = self.anomalies.list_with_snapshots(
            severity=None,
            status=AnomalyStatus.ACTIVE,
            metric_key=None,
            start=current.end,
            end=current.end,
            limit=LIST_MAX_LIMIT,
            offset=0,
        )
        anomalies: list[AnomalyEvidence] = []
        contributors: list[ContributorEvidence] = []
        triggers: dict[str, MetricSnapshotOut] = {}
        for anomaly, snapshot in rows:  # most severe first
            evidence_id = anomaly.evidence_id
            if WindowOut(start=snapshot.window_start, end=snapshot.window_end) != current:
                excluded.append(_exclusion(evidence_id, ExclusionReason.WINDOW_MISMATCH))
                continue
            if self._is_stale(snapshot):
                excluded.append(_exclusion(evidence_id, ExclusionReason.STALE_DEFINITION_VERSION))
                continue
            if len(anomalies) >= MAX_ANOMALIES:
                excluded.append(_exclusion(evidence_id, ExclusionReason.OVER_LIMIT))
                continue

            summary = anomaly_out(anomaly, snapshot)
            trigger = snapshot_out(snapshot)
            triggers[trigger.evidence_id] = trigger
            items, status = self._contributor_evidence(
                evidence_id, trigger.evidence_id, current, excluded
            )
            contributors.extend(items)
            anomalies.append(
                AnomalyEvidence(
                    evidence_id=evidence_id,
                    label=f"{summary.severity.value.title()} anomaly: {summary.display_name} "
                    f"({_scope(summary.dimensions)})",
                    window=current,
                    dimensions=dict(summary.dimensions),
                    provenance=ProvenanceSummary(
                        source=f"anomaly_detector:{summary.detector_key}",
                        sample_size=snapshot.sample_size,
                        computed_at=summary.detected_at,
                    ),
                    metric_evidence_id=summary.metric_evidence_id,
                    metric_key=summary.metric_key,
                    severity=summary.severity,
                    score=summary.score,
                    score_comparison=summary.score_comparison,
                    detector_key=summary.detector_key,
                    explanation=summary.explanation,
                    contributor_status=status,
                    contributor_evidence_ids=[c.evidence_id for c in items],
                )
            )
        return anomalies, contributors, triggers

    @staticmethod
    def _is_stale(snapshot: MetricSnapshot) -> bool:
        definition = METRIC_REGISTRY.get(snapshot.metric_key)
        provenance = MetricProvenance.model_validate(snapshot.provenance_json)
        return definition is None or provenance.definition.version != definition.version

    def _contributor_evidence(
        self,
        anomaly_id: str,
        metric_id: str,
        current: WindowOut,
        excluded: list[ExcludedEvidence],
    ) -> tuple[list[ContributorEvidence], ContributorStatus]:
        try:
            analysis = self.contributors.get(anomaly_id)  # stored rows only; never computes
        except ContributorsNotComputedError:
            return [], "not_computed"

        items: list[ContributorEvidence] = []
        for group in analysis.groups:
            for contributor in group.contributors:
                provenance = contributor.provenance
                if (
                    provenance.anomaly_evidence_id != anomaly_id
                    or provenance.metric_evidence_id != metric_id
                    or WindowOut(
                        start=provenance.current_window.start, end=provenance.current_window.end
                    )
                    != current
                ):
                    excluded.append(
                        _exclusion(contributor.evidence_id, ExclusionReason.WINDOW_MISMATCH)
                    )
                elif contributor.rank > CONTRIBUTORS_PER_FAMILY:
                    excluded.append(_exclusion(contributor.evidence_id, ExclusionReason.OVER_LIMIT))
                else:
                    items.append(_contributor_item(anomaly_id, group, contributor, current))
        return items, "available" if items else "none_ranked"

    # --- timeline events -------------------------------------------------------------

    def _event_evidence(
        self, current: WindowOut, excluded: list[ExcludedEvidence]
    ) -> list[RelatedEventEvidence]:
        start = current.start - timedelta(hours=self.lookback_hours)
        events: list[RelatedEventEvidence] = []
        for incident in self.incidents.list_between(start, current.end):  # newest first
            if len(events) >= MAX_RELATED_EVENTS:
                excluded.append(_exclusion(incident.evidence_id, ExclusionReason.OVER_LIMIT))
            else:
                events.append(_event_item(incident, current))
        return events

    # --- final resolution pass -------------------------------------------------------

    def _resolved(
        self,
        metrics: list[MetricEvidence],
        anomalies: list[AnomalyEvidence],
        contributors: list[ContributorEvidence],
        events: list[RelatedEventEvidence],
        excluded: list[ExcludedEvidence],
    ) -> tuple[
        list[MetricEvidence],
        list[AnomalyEvidence],
        list[ContributorEvidence],
        list[RelatedEventEvidence],
    ]:
        """Keep only items whose IDs exist in persisted evidence, and what still cites them."""
        existing = self.resolver.existing(
            item.evidence_id for item in (*metrics, *anomalies, *contributors, *events)
        )

        def ok(evidence_id: str, parent_kept: bool = True) -> bool:
            if evidence_id in existing and parent_kept:
                return True
            excluded.append(_exclusion(evidence_id, ExclusionReason.UNRESOLVED))
            return False

        metrics = [m for m in metrics if ok(m.evidence_id)]
        metric_ids = {m.evidence_id for m in metrics}
        anomalies = [a for a in anomalies if ok(a.evidence_id, a.metric_evidence_id in metric_ids)]
        anomaly_ids = {a.evidence_id for a in anomalies}
        contributors = [
            c for c in contributors if ok(c.evidence_id, c.anomaly_evidence_id in anomaly_ids)
        ]
        contributor_ids = {c.evidence_id for c in contributors}
        anomalies = [_without_missing(a, contributor_ids) for a in anomalies]
        return metrics, anomalies, contributors, [e for e in events if ok(e.evidence_id)]


def _without_missing(anomaly: AnomalyEvidence, contributor_ids: set[str]) -> AnomalyEvidence:
    kept = [i for i in anomaly.contributor_evidence_ids if i in contributor_ids]
    if len(kept) == len(anomaly.contributor_evidence_ids):
        return anomaly
    return anomaly.model_copy(
        update={
            "contributor_evidence_ids": kept,
            "contributor_status": "available" if kept else "none_ranked",
        }
    )


def _contributor_item(
    anomaly_id: str,
    group: ContributorGroupOut,
    contributor: ContributorOut,
    current: WindowOut,
) -> ContributorEvidence:
    provenance = contributor.provenance
    return ContributorEvidence(
        evidence_id=contributor.evidence_id,
        label=f"{contributor.label} ({group.family_key}, rank {contributor.rank})",
        window=current,
        dimensions=dict(provenance.base_filters),
        provenance=ProvenanceSummary(
            source=f"contributor_analysis:{provenance.analysis_version}",
            formula=group.formula,
            sample_size=provenance.sample,
            computed_at=provenance.computed_at,
        ),
        anomaly_evidence_id=anomaly_id,
        metric_evidence_id=provenance.metric_evidence_id,
        family_key=group.family_key,
        segment=dict(contributor.segment),
        rank=contributor.rank,
        current_value=contributor.current_value,
        baseline_value=contributor.baseline_value,
        delta_value=contributor.delta_value,
        contribution_pct=contributor.contribution_pct,
        method=str(group.method),
        sample=provenance.sample,
        min_sample=provenance.min_sample,
        sample_sufficient=provenance.sample_sufficient,
        flags=[str(flag) for flag in contributor.flags],
        statement=contributor.statement,
    )


def _event_item(incident: Incident, current: WindowOut) -> RelatedEventEvidence:
    details = event_details(incident)
    return RelatedEventEvidence(
        evidence_id=incident.evidence_id,
        label=incident.title,
        window=None,
        dimensions={} if incident.product is None else {"product": str(incident.product)},
        provenance=ProvenanceSummary(source="incident_timeline"),
        event_type=incident.event_type,
        title=incident.title,
        occurred_at=incident.occurred_at,
        product=None if incident.product is None else str(incident.product),
        hours_from_window_start=round(
            (incident.occurred_at - current.start).total_seconds() / 3600, 2
        ),
        details=details,
    )
