"""Request correlation: one request ID per HTTP request, echoed and logged.

A caller-supplied ``X-Request-ID`` is reused only when it is short and plain; anything
else is replaced so header content can never inject into logs. The ID is held in a
context variable that log lines and LLM traces read.
"""

import logging
import re
import time
import uuid

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.logging import log_event, request_id_var

REQUEST_ID_HEADER = "X-Request-ID"
_VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9._\-]{1,64}$")

logger = logging.getLogger("app.http")


def resolve_request_id(candidate: str | None) -> str:
    if candidate and _VALID_REQUEST_ID.fullmatch(candidate):
        return candidate
    return uuid.uuid4().hex


class RequestContextMiddleware:
    """Pure ASGI middleware so the context variable reaches sync route handlers."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = resolve_request_id(Headers(scope=scope).get(REQUEST_ID_HEADER))
        token = request_id_var.set(request_id)
        started = time.perf_counter()
        status_code = 500

        async def send_with_id(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        except Exception as exc:
            # Class name only: exception text may carry request content.
            log_event(
                logger,
                logging.ERROR,
                "http.unhandled_error",
                method=scope.get("method"),
                path=str(scope.get("path", ""))[:200],
                error_type=type(exc).__name__,
            )
            raise
        finally:
            # Path only: query strings and bodies are never logged.
            log_event(
                logger,
                logging.WARNING if status_code >= 500 else logging.INFO,
                "http.request",
                method=scope.get("method"),
                path=str(scope.get("path", ""))[:200],
                status_code=status_code,
                duration_ms=round((time.perf_counter() - started) * 1000, 2),
            )
            request_id_var.reset(token)
