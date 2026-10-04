"""Resolve evidence IDs against their persisted sources.

``existing`` is the bulk existence check used by the bundle assembler and the claim
validator. ``resolve`` builds the typed provenance envelope behind one ID, reusing the
same read-side builders as the metric, anomaly and contributor APIs. Nothing is computed
here: every value comes from a stored row and its stored provenance.
"""

from collections.abc import Iterable

from sqlalchemy.orm import Session

from app.models import Incident
from app.models.enums import EvidenceType
from app.repositories.anomaly_repository import AnomalyRepository as AnomalySnapshotRepository
from app.repositories.evidence import (
    AnomalyContributorRepository,
    AnomalyRepository,
    IncidentRepository,
    MetricSnapshotRepository,
)
from app.schemas.evidence import (
    CONTRIBUTOR_CONTEXT_NOTE,
    EVENT_CONTEXT_NOTE,
    AnomalyDetailProvenance,
    ContributorDetailProvenance,
    EventDetailProvenance,
    EvidenceDetailOut,
    EvidenceMethod,
    EvidenceValue,
    MetricDetailProvenance,
    WindowOut,
)
from app.services.anomalies.detector import ThresholdDetails
from app.services.anomalies.service import anomaly_out
from app.services.contributors.provenance import ContributorProvenance
from app.services.contributors.service import ContributorService
from app.services.evidence.errors import EvidenceNotFoundError, InvalidEvidenceIdError
from app.services.evidence.events import event_details
from app.services.evidence_ids import parse_evidence_id
from app.services.metrics.service import snapshot_out

PP_UNIT = "percentage_points"
PERCENT_UNIT = "percent"


def _scope(dimensions: dict[str, str]) -> str:
    if not dimensions:
        return "overall"
    return ", ".join(f"{key}={value}" for key, value in sorted(dimensions.items()))


