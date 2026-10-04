"""Expected, user-facing brief failures with stable machine-readable codes."""


class BriefError(Exception):
    code: str = "BRIEF_ERROR"
    http_status: int = 400

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class BriefNotFoundError(BriefError):
    code = "BRIEF_NOT_FOUND"
    http_status = 404


class BriefEvidenceUnavailableError(BriefError):
    code = "EVIDENCE_BUNDLE_EMPTY"
    http_status = 409


class NoValidatedBriefError(BriefError):
    code = "NO_VALIDATED_BRIEF"
    http_status = 404
