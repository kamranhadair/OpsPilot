"""Provider-neutral LLM contract: the client protocol, its result and typed failures."""

from dataclasses import dataclass
from typing import Protocol

from app.schemas.actions import ActionProposalContext, ActionProposalOutput
from app.schemas.briefs import BriefDraftOutput
from app.schemas.evidence import EvidenceBundle


class LLMError(Exception):
    """Expected provider failure. Messages must never contain keys or headers."""

    code: str = "LLM_ERROR"
    http_status: int = 502

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class LLMNotConfiguredError(LLMError):
    code = "LLM_NOT_CONFIGURED"
    http_status = 503


class LLMTimeoutError(LLMError):
    code = "LLM_TIMEOUT"
    http_status = 504


class LLMRateLimitedError(LLMError):
    code = "LLM_RATE_LIMITED"
    http_status = 429


class LLMProviderError(LLMError):
    code = "LLM_PROVIDER_ERROR"
    http_status = 502


class LLMMalformedOutputError(LLMError):
    code = "LLM_MALFORMED_OUTPUT"
    http_status = 502


@dataclass(frozen=True)
class BriefLLMResult:
    output: BriefDraftOutput
    model_name: str
    input_tokens: int | None
    output_tokens: int | None
    latency_ms: int


class BriefLLMClient(Protocol):
    def generate_brief(self, bundle: EvidenceBundle) -> BriefLLMResult:
        """Narrate ``bundle``. Raises ``LLMError`` subclasses on failure."""
        ...


@dataclass(frozen=True)
class ActionLLMResult:
    output: ActionProposalOutput
    model_name: str
    input_tokens: int | None
    output_tokens: int | None
    latency_ms: int


class ActionLLMClient(Protocol):
    def propose_action(self, context: ActionProposalContext) -> ActionLLMResult:
        """Draft one action from a validated brief. Raises ``LLMError`` subclasses."""
        ...
