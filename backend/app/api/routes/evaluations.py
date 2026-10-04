"""Evaluation route: return the latest stored report or an explicit not_run state."""

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse

from app.core.config import Settings, get_settings
from app.evals.store import EvaluationReportInvalidError
from app.schemas.evaluations import EvaluationLatestResponse
from app.schemas.health import ErrorResponse
from app.services.evaluations.service import EvaluationReportService

router = APIRouter(prefix="/evaluations", tags=["evaluations"])

AppSettings = Annotated[Settings, Depends(get_settings)]


def get_evaluation_service(settings: AppSettings) -> EvaluationReportService:
    """Dependency seam: tests point the service at a temporary reports directory."""
    return EvaluationReportService(Path(settings.eval_reports_dir))


Service = Annotated[EvaluationReportService, Depends(get_evaluation_service)]


@router.get(
    "/latest",
    response_model=EvaluationLatestResponse,
    responses={status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse}},
    summary="Latest evaluation report, or state 'not_run' when none exists",
)
def read_latest_evaluation(service: Service) -> EvaluationLatestResponse | JSONResponse:
    try:
        return service.latest()
    except EvaluationReportInvalidError as exc:
        body = ErrorResponse(code=exc.code, message=exc.message)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content=body.model_dump()
        )
