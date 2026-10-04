"""Contributor use cases: compute and persist idempotently, read back with provenance.

Contributor statements describe the *share of observed change* in a segment.
They never assert a cause.
"""

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.observability import stage_timer
from app.models import Anomaly, AnomalyContributor, MetricSnapshot
from app.models.enums import EvidenceType
from app.repositories.anomaly_repository import AnomalyRepository
from app.repositories.contributor_repository import ContributorRepository
from app.schemas.contributors import (
    ContributorAnalysisResponse,
    ContributorGroupOut,
    ContributorOut,
    UnrankedFamilyOut,
)
from app.services.anomalies.errors import AnomalyNotFoundError, InvalidEvidenceIdError
from app.services.contributors.engine import AnalysisResult, analyze, base_filters_of
from app.services.contributors.errors import ContributorsNotComputedError
from app.services.contributors.formulas import (
    ANALYSIS_VERSION,
    FAMILIES,
    ContributorFamily,
    FamilyStatus,
    Method,
    display_label,
    formula_for,
    segment_value,
)
from app.services.contributors.provenance import ContributorProvenance
from app.services.evidence_ids import allocate_evidence_id, parse_evidence_id
from app.services.metrics.definitions import METRIC_REGISTRY, Dimension
from app.services.metrics.engine import quantize
from app.services.metrics.provenance import WindowProvenance

_FAMILY_BY_KEY = {family.key: family for family in FAMILIES}


def statement_for(label: str, pct: Decimal, display_name: str, method: Method) -> str:
    if method is Method.RATE_EXCESS:
        return (
            f"{label} accounts for {pct:.1f}% of the observed excess {display_name} events "
            "relative to the 7-day baseline rate."
        )
    return (
        f"{label} accounts for {pct:.1f}% of the observed positive change in "
        f"{display_name} relative to the 7-day baseline."
    )


def _segment_map(family: ContributorFamily, value: str) -> dict[Dimension, str]:
    return dict(zip(family.dimensions, value.split("|"), strict=True))


def _contributor_out(row: AnomalyContributor, family: ContributorFamily) -> ContributorOut:
    provenance = ContributorProvenance.model_validate(row.provenance_json)
    segment = _segment_map(family, row.segment_value)
    display_name = METRIC_REGISTRY[provenance.metric_key].display_name
    label = display_label(segment)
    return ContributorOut(
        evidence_id=row.evidence_id,
        rank=row.rank,
        segment={str(dim): value for dim, value in segment.items()},
        label=label,
        current_value=float(row.current_value),
        baseline_value=float(row.baseline_value),
        delta_value=float(row.delta_value),
        contribution_pct=float(row.contribution_pct),
        flags=list(provenance.flags),
        statement=statement_for(label, row.contribution_pct, display_name, provenance.method),
        provenance=provenance,
    )


