"""System routes (internal/demo): validate, delegate, map failures to typed errors."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.models.enums import TraceStatus
from app.schemas.health import ErrorResponse
from app.schemas.system import (
    LLMTraceListOut,
    SummaryPeriod,
    SystemHealthErrorResponse,
    SystemHealthResponse,
    SystemSummaryOut,
)
from app.services.observability.errors import SystemEndpointError
from app.services.observability.system import SystemService

router = APIRouter(prefix="/system", tags=["system"])

DbSession = Annotated[Session, Depends(get_db)]
AppSettings = Annotated[Settings, Depends(get_settings)]

TRACE_DEFAULT_LIMIT = 25
TRACE_MAX_LIMIT = 100

_ERRORS: dict[int | str, dict[str, object]] = {
    status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
}


def _error(exc: SystemEndpointError) -> JSONResponse:
    body = ErrorResponse(code=exc.code, message=exc.message)
    return JSONResponse(status_code=exc.http_status, content=body.model_dump())


@router.get(
    "/health",
    response_model=SystemHealthResponse,
    responses={
        **_ERRORS,
        status.HTTP_503_SERVICE_UNAVAILABLE: {"model": SystemHealthErrorResponse},
    },
    summary="Detailed database and configuration readiness (demo only; never echoes secrets)",
)
def read_system_health(
    session: DbSession, settings: AppSettings
) -> SystemHealthResponse | JSONResponse:
    try:
        health = SystemService(session, settings).health()
    except SystemEndpointError as exc:
        return _error(exc)
    if health.status == "error":
        body = SystemHealthErrorResponse(
            code="DATABASE_UNAVAILABLE",
            message="Database connectivity check failed.",
            health=health,
        )
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content=body.model_dump(mode="json")
        )
    return health


@router.get(
    "/llm-traces",
    response_model=LLMTraceListOut,
    responses={**_ERRORS, status.HTTP_422_UNPROCESSABLE_CONTENT: {"model": ErrorResponse}},
    summary="Paginated safe LLM call trace metadata, newest first (demo only)",
)
def list_llm_traces(
    session: DbSession,
    settings: AppSettings,
    operation: Annotated[str | None, Query(min_length=1, max_length=100)] = None,
    trace_status: Annotated[TraceStatus | None, Query(alias="status")] = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=TRACE_MAX_LIMIT)] = TRACE_DEFAULT_LIMIT,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> LLMTraceListOut | JSONResponse:
    try:
        return SystemService(session, settings).list_traces(
            operation=operation,
            status=trace_status,
            since=since,
            until=until,
            limit=limit,
            offset=offset,
        )
    except SystemEndpointError as exc:
        return _error(exc)


@router.get(
    "/summary",
    response_model=SystemSummaryOut,
    responses=_ERRORS,
    summary="Aggregated LLM call and execution outcomes for a period (demo only)",
)
def read_system_summary(
    session: DbSession,
    settings: AppSettings,
    period: SummaryPeriod = "7d",
) -> SystemSummaryOut | JSONResponse:
    try:
        return SystemService(session, settings).summary(period)
    except SystemEndpointError as exc:
        return _error(exc)
