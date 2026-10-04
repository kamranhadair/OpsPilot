"""OpenAI implementation of the LLM client boundary. The only module that imports ``openai``.

One client serves every model operation (brief generation, action proposal and the
optional evaluation citation judge); each operation has its own prompt and
structured-output schema.
"""

import logging
import time
from dataclasses import dataclass

import openai
from pydantic import BaseModel, ValidationError

from app.core.config import Settings
from app.integrations.llm.base import (
    ActionLLMResult,
    BriefLLMResult,
    CitationJudgeResult,
    LLMMalformedOutputError,
    LLMNotConfiguredError,
    LLMProviderError,
    LLMRateLimitedError,
    LLMTimeoutError,
)
from app.integrations.llm.prompts import (
    ACTION_SYSTEM_PROMPT,
    BRIEF_SYSTEM_PROMPT,
    JUDGE_SYSTEM_PROMPT,
    build_action_user_message,
    build_judge_user_message,
    build_user_message,
)
from app.schemas.actions import ActionProposalContext, ActionProposalOutput
from app.schemas.briefs import BriefDraftOutput
from app.schemas.evaluations import CitationJudgeRequest, CitationSupportJudgement
from app.schemas.evidence import EvidenceBundle

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _Parsed[OutputT: BaseModel]:
    output: OutputT
    model_name: str
    input_tokens: int | None
    output_tokens: int | None
    latency_ms: int


class OpenAILLMClient:
    def __init__(self, settings: Settings, *, http_client: object | None = None) -> None:
        if not settings.llm_configured or settings.openai_api_key is None:
            raise LLMNotConfiguredError("OPENAI_API_KEY and OPENAI_MODEL must be configured.")
        assert settings.openai_model is not None
        self._model = settings.openai_model
        extra: dict[str, object] = {} if http_client is None else {"http_client": http_client}
        if settings.openai_base_url:
            extra["base_url"] = settings.openai_base_url
        # max_retries bounds the SDK's own backoff on 429/5xx/timeouts.
        self._client = openai.OpenAI(
            api_key=settings.openai_api_key.get_secret_value(),
            timeout=settings.openai_timeout_seconds,
            max_retries=settings.openai_max_retries,
            **extra,  # type: ignore[arg-type]
        )

    def generate_brief(self, bundle: EvidenceBundle) -> BriefLLMResult:
        parsed = self._parse(BRIEF_SYSTEM_PROMPT, build_user_message(bundle), BriefDraftOutput)
        return BriefLLMResult(
            output=parsed.output,
            model_name=parsed.model_name,
            input_tokens=parsed.input_tokens,
            output_tokens=parsed.output_tokens,
            latency_ms=parsed.latency_ms,
        )

    def propose_action(self, context: ActionProposalContext) -> ActionLLMResult:
        parsed = self._parse(
            ACTION_SYSTEM_PROMPT, build_action_user_message(context), ActionProposalOutput
        )
        return ActionLLMResult(
            output=parsed.output,
            model_name=parsed.model_name,
            input_tokens=parsed.input_tokens,
            output_tokens=parsed.output_tokens,
            latency_ms=parsed.latency_ms,
        )

    def judge_citation_support(self, request: CitationJudgeRequest) -> CitationJudgeResult:
        parsed = self._parse(
            JUDGE_SYSTEM_PROMPT, build_judge_user_message(request), CitationSupportJudgement
        )
        return CitationJudgeResult(
            output=parsed.output,
            model_name=parsed.model_name,
            latency_ms=parsed.latency_ms,
            input_tokens=parsed.input_tokens,
            output_tokens=parsed.output_tokens,
        )

    def _parse[OutputT: BaseModel](
        self, system: str, user: str, text_format: type[OutputT]
    ) -> _Parsed[OutputT]:
        started = time.monotonic()
        try:
            response = self._client.responses.parse(
                model=self._model,
                input=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                text_format=text_format,
            )
        except openai.APITimeoutError as exc:
            raise LLMTimeoutError(
                "The model provider timed out.", latency_ms=_elapsed_ms(started)
            ) from exc
        except openai.RateLimitError as exc:
            raise LLMRateLimitedError(
                "The model provider rate-limited the request.", latency_ms=_elapsed_ms(started)
            ) from exc
        except ValidationError as exc:
            raise LLMMalformedOutputError(
                "The model returned output that failed validation.",
                latency_ms=_elapsed_ms(started),
            ) from exc
        except openai.APIError as exc:
            status = getattr(exc, "status_code", None)
            logger.warning("LLM provider error (%s): %s", type(exc).__name__, status)
            raise LLMProviderError(
                f"The model provider request failed ({type(exc).__name__}).",
                latency_ms=_elapsed_ms(started),
            ) from exc
        latency_ms = _elapsed_ms(started)

        parsed = response.output_parsed
        if parsed is None:
            raise LLMMalformedOutputError(
                "The model returned no structured output.", latency_ms=latency_ms
            )
        usage = response.usage
        return _Parsed(
            output=parsed,
            model_name=response.model or self._model,
            input_tokens=usage.input_tokens if usage else None,
            output_tokens=usage.output_tokens if usage else None,
            latency_ms=latency_ms,
        )


def _elapsed_ms(started: float) -> int:
    return max(0, int((time.monotonic() - started) * 1000))


# Spec 09 name, kept for existing imports.
OpenAIBriefClient = OpenAILLMClient


def get_brief_llm_client(settings: Settings) -> OpenAILLMClient:
    """Factory used by the API layer; tests substitute a fake."""
    return OpenAILLMClient(settings)


def get_action_llm_client(settings: Settings) -> OpenAILLMClient:
    """Factory used by the action API layer; tests substitute a fake."""
    return OpenAILLMClient(settings)


def get_citation_judge_client(settings: Settings) -> OpenAILLMClient:
    """Factory used by the optional model-based evaluation; tests substitute a fake."""
    return OpenAILLMClient(settings)
