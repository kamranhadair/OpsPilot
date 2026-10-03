"""Evidence bundle routes: delegate to the bundle service, map failures to HTTP."""

from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.schemas.evidence import EvidenceBundle
from app.schemas.health import ErrorResponse
from app.services.evidence.errors import EvidenceError
from app.services.evidence.service import EvidenceBundleService

router = APIRouter(prefix="/evidence-bundles", tags=["evidence-bundles"])

DbSession = Annotated[Session, Depends(get_db)]
AppSettings = Annotated[Settings, Depends(get_settings)]

_ERRORS: dict[int | str, dict[str, object]] = {
    status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
}


@router.get(
    "/latest",
    response_model=EvidenceBundle,
    responses=_ERRORS,
    summary="The current Evidence Bundle exactly as the brief model would receive it (demo only)",
)
def read_latest_bundle(session: DbSession, settings: AppSettings) -> EvidenceBundle | JSONResponse:
    try:
        return EvidenceBundleService(session, settings).latest()
    except EvidenceError as exc:
        body = ErrorResponse(code=exc.code, message=exc.message)
        return JSONResponse(status_code=exc.http_status, content=body.model_dump())
