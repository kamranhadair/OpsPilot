"""The one place model-call traces are recorded (Spec 14).

Every model operation reports its call here. The recorder estimates cost only from
configured prices, masks and truncates error text, attaches the current request ID,
persists the row inside a SAVEPOINT and always emits an ``llm.call`` log line. A trace
that cannot be stored is logged and dropped: observability never fails the request.

Only metadata is recorded. Prompts, model output and evidence payloads never are.
"""

import logging
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.logging import log_event, redact_text, request_id_var
from app.integrations.llm.base import LLMError
from app.models.enums import LLMOperation, TraceStatus
from app.models.observability import LLMTrace

logger = logging.getLogger(__name__)

ERROR_MESSAGE_MAX = 1000
_PER_MILLION = Decimal(1_000_000)
_COST_QUANTUM = Decimal("0.000001")


def estimate_cost_usd(
    settings: Settings, input_tokens: int | None, output_tokens: int | None
) -> Decimal | None:
    """Configured-price estimate, or ``None`` when a price or a token count is unknown."""
    input_rate = settings.openai_input_cost_per_1m
    output_rate = settings.openai_output_cost_per_1m
    if input_rate is None or output_rate is None:
        return None
    if input_tokens is None or output_tokens is None:
        return None
    cost = (Decimal(input_tokens) * input_rate + Decimal(output_tokens) * output_rate) / (
        _PER_MILLION
    )
    return cost.quantize(_COST_QUANTUM, rounding=ROUND_HALF_UP)


def safe_error_message(message: str) -> str:
    return redact_text(message)[:ERROR_MESSAGE_MAX]


class LLMTraceRecorder:
    def __init__(self, session: Session | None, settings: Settings) -> None:
        self.session = session
        self.settings = settings

    def success(
        self,
        operation: LLMOperation,
        *,
        model_name: str,
        latency_ms: int,
        input_tokens: int | None,
        output_tokens: int | None,
        brief_id: int | None = None,
        action_id: int | None = None,
        persist: bool = True,
    ) -> LLMTrace | None:
        return self._record(
            LLMTrace(
                operation=operation.value,
                model_name=model_name,
                latency_ms=max(0, latency_ms),
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                estimated_cost_usd=estimate_cost_usd(self.settings, input_tokens, output_tokens),
                status=TraceStatus.SUCCESS,
                brief_id=brief_id,
                action_id=action_id,
                request_id=request_id_var.get(),
            ),
            persist=persist,
        )

    def failure(
        self,
        operation: LLMOperation,
        error: LLMError,
        *,
        model_name: str,
        latency_ms: int,
        brief_id: int | None = None,
        action_id: int | None = None,
        persist: bool = True,
    ) -> LLMTrace | None:
        """A failed call. ``latency_ms`` is the caller's measurement, used when the client
        did not attach its own. Providers return no usage on failure, so tokens are null."""
        return self._record(
            LLMTrace(
                operation=operation.value,
                model_name=model_name,
                latency_ms=max(0, error.latency_ms if error.latency_ms is not None else latency_ms),
                status=TraceStatus.ERROR,
                error_code=error.code,
                error_message=safe_error_message(error.message),
                brief_id=brief_id,
                action_id=action_id,
                request_id=request_id_var.get(),
            ),
            persist=persist,
        )

    def link_action(self, trace: LLMTrace | None, action_id: int) -> None:
        """Attach the action created from a traced proposal. Best effort, like ``_record``."""
        if trace is None or self.session is None:
            return
        try:
            with self.session.begin_nested():
                trace.action_id = action_id
        except SQLAlchemyError as exc:
            log_event(
                logger,
                logging.WARNING,
                "llm_trace.link_failed",
                trace_id=trace.id,
                action_id=action_id,
                error_type=type(exc).__name__,
            )

    def _record(self, trace: LLMTrace, *, persist: bool) -> LLMTrace | None:
        stored: LLMTrace | None = None
        if persist and self.session is not None:
            try:
                with self.session.begin_nested():
                    self.session.add(trace)
                    self.session.flush()
                stored = trace
            except SQLAlchemyError as exc:
                if trace in self.session:
                    self.session.expunge(trace)
                log_event(
                    logger,
                    logging.ERROR,
                    "llm_trace.persist_failed",
                    operation=trace.operation,
                    error_type=type(exc).__name__,
                )
        log_event(
            logger,
            logging.INFO if trace.status is TraceStatus.SUCCESS else logging.WARNING,
            "llm.call",
            trace_id=stored.id if stored is not None else None,
            persisted=stored is not None,
            operation=trace.operation,
            model_name=trace.model_name,
            outcome=trace.status.value,
            latency_ms=trace.latency_ms,
            input_tokens=trace.input_tokens,
            output_tokens=trace.output_tokens,
            estimated_cost_usd=(
                str(trace.estimated_cost_usd) if trace.estimated_cost_usd is not None else None
            ),
            error_code=trace.error_code,
            brief_id=trace.brief_id,
            action_id=trace.action_id,
        )
        return stored
