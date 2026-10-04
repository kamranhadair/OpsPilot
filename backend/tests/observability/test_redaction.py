"""Secrets never reach log output (Spec 14). Pure unit tests; no database."""

import json
import logging
import sys

from app.core.logging import (
    REDACTED,
    JsonFormatter,
    TextFormatter,
    redact,
    redact_text,
    request_id_var,
)
from app.services.observability.traces import ERROR_MESSAGE_MAX, safe_error_message
from tests.observability.conftest import SECRET_KEY


def _record(msg: str, **extra: object) -> logging.LogRecord:
    record = logging.LogRecord("t", logging.INFO, __file__, 1, msg, None, None)
    for key, value in extra.items():
        setattr(record, key, value)
    return record


def test_secret_shaped_values_are_masked_inside_text() -> None:
    text = (
        f"key={SECRET_KEY} Authorization: Bearer abc.def-ghi "
        "url=postgresql+psycopg://opspilot:hunter2@db:5432/opspilot password=hunter2"
    )
    out = redact_text(text)
    assert SECRET_KEY not in out
    assert "abc.def-ghi" not in out
    assert "hunter2" not in out
    assert "opspilot@db" not in out
    assert "postgresql+psycopg://opspilot:" + REDACTED + "@db" in out


def test_secret_named_fields_are_masked_but_token_counts_are_kept() -> None:
    out = redact(
        {
            "api_key": "anything",
            "Authorization": "Bearer x",
            "openai_api_key": "y",
            "access_token": "z",
            "input_tokens": 120,
            "output_tokens": 30,
            "nested": {"password": "p", "ok": "value"},
        }
    )
    assert out == {
        "api_key": REDACTED,
        "Authorization": REDACTED,
        "openai_api_key": REDACTED,
        "access_token": REDACTED,
        "input_tokens": 120,
        "output_tokens": 30,
        "nested": {"password": REDACTED, "ok": "value"},
    }


def test_json_formatter_redacts_message_extras_and_traceback() -> None:
    try:
        raise RuntimeError(f"provider said {SECRET_KEY}")
    except RuntimeError:
        exc_info = sys.exc_info()
    record = _record(f"call failed with {SECRET_KEY}", api_key=SECRET_KEY, note=SECRET_KEY)
    record.exc_info = exc_info
    token = request_id_var.set("req-123")
    try:
        line = JsonFormatter().format(record)
    finally:
        request_id_var.reset(token)

    assert SECRET_KEY not in line
    entry = json.loads(line)
    assert entry["request_id"] == "req-123"
    assert entry["api_key"] == REDACTED
    assert entry["exc_type"] == "RuntimeError"


def test_text_formatter_redacts_too() -> None:
    line = TextFormatter().format(_record(f"oops {SECRET_KEY}", authorization="Bearer abc"))
    assert SECRET_KEY not in line
    assert "Bearer abc" not in line


def test_persisted_error_messages_are_redacted_and_bounded() -> None:
    message = safe_error_message(f"failed: {SECRET_KEY} " + "x" * 5000)
    assert SECRET_KEY not in message
    assert len(message) == ERROR_MESSAGE_MAX