class ContributorService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.anomalies = AnomalyRepository(session)
        self.repo = ContributorRepository(session)

    # --- compute ---------------------------------------------------------------------

    def compute(self, evidence_id: str) -> ContributorAnalysisResponse:
        """Timed entry point; see ``_compute``."""
        with stage_timer("contributor_computation", evidence_id=evidence_id[:64]) as stage:
            response = self._compute(evidence_id)
            stage.update(outcome=response.status, family_count=len(response.groups))
            return response

    def _compute(self, evidence_id: str) -> ContributorAnalysisResponse:
        """Compute and persist contributors for an anomaly; a repeat call reuses the rows.

        Raises:
            InvalidEvidenceIdError / AnomalyNotFoundError: bad or unknown ``ANOM-`` ID.
            SegmentationNotSupportedError: the anomaly's metric is not additive.
            WindowMismatchError: the snapshot does not use the standard windows.
        """
        anomaly, snapshot = self._load(evidence_id)
        existing = self.repo.list_for_anomaly(anomaly.id)
        if existing:
            return self._response(anomaly, snapshot, existing, "reused", [])

        analysis = analyze(self.session, snapshot, self.repo.support_team_keys())
        self._persist(anomaly, snapshot, analysis, datetime.now(UTC))
        self.session.commit()

        rows = self.repo.list_for_anomaly(anomaly.id)
        unranked = [
            UnrankedFamilyOut(family_key=r.family.key, status=r.ranking.status)
            for r in analysis.families
            if r.ranking.status is not FamilyStatus.RANKED
        ]
        return self._response(anomaly, snapshot, rows, "computed", unranked)

    def _persist(
        self,
        anomaly: Anomaly,
        snapshot: MetricSnapshot,
        analysis: AnalysisResult,
        computed_at: datetime,
    ) -> None:
        window = analysis.window
        base_filters = {str(dim): value for dim, value in base_filters_of(snapshot).items()}
        formula = formula_for(analysis.method)
        for family_result in analysis.families:
            ranking = family_result.ranking
            for ranked in ranking.ranked:
                item = ranked.delta
                is_rate = item.method is Method.RATE_EXCESS
                parent_sourced = any(
                    flag.value == "baseline_rate_from_parent_slice" for flag in item.flags
                )
                provenance = ContributorProvenance(
                    analysis_version=ANALYSIS_VERSION,
                    anomaly_evidence_id=anomaly.evidence_id,
                    metric_evidence_id=snapshot.evidence_id,
                    metric_key=snapshot.metric_key,
                    family_key=family_result.family.key,
                    segment={str(dim): value for dim, value in item.segment.items()},
                    base_filters=base_filters,
                    method=item.method,
                    formula=formula,
                    current_window=WindowProvenance(
                        start=window.current.start, end=window.current.end
                    ),
                    baseline_window=WindowProvenance(
                        start=window.baseline.start, end=window.baseline.end
                    ),
                    baseline_days=[
                        WindowProvenance(start=day.start, end=day.end)
                        for day in window.baseline_days
                    ],
                    current_events=item.current_events,
                    current_denominator=item.current_denominator,
                    baseline_value=None if is_rate else item.baseline_value,
                    baseline_numerator=item.baseline_numerator if is_rate else None,
                    baseline_denominator=item.baseline_denominator if is_rate else None,
                    baseline_rate=item.baseline_rate,
                    baseline_rate_source=(
                        None if not is_rate else "parent_slice" if parent_sourced else "segment"
                    ),
                    expected_events=item.baseline_value if is_rate else None,
                    delta=item.delta,
                    family_positive_delta_total=ranking.positive_total,
                    family_suppressed_contribution_pct=ranking.suppressed_contribution_pct,
                    sample=item.sample,
                    min_sample=ranking.min_sample,
                    sample_sufficient=item.sample >= ranking.min_sample,
                    flags=list(item.flags),
                    computed_at=computed_at,
                )
                self.repo.insert_if_absent(
                    {
                        "evidence_id": allocate_evidence_id(self.session, EvidenceType.SEGMENT),
                        "anomaly_id": anomaly.id,
                        "dimension_key": family_result.family.key,
                        "segment_value": segment_value(item.segment),
                        "current_value": item.current_value,
                        "baseline_value": item.baseline_value,
                        "delta_value": item.delta,
                        "contribution_pct": ranked.contribution_pct,
                        "rank": ranked.rank,
                        "provenance_json": provenance.model_dump(mode="json"),
                    }
                )

    # --- read ------------------------------------------------------------------------

    def get(self, evidence_id: str) -> ContributorAnalysisResponse:
        """Stored contributor groups for an anomaly.

        Raises:
            ContributorsNotComputedError: nothing has been stored for this anomaly.
        """
        anomaly, snapshot = self._load(evidence_id)
        rows = self.repo.list_for_anomaly(anomaly.id)
        if not rows:
            raise ContributorsNotComputedError(
                f"No contributors are stored for {evidence_id}; compute them first."
            )
        return self._response(anomaly, snapshot, rows, "reused", [])

    def _load(self, evidence_id: str) -> tuple[Anomaly, MetricSnapshot]:
        parsed = parse_evidence_id(evidence_id)
        if parsed is None or parsed[0] is not EvidenceType.ANOMALY:
            raise InvalidEvidenceIdError(f"{evidence_id!r} is not a valid ANOM- evidence ID.")
        found = self.anomalies.get_with_snapshot(evidence_id)
        if found is None:
            raise AnomalyNotFoundError(f"Anomaly {evidence_id} was not found.")
        return found

    def _response(
        self,
        anomaly: Anomaly,
        snapshot: MetricSnapshot,
        rows: list[AnomalyContributor],
        status: str,
        unranked: list[UnrankedFamilyOut],
    ) -> ContributorAnalysisResponse:
        by_family: dict[str, list[AnomalyContributor]] = {}
        for row in rows:
            by_family.setdefault(row.dimension_key, []).append(row)

        groups: list[ContributorGroupOut] = []
        for family in FAMILIES:  # registry order, independent of storage order
            family_rows = by_family.get(family.key)
            if not family_rows:
                continue
            contributors = [_contributor_out(row, family) for row in family_rows]
            first = contributors[0].provenance
            ranked_pct = sum((row.contribution_pct for row in family_rows), Decimal(0))
            groups.append(
                ContributorGroupOut(
                    family_key=family.key,
                    dimensions=[str(dim) for dim in family.dimensions],
                    method=first.method,
                    formula=first.formula,
                    positive_delta_total=float(first.family_positive_delta_total),
                    contributors=contributors,
                    other_contribution_pct=float(
                        quantize(max(Decimal(100) - ranked_pct, Decimal(0)))
                    ),
                    suppressed_contribution_pct=float(first.family_suppressed_contribution_pct),
                )
            )
        return ContributorAnalysisResponse(
            anomaly_evidence_id=anomaly.evidence_id,
            metric_evidence_id=snapshot.evidence_id,
            metric_key=snapshot.metric_key,
            display_name=METRIC_REGISTRY[snapshot.metric_key].display_name,
            window_start=snapshot.window_start,
            window_end=snapshot.window_end,
            status="computed" if status == "computed" else "reused",
            groups=groups,
            unranked_families=unranked,
        )
