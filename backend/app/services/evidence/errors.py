"""Expected, user-facing evidence-bundle failures with stable machine-readable codes."""


class EvidenceError(Exception):
    code: str = "EVIDENCE_ERROR"
    http_status: int = 400

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class EvidenceInspectionDisabledError(EvidenceError):
    code = "EVIDENCE_INSPECTION_DISABLED"
    http_status = 404
