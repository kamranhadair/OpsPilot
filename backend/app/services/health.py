"""Health-check use case.

Owns the database probe so the route stays thin.
"""

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.schemas.health import HealthResponse

DATABASE_UNAVAILABLE_CODE = "DATABASE_UNAVAILABLE"


class DatabaseUnavailableError(Exception):
    """Raised when the database connectivity probe fails."""

    code = DATABASE_UNAVAILABLE_CODE

    def __init__(self, message: str = "Database connectivity check failed.") -> None:
        super().__init__(message)
        self.message = message


def check_health(session: Session) -> HealthResponse:
    """Probe the database and return the health payload.

    Raises:
        DatabaseUnavailableError: if the database cannot be reached.
    """
    try:
        session.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        # Do not log the connection string: it may carry credentials.
        raise DatabaseUnavailableError() from exc

    settings = get_settings()
    return HealthResponse(status="ok", service=settings.service_name, database="ok")
