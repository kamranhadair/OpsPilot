"""Expected, user-facing anomaly failures with stable machine-readable codes."""


class AnomalyError(Exception):
    code: str = "ANOMALY_ERROR"
    http_status: int = 400

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class AnomalyNotFoundError(AnomalyError):
    code = "ANOMALY_NOT_FOUND"
    http_status = 404


class InvalidEvidenceIdError(AnomalyError):
    code = "INVALID_EVIDENCE_ID"
    http_status = 422


class InvalidMetricKeyError(AnomalyError):
    code = "INVALID_METRIC_KEY"
    http_status = 422


class InvalidDateRangeError(AnomalyError):
    code = "INVALID_DATE_RANGE"
    http_status = 422
