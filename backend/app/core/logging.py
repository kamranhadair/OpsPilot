"""Structured application logging on the standard library, with secret redaction.

Log lines are JSON by default (``LOG_FORMAT=text`` for local reading). Every line carries
the current request ID when there is one. Redaction runs in the formatter, so it covers
the message, every structured field and any formatted traceback.

Callers log *events* with identifiers, counts and sizes in ``extra``; never prompts,
model output, evidence payloads or ticket bodies.
"""

import contextlib
import json
import logging
import re
import sys
from collections.abc import Mapping
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

from app.core.config import Settings

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)

REDACTED = "[REDACTED]"

# Field names whose values are always secret. ``input_tokens`` and friends are counts, so
# only an exact ``token`` (or ``*_token`` credential names) matches, not ``*_tokens``.
_SENSITIVE_KEY = re.compile(
    r"(api[_-]?key|authorization|secret|password|passwd|credential|cookie"
    r"|^token$|_token$|^bearer$)",
    re.IGNORECASE,
)

# Secret-shaped values, wherever they appear inside a string.
_VALUE_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"sk-[A-Za-z0-9_\-]{6,}"), f"sk-{REDACTED}"),
    (re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-~+/=]+"), f"Bearer {REDACTED}"),
    # Credentials embedded in a connection URL: scheme://user:password@host
    (re.compile(r"(\b[a-z][a-z0-9+.\-]*://[^:/\s@]+:)[^@\s]+@", re.IGNORECASE), rf"\1{REDACTED}@"),
    (
        re.compile(r"(?i)\b(api[_-]?key|password|secret|authorization)(\s*[=:]\s*)[^\s,;&\"']+"),
        rf"\1\2{REDACTED}",
    ),
)

# Attributes every ``LogRecord`` has; anything else on a record came from ``extra``.
_RECORD_ATTRS = frozenset(vars(logging.makeLogRecord({}))) | {"message", "asctime", "taskName"}

_HANDLER_MARKER = "_opspilot_handler"


def redact_text(text: str) -> str:
    for pattern, replacement in _VALUE_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def redact(value: object) -> object:
    """Return ``value`` with secret-named fields and secret-shaped strings masked."""
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, Mapping):
        return {
            k: REDACTED if isinstance(k, str) and _SENSITIVE_KEY.search(k) else redact(v)
            for k, v in value.items()
        }
    if isinstance(value, list | tuple | set | frozenset):
        return [redact(v) for v in value]
    return value


def _extras(record: logging.LogRecord) -> dict[str, object]:
    fields = {k: v for k, v in vars(record).items() if k not in _RECORD_ATTRS}
    return redact(fields)  # type: ignore[return-value]


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, object] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": redact_text(record.getMessage()),
            "request_id": request_id_var.get(),
        }
        entry.update(_extras(record))
        if record.exc_info:
            entry["exc_type"] = record.exc_info[0].__name__ if record.exc_info[0] else None
            entry["exc"] = redact_text(self.formatException(record.exc_info))
        return json.dumps(entry, default=str, ensure_ascii=False)


class TextFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        parts = [
            datetime.fromtimestamp(record.created, UTC).strftime("%Y-%m-%dT%H:%M:%S"),
            record.levelname,
            record.name,
            redact_text(record.getMessage()),
        ]
        request_id = request_id_var.get()
        if request_id:
            parts.append(f"request_id={request_id}")
        parts.extend(f"{k}={v}" for k, v in _extras(record).items())
        line = " ".join(parts)
        if record.exc_info:
            line += "\n" + redact_text(self.formatException(record.exc_info))
        return line


def configure_logging(settings: Settings) -> None:
    """Install one stdout handler on the root logger. Idempotent; leaves other handlers."""
    root = logging.getLogger()
    for handler in list(root.handlers):
        if getattr(handler, _HANDLER_MARKER, False):
            root.removeHandler(handler)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter() if settings.log_format == "json" else TextFormatter())
    setattr(handler, _HANDLER_MARKER, True)
    root.addHandler(handler)
    root.setLevel(settings.log_level.upper())


def log_event(logger: logging.Logger, level: int, event: str, **fields: Any) -> None:
    """Emit one structured event. Observability must never break the caller's path."""
    with contextlib.suppress(Exception):  # a logging fault is swallowed by design
        logger.log(level, event, extra=fields)
