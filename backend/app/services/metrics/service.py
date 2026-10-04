"""Metrics use cases: validate -> compute -> persist, and snapshot read paths.

Snapshots are immutable evidence. Repeating an analysis with the same signature
returns the existing snapshot (same ``MTR-`` ID) instead of writing a new row.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.core.observability import stage_timer
from app.models import MetricSnapshot
from app.models.enums import EvidenceType
from app.repositories.metric_repository import MetricRepository
from app.schemas.metrics import (
    ComputeStatus,
    MetricComputeItem,
    MetricComputeResponse,
    MetricDefinitionOut,
    MetricFilters,
    MetricOverviewResponse,
    MetricSeriesResponse,
    MetricSnapshotOut,
)
from app.services.evidence_ids import allocate_evidence_id
from app.services.metrics.definitions import (
    METRIC_REGISTRY,
    Dimension,
    MetricDefinition,
    get_metric_definition,
)
from app.services.metrics.engine import (
    BASELINE_WINDOW_COUNT,
    WINDOW_LENGTH,
    AnalysisWindow,
    MetricResult,
    analysis_window,
    compute_metric,
    to_utc,
    utc_midnight,
)
from app.services.metrics.errors import (
    InvalidDimensionValueError,
    InvalidWindowRangeError,
    MetricNotFoundError,
    NoSourceDataError,
    WindowOutOfRangeError,
)
from app.services.metrics.provenance import (
    MetricProvenance,
    analysis_signature,
    build_provenance,
    canonical_filters,
)
from app.services.metrics.queries import fetch_bucket_aggregates

SERIES_DEFAULT_LIMIT = 90
SERIES_MAX_LIMIT = 366


def definition_out(definition: MetricDefinition) -> MetricDefinitionOut:
    return MetricDefinitionOut(
        key=definition.key,
        display_name=definition.display_name,
        description=definition.description,
        unit=definition.unit,
        aggregation=definition.aggregation,
        cohort=definition.cohort,
        formula=definition.formula,
        direction=definition.direction,
        baseline_method=definition.baseline_method,
        supported_dimensions=sorted(definition.supported_dimensions),
        min_sample_size=definition.min_sample_size,
        version=definition.version,
    )


def snapshot_out(row: MetricSnapshot) -> MetricSnapshotOut:
    definition = METRIC_REGISTRY[row.metric_key]
    provenance = MetricProvenance.model_validate(row.provenance_json)
    change_pp = None
    if definition.is_rate and row.baseline_value is not None:
        change_pp = float(row.value - row.baseline_value)
    return MetricSnapshotOut(
        evidence_id=row.evidence_id,
        metric_key=row.metric_key,
        display_name=definition.display_name,
        unit=definition.unit,
        direction=definition.direction,
        window_start=row.window_start,
        window_end=row.window_end,
        baseline_start=row.baseline_start,
        baseline_end=row.baseline_end,
        dimensions=dict(row.dimensions_json),
        value=float(row.value),
        baseline_value=None if row.baseline_value is None else float(row.baseline_value),
        change_pct=None if row.change_pct is None else float(row.change_pct),
        change_pp=change_pp,
        baseline_zero=provenance.flags.baseline_zero,
        baseline_empty=provenance.flags.baseline_empty,
        sample_size=row.sample_size,
        sample_sufficient=provenance.sample.sufficient,
        provenance=provenance,
        computed_at=row.computed_at,
    )


class MetricsService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repo = MetricRepository(session)

    # --- compute ---------------------------------------------------------------------

    def compute(self, window_end: datetime | None, filters: MetricFilters) -> MetricComputeResponse:
        """Timed entry point; see ``_compute``."""
        with stage_timer("metric_computation") as stage:
            response = self._compute(window_end, filters)
            stage.update(filters=dict(response.filters), metric_count=len(response.items))
            return response

    def _compute(
        self, window_end: datetime | None, filters: MetricFilters
    ) -> MetricComputeResponse:
        """Compute all registry metrics for one analysis window and persist them idempotently.

        Raises:
            NoSourceDataError: there are no tickets at all.
            WindowOutOfRangeError: the current or baseline window lies outside the data.
            InvalidDimensionValueError: an unknown ``support_team`` key was requested.
        """
        dimensions = filters.as_dimensions()
        window = self._resolve_window(window_end)
        self._validate_dimensions(dimensions)

        buckets = fetch_bucket_aggregates(self.session, window, dimensions)
        # Every metric is computed before anything is written.
        results = [
            compute_metric(definition, window, dimensions, buckets)
            for definition in METRIC_REGISTRY.values()
        ]

        computed_at = datetime.now(UTC)
        items = [self._persist(result, computed_at) for result in results]
        self.session.commit()

        return MetricComputeResponse(
            window_start=window.current.start,
            window_end=window.current.end,
            baseline_start=window.baseline.start,
            baseline_end=window.baseline.end,
            filters=canonical_filters(dimensions),
            items=items,
        )

    def _resolve_window(self, window_end: datetime | None) -> AnalysisWindow:
        bounds = self.repo.ticket_time_bounds()
        if bounds is None:
            raise NoSourceDataError("No tickets are available to compute metrics from.")
        data_start = utc_midnight(bounds[0])
        # Midnight after the last ticket, so the final ticket falls inside [start, end).
        data_end = utc_midnight(bounds[1]) + timedelta(days=1)

        window = analysis_window(data_end if window_end is None else to_utc(window_end))
        if window.current.end > data_end or window.baseline.start < data_start:
            earliest = data_start + WINDOW_LENGTH * (BASELINE_WINDOW_COUNT + 1)
            raise WindowOutOfRangeError(
                f"window_end must be between {earliest.isoformat()} and "
                f"{data_end.isoformat()} so the current window and its "
                f"{BASELINE_WINDOW_COUNT}-day baseline lie within the available data."
            )
        return window

    def _validate_dimensions(self, dimensions: dict[Dimension, str]) -> None:
        team_key = dimensions.get(Dimension.SUPPORT_TEAM)
        if team_key is not None and not self.repo.team_key_exists(team_key):
            raise InvalidDimensionValueError(f"Unknown support_team {team_key!r}.")

    def _persist(self, result: MetricResult, computed_at: datetime) -> MetricComputeItem:
        key = result.definition.key
        if not result.is_defined:
            return MetricComputeItem(metric_key=key, status="insufficient_data", snapshot=None)

        signature = analysis_signature(result.definition, result.window, result.filters)
        status: ComputeStatus = "reused"
        row = self.repo.get_by_signature(signature)
        if row is None:
            provenance = build_provenance(result, signature, computed_at)
            inserted = self.repo.insert_if_absent(
                {
                    "evidence_id": allocate_evidence_id(self.session, EvidenceType.METRIC),
                    "metric_key": key,
                    "analysis_signature": signature,
                    "window_start": result.window.current.start,
                    "window_end": result.window.current.end,
                    "baseline_start": result.window.baseline.start,
                    "baseline_end": result.window.baseline.end,
                    "dimensions_json": canonical_filters(result.filters),
                    "value": result.current.value,
                    "baseline_value": result.baseline_value,
                    "change_pct": result.change_pct,
                    "sample_size": result.current.sample_size,
                    "provenance_json": provenance.model_dump(mode="json"),
                    "computed_at": computed_at,
                }
            )
            status = "computed" if inserted else "reused"
            row = self.repo.get_by_signature(signature)
        if row is None:  # pragma: no cover - the insert or a concurrent writer created it
            raise RuntimeError(f"Metric snapshot {signature} vanished after insert.")
        return MetricComputeItem(metric_key=key, status=status, snapshot=snapshot_out(row))

    # --- read ------------------------------------------------------------------------

    def overview(self, window_end: datetime | None) -> MetricOverviewResponse:
        """Overall (unfiltered) snapshots at the requested or latest computed window."""
        keys = list(METRIC_REGISTRY)
        resolved = to_utc(window_end) if window_end else self.repo.latest_window_end({}, keys)
        if resolved is None:
            return MetricOverviewResponse(window_end=None, items=[], missing_metric_keys=keys)

        rows = [
            row
            for row in self.repo.list_at_window(resolved, {}, keys)
            if MetricProvenance.model_validate(row.provenance_json).definition.version
            == METRIC_REGISTRY[row.metric_key].version
        ]
        present = {row.metric_key for row in rows}
        return MetricOverviewResponse(
            window_end=resolved,
            items=[snapshot_out(row) for row in rows],
            missing_metric_keys=[key for key in keys if key not in present],
        )

    def series(
        self,
        metric_key: str,
        start: datetime | None,
        end: datetime | None,
        filters: MetricFilters,
        limit: int = SERIES_DEFAULT_LIMIT,
    ) -> MetricSeriesResponse:
        """Persisted snapshots of one metric, ordered by ``window_end`` ascending.

        Raises:
            MetricNotFoundError: ``metric_key`` is not in the registry.
            InvalidWindowRangeError: ``start`` is after ``end``.
        """
        definition = get_metric_definition(metric_key)
        if definition is None:
            raise MetricNotFoundError(f"Unknown metric {metric_key!r}.")
        start_utc = to_utc(start) if start else None
        end_utc = to_utc(end) if end else None
        if start_utc and end_utc and start_utc > end_utc:
            raise InvalidWindowRangeError("start must not be after end.")

        dimensions = canonical_filters(filters.as_dimensions())
        rows = self.repo.series(
            metric_key, definition.version, dimensions, start_utc, end_utc, limit
        )
        return MetricSeriesResponse(
            definition=definition_out(definition),
            filters=dimensions,
            points=[snapshot_out(row) for row in rows],
        )
