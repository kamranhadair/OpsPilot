"""Serve the latest evaluation report; running evaluations stays a CLI operation."""

from pathlib import Path

from app.evals.store import read_latest
from app.schemas.evaluations import EvaluationLatestResponse

NOT_RUN_MESSAGE = "No evaluation report yet. Run `python -m app.evals.run --suite all`."


class EvaluationReportService:
    def __init__(self, reports_dir: Path) -> None:
        self.reports_dir = reports_dir

    def latest(self) -> EvaluationLatestResponse:
        """The latest report, or an explicit ``not_run`` state.

        Raises:
            EvaluationReportInvalidError: the stored report is unreadable or corrupt.
        """
        report = read_latest(self.reports_dir)
        if report is None:
            return EvaluationLatestResponse(state="not_run", report=None, message=NOT_RUN_MESSAGE)
        return EvaluationLatestResponse(state="available", report=report)
