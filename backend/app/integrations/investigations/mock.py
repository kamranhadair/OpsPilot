"""Mock investigation adapter: deterministic reference, no external side effects."""

from collections.abc import Mapping

from app.core.config import Settings
from app.integrations.investigations.base import (
    InvestigationAdapter,
    InvestigationRequest,
    InvestigationResult,
)
from app.models.enums import ActionType


class MockInvestigationAdapter:
    """Returns ``INV-<action id, 4 digits>``; the same action always gets the same reference."""

    adapter_key = "mock_investigation"

    def create_investigation(self, request: InvestigationRequest) -> InvestigationResult:
        return InvestigationResult(
            external_ref=f"INV-{request.action_id:04d}",
            response={"mock": True, "message": "Mock investigation recorded; no external system."},
        )


def get_investigation_adapters(settings: Settings) -> Mapping[ActionType, InvestigationAdapter]:
    """The adapter per action type. The mock is demo-only, so elsewhere execution fails closed."""
    if not settings.is_demo_environment:
        return {}
    return {ActionType.OPEN_INVESTIGATION: MockInvestigationAdapter()}
