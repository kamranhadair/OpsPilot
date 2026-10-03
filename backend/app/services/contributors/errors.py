"""Expected, user-facing contributor failures with stable machine-readable codes."""


class ContributorError(Exception):
    code: str = "CONTRIBUTOR_ERROR"
    http_status: int = 400

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class SegmentationNotSupportedError(ContributorError):
    code = "SEGMENTATION_NOT_SUPPORTED"
    http_status = 422


class ContributorsNotComputedError(ContributorError):
    code = "CONTRIBUTORS_NOT_COMPUTED"
    http_status = 404


class WindowMismatchError(ContributorError):
    code = "CONTRIBUTOR_WINDOW_MISMATCH"
    http_status = 409
