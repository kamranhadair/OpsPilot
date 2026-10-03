"""Application configuration.

All values come from the environment (or the repository-root ``.env`` file).
No secret is ever hard-coded here.
"""

from functools import lru_cache
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """Typed application settings."""

    model_config = SettingsConfigDict(
        # The backend normally runs from ``backend/``, so the repository-root
        # ``.env`` is one level up. A local ``backend/.env`` also works.
        env_file=("../.env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    service_name: str = "opspilot-api"
    environment: str = "development"
    api_prefix: str = "/api"

    database_url: str = "postgresql+psycopg://opspilot:opspilot_local_dev@localhost:5432/opspilot"

    # Used only by destructive database tests; deliberately has no default so a
    # test run can never silently fall back to the application database.
    test_database_url: str | None = None

    # NoDecode: parse the raw environment string with the validator below
    # instead of letting pydantic-settings attempt a JSON decode.
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:5173"]

    # How far before the analysis window a timeline event may sit and still be bundled.
    evidence_event_lookback_hours: int = Field(default=72, ge=1, le=720)

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_cors_origins(cls, value: object) -> object:
        """Accept a comma-separated string so ``.env`` stays readable."""
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @property
    def is_demo_environment(self) -> bool:
        """Demo-only capabilities must stay disabled outside these environments."""
        return self.environment in {"development", "demo", "test"}


@lru_cache
def get_settings() -> Settings:
    """Return the cached settings instance."""
    return Settings()
