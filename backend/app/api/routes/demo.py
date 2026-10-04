"""Demo routes (demo/development/test only): delegate to the demo service, map failures.

There is deliberately no reset endpoint: resetting is a CLI-only operation
(``python -m app.scripts.demo reset``).
"""

from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.api.routes.briefs import ClientFactory
from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.schemas.analysis import AnalysisRunResponse, DemoStatusResponse
from app.schemas.health import ErrorResponse
from app.services.demo.service import DemoError, DemoService
from app.services.metrics.errors import MetricsError

router = APIRouter(prefix="/demo", tags=["demo"])

DbSession = Annotated[Session, Depends(get_db)]
AppSettings = Annotated[Settings, Depends(get_settings)]

_ERRORS: dict[int | str, dict[str, object]] = {
    code: {"model": ErrorResponse}
    for code in (
        status.HTTP_404_NOT_FOUND,
        status.HTTP_409_CONFLICT,
        status.HTTP_422_UNPROCESSABLE_CONTENT,
    )
}


def _error(exc: DemoError | MetricsError) -> JSONResponse:
    body = ErrorResponse(code=exc.code, message=exc.message)
    return JSONResponse(status_code=exc.http_status, content=body.model_dump())


@router.get(
    "/status",
    response_model=DemoStatusResponse,
    responses=_ERRORS,
    summary="Whether the demo is enabled, seeded and analysed (404 DEMO_DISABLED otherwise)",
)
def read_demo_status(
    session: DbSession, settings: AppSettings
) -> DemoStatusResponse | JSONResponse:
    try:
        return DemoService(session, settings).status()
    except DemoError as exc:
        return _error(exc)


@router.post(
    "/analysis/run",
    response_model=AnalysisRunResponse,
    responses=_ERRORS,
    summary="Run metrics -> anomalies -> contributors -> evidence -> brief for the final window",
)
def run_demo_analysis(
    session: DbSession, settings: AppSettings, factory: ClientFactory
) -> AnalysisRunResponse | JSONResponse:
    try:
        return DemoService(session, settings, factory).run_analysis()
    except (DemoError, MetricsError) as exc:
        return _error(exc)
