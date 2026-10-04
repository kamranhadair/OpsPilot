"""Typed system-endpoint failures with stable machine-readable codes."""


class SystemEndpointError(Exception):
    code: str = "SYSTEM_ERROR"
    http_status: int = 500

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class SystemEndpointsDisabledError(SystemEndpointError):
    code = "SYSTEM_ENDPOINTS_DISABLED"
    http_status = 404


class InvalidTraceFilterError(SystemEndpointError):
    code = "INVALID_TRACE_FILTER"
    http_status = 422
