"""Health route: validate, delegate, map failures to HTTP."""

from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.health import ErrorResponse, HealthResponse
from app.services.health import DatabaseUnavailableError, check_health

router = APIRouter(tags=["system"])

DbSession = Annotated[Session, Depends(get_db)]


@router.get(
    "/health",
    response_model=HealthResponse,
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ErrorResponse}},
    summary="Service and database health",
)
def read_health(session: DbSession) -> HealthResponse | JSONResponse:
    """Return service health, or 503 when the database is unreachable."""
    try:
        return check_health(session)
    except DatabaseUnavailableError as exc:
        body = ErrorResponse(code=exc.code, message=exc.message)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=body.model_dump(),
        )
