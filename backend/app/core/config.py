"""Application configuration.

All values come from the environment (or the repository-root ``.env`` file).
No secret is ever hard-coded here.
"""

from decimal import Decimal
from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator
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

    # The single AI provider boundary. Both values are required before any model call;
    # the model name is configuration, never hard-coded in domain code.
    openai_api_key: SecretStr | None = None
    openai_model: str | None = None
    openai_timeout_seconds: float = Field(default=30.0, gt=0, le=120)
    openai_max_retries: int = Field(default=2, ge=0, le=5)
    # Optional OpenAI-compatible endpoint. Unset means the provider default. The offline
    # end-to-end test points it at a local stub; it is never a silent fallback.
    openai_base_url: str | None = None

    # Spec 13 evaluation. Reports are written relative to the backend directory. The
    # optional model-based citation judge never runs unless explicitly enabled here
    # *and* the LLM is configured; otherwise it reports not_run.
    eval_reports_dir: str = "evals/reports"
    eval_model_enabled: bool = False

    # Spec 14 observability. Provider prices change, so none is hard-coded: cost is
    # estimated only when both per-million-token USD rates are configured here.
    openai_input_cost_per_1m: Decimal | None = Field(default=None, ge=0)
    openai_output_cost_per_1m: Decimal | None = Field(default=None, ge=0)
    log_level: str = "INFO"
    log_format: Literal["json", "text"] = "json"

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_cors_origins(cls, value: object) -> object:
        """Accept a comma-separated string so ``.env`` stays readable."""
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @property
    def llm_configured(self) -> bool:
        """True only when both an API key and a model name are present and non-blank."""
        key = self.openai_api_key.get_secret_value().strip() if self.openai_api_key else ""
        return bool(key and self.openai_model and self.openai_model.strip())

    @property
    def cost_estimation_configured(self) -> bool:
        """True only when both token prices are configured; otherwise cost stays null."""
        return (
            self.openai_input_cost_per_1m is not None and self.openai_output_cost_per_1m is not None
        )

    @property
    def is_demo_environment(self) -> bool:
        """Demo-only capabilities must stay disabled outside these environments."""
        return self.environment in {"development", "demo", "test"}


@lru_cache
def get_settings() -> Settings:
    """Return the cached settings instance."""
    return Settings()
