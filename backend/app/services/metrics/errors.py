"""Expected, user-facing metrics failures with stable machine-readable codes."""


class MetricsError(Exception):
    code: str = "METRICS_ERROR"
    http_status: int = 400

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class MetricNotFoundError(MetricsError):
    code = "METRIC_NOT_FOUND"
    http_status = 404


class InvalidDimensionValueError(MetricsError):
    code = "INVALID_DIMENSION_VALUE"
    http_status = 422


class InvalidWindowRangeError(MetricsError):
    code = "INVALID_WINDOW_RANGE"
    http_status = 422


class WindowOutOfRangeError(MetricsError):
    code = "WINDOW_OUT_OF_RANGE"
    http_status = 422


class NoSourceDataError(MetricsError):
    code = "NO_SOURCE_DATA"
    http_status = 409
