"""Anomaly routes: validate, delegate to the anomaly service, map failures to HTTP."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import JSONResponse
from pydantic import AwareDatetime
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.enums import AnomalySeverity, AnomalyStatus
from app.schemas.anomalies import (
    AnomalyDetailOut,
    AnomalyDetectRequest,
    AnomalyDetectResponse,
    AnomalyListResponse,
)
from app.schemas.health import ErrorResponse
from app.services.anomalies.errors import AnomalyError
from app.services.anomalies.service import LIST_DEFAULT_LIMIT, LIST_MAX_LIMIT, AnomalyService
from app.services.metrics.errors import MetricsError

router = APIRouter(prefix="/anomalies", tags=["anomalies"])

DbSession = Annotated[Session, Depends(get_db)]

_ERRORS: dict[int | str, dict[str, object]] = {
    code: {"model": ErrorResponse}
    for code in (
        status.HTTP_404_NOT_FOUND,
        status.HTTP_409_CONFLICT,
        status.HTTP_422_UNPROCESSABLE_CONTENT,
    )
}


def _error(exc: AnomalyError | MetricsError) -> JSONResponse:
    body = ErrorResponse(code=exc.code, message=exc.message)
    return JSONResponse(status_code=exc.http_status, content=body.model_dump())


@router.post(
    "/detect",
    response_model=AnomalyDetectResponse,
    responses=_ERRORS,
    summary="Detect and persist anomalies for one analysis window",
)
def detect_anomalies(
    request: AnomalyDetectRequest, session: DbSession
) -> AnomalyDetectResponse | JSONResponse:
    try:
        return AnomalyService(session).detect(request.window_end)
    except (AnomalyError, MetricsError) as exc:
        return _error(exc)


@router.get(
    "",
    response_model=AnomalyListResponse,
    responses=_ERRORS,
    summary="List persisted anomalies",
)
def list_anomalies(
    session: DbSession,
    severity: Annotated[AnomalySeverity | None, Query()] = None,
    anomaly_status: Annotated[AnomalyStatus | None, Query(alias="status")] = None,
    metric_key: Annotated[str | None, Query(min_length=1, max_length=100)] = None,
    start: Annotated[AwareDatetime | None, Query(description="Min window_end.")] = None,
    end: Annotated[AwareDatetime | None, Query(description="Max window_end.")] = None,
    limit: Annotated[int, Query(ge=1, le=LIST_MAX_LIMIT)] = LIST_DEFAULT_LIMIT,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AnomalyListResponse | JSONResponse:
    try:
        return AnomalyService(session).list(
            severity=severity,
            status=anomaly_status,
            metric_key=metric_key,
            start=start,
            end=end,
            limit=limit,
            offset=offset,
        )
    except AnomalyError as exc:
        return _error(exc)


@router.get(
    "/{evidence_id}",
    response_model=AnomalyDetailOut,
    responses=_ERRORS,
    summary="One anomaly with its snapshot, detector metadata and threshold explanation",
)
def read_anomaly(evidence_id: str, session: DbSession) -> AnomalyDetailOut | JSONResponse:
    try:
        return AnomalyService(session).get(evidence_id)
    except AnomalyError as exc:
        return _error(exc)
