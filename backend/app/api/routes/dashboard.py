"""Dashboard routes: delegate to the dashboard service, map failures to HTTP."""

from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.dashboard import DashboardOverviewResponse
from app.schemas.health import ErrorResponse
from app.services.anomalies.errors import AnomalyError
from app.services.dashboard.service import DashboardService
from app.services.metrics.errors import MetricsError

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

DbSession = Annotated[Session, Depends(get_db)]

_ERRORS: dict[int | str, dict[str, object]] = {
    status.HTTP_422_UNPROCESSABLE_CONTENT: {"model": ErrorResponse},
}


@router.get(
    "/overview",
    response_model=DashboardOverviewResponse,
    responses=_ERRORS,
    summary="Latest metric cards, short trends and active anomalies in one response",
)
def read_overview(session: DbSession) -> DashboardOverviewResponse | JSONResponse:
    try:
        return DashboardService(session).overview()
    except (AnomalyError, MetricsError) as exc:
        body = ErrorResponse(code=exc.code, message=exc.message)
        return JSONResponse(status_code=exc.http_status, content=body.model_dump())
