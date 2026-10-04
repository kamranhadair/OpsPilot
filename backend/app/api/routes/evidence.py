"""Evidence resolver route: delegate to the resolver, map failures to HTTP."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.evidence import EvidenceDetailOut
from app.schemas.health import ErrorResponse
from app.services.evidence.errors import EvidenceError
from app.services.evidence.resolver import EvidenceResolver

router = APIRouter(prefix="/evidence", tags=["evidence"])

DbSession = Annotated[Session, Depends(get_db)]

_ERRORS: dict[int | str, dict[str, object]] = {
    status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
    status.HTTP_422_UNPROCESSABLE_CONTENT: {"model": ErrorResponse},
}


@router.get(
    "/{evidence_id}",
    response_model=EvidenceDetailOut,
    responses=_ERRORS,
    summary="Resolve an MTR/ANOM/SEG/EVT evidence ID to its values and provenance",
)
def read_evidence(
    session: DbSession, evidence_id: Annotated[str, Path(max_length=32)]
) -> EvidenceDetailOut | JSONResponse:
    try:
        return EvidenceResolver(session).resolve(evidence_id)
    except EvidenceError as exc:
        body = ErrorResponse(code=exc.code, message=exc.message)
        return JSONResponse(status_code=exc.http_status, content=body.model_dump())
