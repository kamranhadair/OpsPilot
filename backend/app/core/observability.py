"""Lightweight pipeline-stage timing written as structured log events.

Stage timings are logs, not database rows (Spec 14). Callers add identifiers, counts and
sizes to the yielded dict; never payload content.
"""

import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager

from app.core.logging import log_event

logger = logging.getLogger("app.pipeline")

STAGE_EVENT = "pipeline.stage"


@contextmanager
def stage_timer(stage: str, **context: object) -> Iterator[dict[str, object]]:
    """Time one pipeline stage and log ``pipeline.stage`` with ``status`` ok or error.

    The exception is always re-raised; only its class name and stable ``code`` (when the
    application error has one) are logged, never its message.
    """
    fields: dict[str, object] = dict(context)
    started = time.perf_counter()
    try:
        yield fields
    except Exception as exc:
        code = getattr(exc, "code", None)
        log_event(
            logger,
            logging.WARNING,
            STAGE_EVENT,
            stage=stage,
            status="error",
            duration_ms=_elapsed_ms(started),
            error_type=type(exc).__name__,
            error_code=code if isinstance(code, str) else None,
            **fields,
        )
        raise
    log_event(
        logger,
        logging.INFO,
        STAGE_EVENT,
        stage=stage,
        status="ok",
        duration_ms=_elapsed_ms(started),
        **fields,
    )


def _elapsed_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 2)
