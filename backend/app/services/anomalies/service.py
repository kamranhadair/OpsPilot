"""Anomaly use cases: detect over metric snapshots, persist idempotently, read back.

Detection never recomputes metric math: it asks the metrics service for the
(idempotent) snapshots of each detection slice and applies the deterministic
rules to them. Anomalies reference their triggering snapshot, so every flagged
change traces to ``MTR-`` evidence.
"""

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models import Anomaly, MetricSnapshot
from app.models.enums import AnomalySeverity, AnomalyStatus, EvidenceType
from app.repositories.anomaly_repository import AnomalyRepository
from app.repositories.evidence import MetricSnapshotRepository
from app.schemas.anomalies import (
    AnomalyDetailOut,
    AnomalyDetectItem,
    AnomalyDetectResponse,
    AnomalyListResponse,
    AnomalyOut,
    DetectStatus,
)
from app.schemas.metrics import MetricComputeItem, MetricFilters
from app.services.anomalies.detector import (
    Detection,
    DetectionInput,
    Skip,
    SkipReason,
    ThresholdDetails,
    detect,
    explain,
)
from app.services.anomalies.errors import (
    AnomalyNotFoundError,
    InvalidDateRangeError,
    InvalidEvidenceIdError,
    InvalidMetricKeyError,
)
from app.services.anomalies.rules import ANOMALY_RULES, DETECTION_SLICES
from app.services.evidence_ids import allocate_evidence_id, parse_evidence_id
from app.services.metrics.definitions import METRIC_REGISTRY
from app.services.metrics.provenance import MetricProvenance
from app.services.metrics.service import MetricsService, snapshot_out

LIST_DEFAULT_LIMIT = 50
LIST_MAX_LIMIT = 200


def anomaly_out(anomaly: Anomaly, snapshot: MetricSnapshot) -> AnomalyOut:
    definition = METRIC_REGISTRY[snapshot.metric_key]
    threshold = ThresholdDetails.model_validate(anomaly.threshold_json)
    return AnomalyOut(
        evidence_id=anomaly.evidence_id,
        metric_evidence_id=snapshot.evidence_id,
        metric_key=snapshot.metric_key,
        display_name=definition.display_name,
        dimensions=dict(snapshot.dimensions_json),
        severity=anomaly.severity,
        status=anomaly.status,
        score=None if anomaly.score is None else float(anomaly.score),
        detector_key=anomaly.detector_key,
        window_start=snapshot.window_start,
        window_end=snapshot.window_end,
        detected_at=anomaly.detected_at,
        explanation=explain(anomaly.severity, threshold, definition.display_name),
    )


def _skipped(
    metric_key: str,
    filters: dict[str, str],
    metric_evidence_id: str | None,
    reason: SkipReason,
    detail: str | None,
) -> AnomalyDetectItem:
    return AnomalyDetectItem(
        metric_key=metric_key,
        filters=filters,
        status="skipped",
        metric_evidence_id=metric_evidence_id,
        anomaly=None,
        skip_reason=reason,
        skip_detail=detail,
    )


def _detection_input(row: MetricSnapshot) -> DetectionInput:
    """Facts for the detector, taken from the persisted snapshot and its provenance."""
    provenance = MetricProvenance.model_validate(row.provenance_json)
    definition = METRIC_REGISTRY[row.metric_key]
    return DetectionInput(
        metric_key=row.metric_key,
        direction=definition.direction,
        value=row.value,
        baseline_value=row.baseline_value,
        change_pct=row.change_pct,
        baseline_zero=provenance.flags.baseline_zero,
        current_sample_size=row.sample_size,
        baseline_sample_size=provenance.sample.baseline_sample_size,
        daily_baseline_values=[day.value for day in provenance.baseline.days],
    )


