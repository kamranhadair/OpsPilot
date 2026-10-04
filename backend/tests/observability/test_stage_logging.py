"""Pipeline stages emit structured timing/error events (Spec 14)."""

import json
import logging

import pytest
from sqlalchemy.orm import Session

from app.core.logging import JsonFormatter
from app.core.observability import STAGE_EVENT, stage_timer
from app.services.anomalies.service import AnomalyService
from app.services.evidence.assembler import EvidenceBundleAssembler
from app.services.metrics.errors import NoSourceDataError
from tests.anomalies.conftest import END
from tests.evidence.conftest import detect_billing_volume
from tests.metrics.conftest import World


def _stages(caplog: pytest.LogCaptureFixture, stage: str) -> list[logging.LogRecord]:
    return [
        r
        for r in caplog.records
        if r.getMessage() == STAGE_EVENT and r.__dict__.get("stage") == stage
    ]


class _CodedError(Exception):
    code = "SOMETHING_FAILED"


def test_stage_timer_logs_success_with_duration_and_fields(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="app.pipeline")
    with stage_timer("unit_stage", run=1) as stage:
        stage["item_count"] = 3

    (record,) = _stages(caplog, "unit_stage")
    assert record.__dict__["status"] == "ok"
    assert record.__dict__["item_count"] == 3
    assert record.__dict__["run"] == 1
    assert record.__dict__["duration_ms"] >= 0


def test_stage_timer_logs_error_class_and_code_only_and_reraises(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="app.pipeline")
    with pytest.raises(_CodedError), stage_timer("unit_stage"):
        raise _CodedError("ticket body: customer wrote something private")

    (record,) = _stages(caplog, "unit_stage")
    assert record.levelno == logging.WARNING
    assert record.__dict__["status"] == "error"
    assert record.__dict__["error_type"] == "_CodedError"
    assert record.__dict__["error_code"] == "SOMETHING_FAILED"
    assert "private" not in caplog.text


@pytest.mark.db
def test_anomaly_detection_and_metric_computation_are_timed(
    volume_world: World, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger="app.pipeline")
    detect_billing_volume(volume_world)

    (detection,) = _stages(caplog, "anomaly_detection")
    assert detection.__dict__["status"] == "ok"
    assert detection.__dict__["detected_count"] >= 1
    assert _stages(caplog, "metric_computation")
    assert _stages(caplog, "contributor_computation")


@pytest.mark.db
def test_failed_stage_is_logged_as_an_error(
    clean_db: Session, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger="app.pipeline")
    with pytest.raises(NoSourceDataError):
        AnomalyService(clean_db).detect(END)
    (record,) = _stages(caplog, "anomaly_detection")
    assert record.__dict__["status"] == "error"
    assert record.__dict__["error_type"] == "NoSourceDataError"


@pytest.mark.db
def test_evidence_assembly_logs_sizes_never_content(
    volume_world: World, caplog: pytest.LogCaptureFixture
) -> None:
    detect_billing_volume(volume_world)
    caplog.set_level(logging.INFO, logger="app.pipeline")
    bundle = EvidenceBundleAssembler(volume_world.session, event_lookback_hours=72).assemble(None)

    (record,) = _stages(caplog, "evidence_assembly")
    fields = record.__dict__
    assert fields["anomaly_count"] == len(bundle.anomalies) >= 1
    assert fields["metric_count"] == len(bundle.metrics)
    assert fields["bundle_bytes"] == len(bundle.model_dump_json().encode("utf-8"))
    line = JsonFormatter().format(record)
    # Identifiers and statements from the bundle never appear in the log line.
    for anomaly in bundle.anomalies:
        assert anomaly.evidence_id not in line
    assert len(line) < 1000
    assert json.loads(line)["stage"] == "evidence_assembly"
