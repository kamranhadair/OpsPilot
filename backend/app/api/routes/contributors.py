"""Contributor routes: validate, delegate to the contributor service, map failures to HTTP."""

from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.contributors import ContributorAnalysisResponse
from app.schemas.health import ErrorResponse
from app.services.anomalies.errors import AnomalyError
from app.services.contributors.errors import ContributorError
from app.services.contributors.service import ContributorService

router = APIRouter(prefix="/anomalies", tags=["contributors"])

DbSession = Annotated[Session, Depends(get_db)]

_ERRORS: dict[int | str, dict[str, object]] = {
    code: {"model": ErrorResponse}
    for code in (
        status.HTTP_404_NOT_FOUND,
        status.HTTP_409_CONFLICT,
        status.HTTP_422_UNPROCESSABLE_CONTENT,
    )
}


def _error(exc: AnomalyError | ContributorError) -> JSONResponse:
    body = ErrorResponse(code=exc.code, message=exc.message)
    return JSONResponse(status_code=exc.http_status, content=body.model_dump())


@router.post(
    "/{evidence_id}/contributors/compute",
    response_model=ContributorAnalysisResponse,
    responses=_ERRORS,
    summary="Compute and persist ranked contributor segments for an anomaly",
)
def compute_contributors(
    evidence_id: str, session: DbSession
) -> ContributorAnalysisResponse | JSONResponse:
    try:
        return ContributorService(session).compute(evidence_id)
    except (AnomalyError, ContributorError) as exc:
        return _error(exc)


@router.get(
    "/{evidence_id}/contributors",
    response_model=ContributorAnalysisResponse,
    responses=_ERRORS,
    summary="Ranked contributor groups with provenance for an anomaly",
)
def read_contributors(
    evidence_id: str, session: DbSession
) -> ContributorAnalysisResponse | JSONResponse:
    try:
        return ContributorService(session).get(evidence_id)
    except (AnomalyError, ContributorError) as exc:
        return _error(exc)
