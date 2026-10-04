"""Brief routes: delegate to the brief service, map failures to HTTP."""

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, Path, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.integrations.llm.base import BriefLLMClient, LLMError
from app.integrations.llm.openai_client import get_brief_llm_client
from app.schemas.briefs import BriefGenerateResponse, BriefOut
from app.schemas.health import ErrorResponse
from app.services.briefs.errors import BriefError
from app.services.briefs.generator import BriefService

router = APIRouter(prefix="/briefs", tags=["briefs"])

DbSession = Annotated[Session, Depends(get_db)]
AppSettings = Annotated[Settings, Depends(get_settings)]


def get_client_factory(settings: AppSettings) -> Callable[[], BriefLLMClient]:
    """Dependency seam: tests override this with a fake client."""
    return lambda: get_brief_llm_client(settings)


ClientFactory = Annotated[Callable[[], BriefLLMClient], Depends(get_client_factory)]

_ERRORS: dict[int | str, dict[str, object]] = {
    code: {"model": ErrorResponse}
    for code in (
        status.HTTP_404_NOT_FOUND,
        status.HTTP_409_CONFLICT,
        status.HTTP_429_TOO_MANY_REQUESTS,
        status.HTTP_502_BAD_GATEWAY,
        status.HTTP_503_SERVICE_UNAVAILABLE,
        status.HTTP_504_GATEWAY_TIMEOUT,
    )
}


def _error(exc: BriefError | LLMError) -> JSONResponse:
    body = ErrorResponse(code=exc.code, message=exc.message)
    return JSONResponse(status_code=exc.http_status, content=body.model_dump())


@router.post(
    "/generate",
    response_model=BriefGenerateResponse,
    status_code=status.HTTP_201_CREATED,
    responses=_ERRORS,
    summary="Generate a brief from the current Evidence Bundle and validate its claims",
)
def generate_brief(
    session: DbSession, settings: AppSettings, factory: ClientFactory
) -> BriefGenerateResponse | JSONResponse:
    try:
        return BriefService(session, settings, factory).generate()
    except (BriefError, LLMError) as exc:
        return _error(exc)


@router.get(
    "/latest",
    response_model=BriefOut,
    responses=_ERRORS,
    summary="The most recent validated brief (404 NO_VALIDATED_BRIEF when none)",
)
def read_latest_brief(session: DbSession, settings: AppSettings) -> BriefOut | JSONResponse:
    try:
        return BriefService(session, settings).latest()
    except BriefError as exc:
        return _error(exc)


@router.get("/{brief_id}", response_model=BriefOut, responses=_ERRORS, summary="One brief")
def read_brief(
    session: DbSession,
    settings: AppSettings,
    brief_id: Annotated[int, Path(gt=0)],
) -> BriefOut | JSONResponse:
    try:
        return BriefService(session, settings).get(brief_id)
    except BriefError as exc:
        return _error(exc)
