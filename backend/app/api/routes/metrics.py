"""Metrics routes: validate, delegate to the metrics service, map failures to HTTP."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import JSONResponse
from pydantic import AwareDatetime
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.enums import CustomerTier, Product, Region, TicketCategory
from app.schemas.health import ErrorResponse
from app.schemas.metrics import (
    MetricComputeRequest,
    MetricComputeResponse,
    MetricFilters,
    MetricOverviewResponse,
    MetricSeriesResponse,
)
from app.services.metrics.errors import MetricsError
from app.services.metrics.service import SERIES_DEFAULT_LIMIT, SERIES_MAX_LIMIT, MetricsService

router = APIRouter(prefix="/metrics", tags=["metrics"])

DbSession = Annotated[Session, Depends(get_db)]

_ERRORS: dict[int | str, dict[str, object]] = {
    code: {"model": ErrorResponse}
    for code in (
        status.HTTP_404_NOT_FOUND,
        status.HTTP_409_CONFLICT,
        status.HTTP_422_UNPROCESSABLE_CONTENT,
    )
}


def _error(exc: MetricsError) -> JSONResponse:
    body = ErrorResponse(code=exc.code, message=exc.message)
    return JSONResponse(status_code=exc.http_status, content=body.model_dump())


@router.post(
    "/compute",
    response_model=MetricComputeResponse,
    responses=_ERRORS,
    summary="Compute and persist metric snapshots for one analysis window",
)
def compute_metrics(
    request: MetricComputeRequest, session: DbSession
) -> MetricComputeResponse | JSONResponse:
    try:
        return MetricsService(session).compute(request.window_end, request.filters)
    except MetricsError as exc:
        return _error(exc)


@router.get(
    "/overview",
    response_model=MetricOverviewResponse,
    responses=_ERRORS,
    summary="Latest overall snapshots for every registered metric",
)
def read_overview(
    session: DbSession, window_end: Annotated[AwareDatetime | None, Query()] = None
) -> MetricOverviewResponse | JSONResponse:
    try:
        return MetricsService(session).overview(window_end)
    except MetricsError as exc:
        return _error(exc)


@router.get(
    "/{metric_key}",
    response_model=MetricSeriesResponse,
    responses=_ERRORS,
    summary="Time series of persisted snapshots for one metric",
)
def read_series(
    metric_key: str,
    session: DbSession,
    start: Annotated[AwareDatetime | None, Query(description="Min window_end.")] = None,
    end: Annotated[AwareDatetime | None, Query(description="Max window_end.")] = None,
    limit: Annotated[int, Query(ge=1, le=SERIES_MAX_LIMIT)] = SERIES_DEFAULT_LIMIT,
    category: Annotated[TicketCategory | None, Query()] = None,
    product: Annotated[Product | None, Query()] = None,
    region: Annotated[Region | None, Query()] = None,
    customer_tier: Annotated[CustomerTier | None, Query()] = None,
    support_team: Annotated[str | None, Query(min_length=1, max_length=64)] = None,
) -> MetricSeriesResponse | JSONResponse:
    filters = MetricFilters(
        category=category,
        product=product,
        region=region,
        customer_tier=customer_tier,
        support_team=support_team,
    )
    try:
        return MetricsService(session).series(metric_key, start, end, filters, limit)
    except MetricsError as exc:
        return _error(exc)