class EvidenceResolver:
    def __init__(self, session: Session) -> None:
        self.session = session
        self._repos = {
            EvidenceType.EVENT: IncidentRepository(session),
            EvidenceType.METRIC: MetricSnapshotRepository(session),
            EvidenceType.ANOMALY: AnomalyRepository(session),
            EvidenceType.SEGMENT: AnomalyContributorRepository(session),
        }

    def existing(self, evidence_ids: Iterable[str]) -> set[str]:
        """The IDs that are well formed and present in persisted evidence."""
        grouped: dict[EvidenceType, set[str]] = {}
        for evidence_id in evidence_ids:
            parsed = parse_evidence_id(evidence_id)
            if parsed is not None:
                grouped.setdefault(parsed[0], set()).add(evidence_id)
        found: set[str] = set()
        for evidence_type, ids in grouped.items():
            found |= self._repos[evidence_type].existing_evidence_ids(ids)
        return found

    def resolve(self, evidence_id: str) -> EvidenceDetailOut:
        """The provenance envelope for one persisted evidence ID.

        Raises:
            InvalidEvidenceIdError: not a well-formed MTR/ANOM/SEG/EVT ID.
            EvidenceNotFoundError: well formed but not present in persisted evidence.
        """
        parsed = parse_evidence_id(evidence_id)
        if parsed is None:
            raise InvalidEvidenceIdError(f"{evidence_id!r} is not a valid evidence ID.")
        builders = {
            EvidenceType.METRIC: self._metric,
            EvidenceType.ANOMALY: self._anomaly,
            EvidenceType.SEGMENT: self._contributor,
            EvidenceType.EVENT: self._event,
        }
        detail = builders[parsed[0]](evidence_id)
        if detail is None:
            raise EvidenceNotFoundError(f"Evidence {evidence_id} was not found.")
        return detail

    # --- per type --------------------------------------------------------------------

    def _metric(self, evidence_id: str) -> EvidenceDetailOut | None:
        row = self._repos[EvidenceType.METRIC].get_by_evidence_id(evidence_id)
        if row is None:
            return None
        out = snapshot_out(row)
        definition = out.provenance.definition
        undefined_change = None
        if out.baseline_empty:
            undefined_change = "No baseline data; change is undefined."
        elif out.baseline_zero:
            undefined_change = "Baseline is zero; percentage change is undefined."
        values = [
            EvidenceValue(key="value", label="Current value", value=out.value, unit=out.unit),
            EvidenceValue(
                key="baseline_value",
                label="Baseline value",
                value=out.baseline_value,
                unit=out.unit,
                note="No baseline data." if out.baseline_value is None else None,
            ),
            EvidenceValue(
                key="change_pct",
                label="Change vs baseline",
                value=out.change_pct,
                unit=PERCENT_UNIT,
                note=undefined_change if out.change_pct is None else None,
            ),
        ]
        if out.change_pp is not None:
            values.append(
                EvidenceValue(
                    key="change_pp",
                    label="Change vs baseline (points)",
                    value=out.change_pp,
                    unit=PP_UNIT,
                )
            )
        baseline_window = (
            WindowOut(start=out.baseline_start, end=out.baseline_end)
            if out.baseline_start is not None and out.baseline_end is not None
            else None
        )
        return EvidenceDetailOut(
            evidence_id=out.evidence_id,
            evidence_type=EvidenceType.METRIC,
            evidence_class="observed_fact",
            label=f"{out.display_name} ({_scope(out.dimensions)})",
            window=WindowOut(start=out.window_start, end=out.window_end),
            baseline_window=baseline_window,
            dimensions=dict(out.dimensions),
            sample_size=out.sample_size,
            sample_sufficient=out.sample_sufficient,
            values=values,
            method=EvidenceMethod(
                kind="metric_calculation",
                name=out.metric_key,
                version=str(definition.version),
                formula=definition.formula,
            ),
            related_evidence_ids=[],
            contextual_disclaimer=None,
            provenance=MetricDetailProvenance(computed_at=row.computed_at, metric=out.provenance),
        )

    def _anomaly(self, evidence_id: str) -> EvidenceDetailOut | None:
        found = AnomalySnapshotRepository(self.session).get_with_snapshot(evidence_id)
        if found is None:
            return None
        anomaly, snapshot = found
        out = anomaly_out(anomaly, snapshot)
        threshold = ThresholdDetails.model_validate(anomaly.threshold_json)
        score_unit = PP_UNIT if threshold.comparison == "percentage_points" else PERCENT_UNIT
        metric = snapshot_out(snapshot)
        return EvidenceDetailOut(
            evidence_id=out.evidence_id,
            evidence_type=EvidenceType.ANOMALY,
            evidence_class="observed_fact",
            label=f"{out.severity.value.title()} anomaly: {out.display_name} "
            f"({_scope(out.dimensions)})",
            window=WindowOut(start=metric.window_start, end=metric.window_end),
            baseline_window=(
                WindowOut(start=metric.baseline_start, end=metric.baseline_end)
                if metric.baseline_start is not None and metric.baseline_end is not None
                else None
            ),
            dimensions=dict(out.dimensions),
            sample_size=metric.sample_size,
            sample_sufficient=metric.sample_sufficient,
            values=[
                EvidenceValue(key="severity", label="Severity", value=out.severity.value),
                EvidenceValue(
                    key="score", label="Observed change", value=out.score, unit=score_unit
                ),
                EvidenceValue(
                    key="medium_threshold",
                    label="Medium threshold",
                    value=threshold.medium_threshold,
                    unit=score_unit,
                ),
                EvidenceValue(
                    key="high_threshold",
                    label="High threshold",
                    value=threshold.high_threshold,
                    unit=score_unit,
                ),
                EvidenceValue(key="value", label="Current value", value=out.value, unit=out.unit),
                EvidenceValue(
                    key="baseline_value",
                    label="Baseline value",
                    value=out.baseline_value,
                    unit=out.unit,
                ),
            ],
            method=EvidenceMethod(
                kind="anomaly_detector",
                name=out.detector_key,
                description=out.explanation,
            ),
            related_evidence_ids=[out.metric_evidence_id],
            contextual_disclaimer=None,
            provenance=AnomalyDetailProvenance(
                detected_at=anomaly.detected_at, threshold=threshold
            ),
        )

    def _contributor(self, evidence_id: str) -> EvidenceDetailOut | None:
        row = self._repos[EvidenceType.SEGMENT].get_by_evidence_id(evidence_id)
        if row is None:
            return None
        stored = ContributorProvenance.model_validate(row.provenance_json)
        analysis = ContributorService(self.session).get(stored.anomaly_evidence_id)  # read-only
        for group in analysis.groups:
            for contributor in group.contributors:
                if contributor.evidence_id != evidence_id:
                    continue
                provenance = contributor.provenance
                return EvidenceDetailOut(
                    evidence_id=evidence_id,
                    evidence_type=EvidenceType.SEGMENT,
                    evidence_class="observed_fact",
                    label=f"{contributor.label} ({group.family_key}, rank {contributor.rank})",
                    window=WindowOut(
                        start=provenance.current_window.start, end=provenance.current_window.end
                    ),
                    baseline_window=WindowOut(
                        start=provenance.baseline_window.start, end=provenance.baseline_window.end
                    ),
                    dimensions={**provenance.base_filters, **contributor.segment},
                    sample_size=provenance.sample,
                    sample_sufficient=provenance.sample_sufficient,
                    values=[
                        EvidenceValue(key="rank", label="Rank", value=contributor.rank),
                        EvidenceValue(
                            key="contribution_pct",
                            label="Share of observed change",
                            value=contributor.contribution_pct,
                            unit=PERCENT_UNIT,
                        ),
                        EvidenceValue(
                            key="current_value",
                            label="Current value",
                            value=contributor.current_value,
                        ),
                        EvidenceValue(
                            key="baseline_value",
                            label="Baseline value",
                            value=contributor.baseline_value,
                        ),
                        EvidenceValue(
                            key="delta_value",
                            label="Observed change",
                            value=contributor.delta_value,
                        ),
                    ],
                    method=EvidenceMethod(
                        kind="contribution",
                        name=str(group.method),
                        version=provenance.analysis_version,
                        formula=group.formula,
                    ),
                    related_evidence_ids=[
                        provenance.anomaly_evidence_id,
                        provenance.metric_evidence_id,
                    ],
                    contextual_disclaimer=CONTRIBUTOR_CONTEXT_NOTE,
                    provenance=ContributorDetailProvenance(
                        statement=contributor.statement, contribution=provenance
                    ),
                )
        return None

    def _event(self, evidence_id: str) -> EvidenceDetailOut | None:
        incident: Incident | None = self._repos[EvidenceType.EVENT].get_by_evidence_id(evidence_id)
        if incident is None:
            return None
        product = None if incident.product is None else str(incident.product)
        return EvidenceDetailOut(
            evidence_id=evidence_id,
            evidence_type=EvidenceType.EVENT,
            evidence_class="contextual_event",
            label=incident.title,
            window=None,
            baseline_window=None,
            dimensions={} if product is None else {"product": product},
            sample_size=None,
            sample_sufficient=None,
            values=[
                EvidenceValue(key="event_type", label="Event type", value=incident.event_type),
                EvidenceValue(key="product", label="Product", value=product),
            ],
            method=EvidenceMethod(kind="timeline_event", name="incident_timeline"),
            related_evidence_ids=[],
            contextual_disclaimer=EVENT_CONTEXT_NOTE,
            provenance=EventDetailProvenance(
                event_type=incident.event_type,
                occurred_at=incident.occurred_at,
                details=event_details(incident),
            ),
        )
