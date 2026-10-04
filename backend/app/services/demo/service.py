"""Demo API service: environment guard, status, and the analysis trigger (Spec 15)."""

from collections.abc import Callable

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.integrations.llm.base import BriefLLMClient
from app.repositories.demo_data import DemoDataRepository
from app.schemas.analysis import AnalysisRunResponse, DemoStatusResponse
from app.services.analysis.orchestrator import AnalysisOrchestrator
from app.services.demo_data.config import DEFAULT_CONFIG
from app.services.metrics.service import MetricsService


class DemoError(Exception):
    code: str = "DEMO_ERROR"
    http_status: int = 400

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class DemoDisabledError(DemoError):
    """404 rather than 403 so production does not advertise the capability."""

    code = "DEMO_DISABLED"
    http_status = 404


class DemoService:
    def __init__(
        self,
        session: Session,
        settings: Settings,
        brief_client_factory: Callable[[], BriefLLMClient] | None = None,
    ) -> None:
        self.session = session
        self.settings = settings
        self.brief_client_factory = brief_client_factory

    def status(self) -> DemoStatusResponse:
        """Raises DemoDisabledError outside demo environments."""
        self._require_enabled()
        repo = DemoDataRepository(self.session)
        seeded = repo.count_tickets(DEFAULT_CONFIG.ticket_ref_prefix) > 0 and bool(
            repo.seed_incidents(DEFAULT_CONFIG.seed_key)
        )
        return DemoStatusResponse(
            enabled=True,
            dataset_seeded=seeded,
            analysis_window_end=MetricsService(self.session).overview(None).window_end,
            llm_configured=self.settings.llm_configured,
        )

    def run_analysis(self) -> AnalysisRunResponse:
        """Raises DemoDisabledError outside demo environments, NoSourceDataError when unseeded."""
        self._require_enabled()
        return AnalysisOrchestrator(self.session, self.settings, self.brief_client_factory).run()

    def _require_enabled(self) -> None:
        if not self.settings.is_demo_environment:
            raise DemoDisabledError("Demo endpoints are disabled outside demo environments.")