class AnomalyService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repo = AnomalyRepository(session)
        self.snapshots = MetricSnapshotRepository(session)
        self.metrics = MetricsService(session)

    # --- detect ----------------------------------------------------------------------

    def detect(self, window_end: datetime | None) -> AnomalyDetectResponse:
        """Detect anomalies for one analysis window across every detection slice.

        Raises the metrics errors (no data, window out of range) unchanged.
        """
        detected_at = datetime.now(UTC)
        items: list[AnomalyDetectItem] = []
        window_start = window_stop = None
        for slice_filters in DETECTION_SLICES:
            filters = MetricFilters.model_validate(
                {str(dimension): value for dimension, value in slice_filters.items()}
            )
            computed = self.metrics.compute(window_end, filters)
            window_start, window_stop = computed.window_start, computed.window_end
            items.extend(
                self._evaluate(item, computed.filters, detected_at) for item in computed.items
            )
        self.session.commit()

        assert window_start is not None and window_stop is not None  # slices is never empty
        counts: dict[DetectStatus, int] = {"detected": 0, "reused": 0, "skipped": 0}
        for item in items:
            counts[item.status] += 1
        return AnomalyDetectResponse(
            window_start=window_start,
            window_end=window_stop,
            items=items,
            detected_count=counts["detected"],
            reused_count=counts["reused"],
            skipped_count=counts["skipped"],
        )

    def _evaluate(
        self, item: MetricComputeItem, filters: dict[str, str], detected_at: datetime
    ) -> AnomalyDetectItem:
        key = item.metric_key
        if key not in ANOMALY_RULES:
            return _skipped(
                key, filters, None, SkipReason.NOT_CONFIGURED, f"No anomaly rule for {key!r}."
            )
        if item.snapshot is None:
            return _skipped(
                key, filters, None, SkipReason.NO_DATA, "The current window has no samples."
            )

        row = self.snapshots.get_by_evidence_id(item.snapshot.evidence_id)
        if row is None:  # pragma: no cover - the snapshot was just computed or reused
            raise RuntimeError(f"Metric snapshot {item.snapshot.evidence_id} vanished.")

        result = detect(_detection_input(row))
        if isinstance(result, Skip):
            return _skipped(key, filters, row.evidence_id, result.reason, result.detail)
        return self._persist(result, row, filters, detected_at)

    def _persist(
        self,
        detection: Detection,
        row: MetricSnapshot,
        filters: dict[str, str],
        detected_at: datetime,
    ) -> AnomalyDetectItem:
        detector_key = detection.rule.detector_key
        status: DetectStatus = "reused"
        anomaly = self.repo.get_by_snapshot_and_detector(row.id, detector_key)
        if anomaly is None:
            inserted = self.repo.insert_if_absent(
                {
                    "evidence_id": allocate_evidence_id(self.session, EvidenceType.ANOMALY),
                    "metric_snapshot_id": row.id,
                    "detector_key": detector_key,
                    "severity": detection.severity,
                    "score": detection.score,
                    "threshold_json": detection.threshold.model_dump(mode="json"),
                    "status": AnomalyStatus.ACTIVE,
                    "detected_at": detected_at,
                }
            )
            status = "detected" if inserted else "reused"
            anomaly = self.repo.get_by_snapshot_and_detector(row.id, detector_key)
        if anomaly is None:  # pragma: no cover - the insert or a concurrent writer created it
            raise RuntimeError(f"Anomaly for {row.evidence_id}/{detector_key} vanished.")
        return AnomalyDetectItem(
            metric_key=row.metric_key,
            filters=filters,
            status=status,
            metric_evidence_id=row.evidence_id,
            anomaly=anomaly_out(anomaly, row),
            skip_reason=None,
            skip_detail=None,
        )

    # --- read ------------------------------------------------------------------------

    def list(
        self,
        *,
        severity: AnomalySeverity | None = None,
        status: AnomalyStatus | None = None,
        metric_key: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = LIST_DEFAULT_LIMIT,
        offset: int = 0,
    ) -> AnomalyListResponse:
        """Anomalies filtered by severity/status/metric and the snapshot's ``window_end`` range.

        Raises:
            InvalidMetricKeyError: ``metric_key`` is not a registered metric.
            InvalidDateRangeError: ``start`` is after ``end``.
        """
        if metric_key is not None and metric_key not in METRIC_REGISTRY:
            raise InvalidMetricKeyError(f"Unknown metric {metric_key!r}.")
        if start is not None and end is not None and start > end:
            raise InvalidDateRangeError("start must not be after end.")

        rows, total = self.repo.list_with_snapshots(
            severity=severity,
            status=status,
            metric_key=metric_key,
            start=start,
            end=end,
            limit=limit,
            offset=offset,
        )
        return AnomalyListResponse(
            items=[anomaly_out(anomaly, snapshot) for anomaly, snapshot in rows],
            total=total,
            limit=limit,
            offset=offset,
        )

    def get(self, evidence_id: str) -> AnomalyDetailOut:
        """One anomaly with its snapshot, detector metadata and threshold explanation."""
        parsed = parse_evidence_id(evidence_id)
        if parsed is None or parsed[0] is not EvidenceType.ANOMALY:
            raise InvalidEvidenceIdError(f"{evidence_id!r} is not a valid ANOM- evidence ID.")
        found = self.repo.get_with_snapshot(evidence_id)
        if found is None:
            raise AnomalyNotFoundError(f"Anomaly {evidence_id} was not found.")
        anomaly, snapshot = found
        summary = anomaly_out(anomaly, snapshot)
        return AnomalyDetailOut(
            **summary.model_dump(),
            threshold=ThresholdDetails.model_validate(anomaly.threshold_json),
            snapshot=snapshot_out(snapshot),
        )
