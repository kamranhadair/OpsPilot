"""File store for the latest evaluation report (``<reports dir>/latest.json``)."""

import os
import tempfile
from pathlib import Path

from pydantic import ValidationError

from app.schemas.evaluations import EvaluationReport

LATEST_JSON = "latest.json"
LATEST_MARKDOWN = "latest.md"


class EvaluationReportInvalidError(Exception):
    code = "EVAL_REPORT_INVALID"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def write_report(
    directory: Path, report: EvaluationReport, markdown: str | None = None
) -> list[Path]:
    """Write ``latest.json`` (and ``latest.md``) atomically; returns the written paths."""
    written = [directory / LATEST_JSON]
    _atomic_write(written[0], report.model_dump_json(indent=2) + "\n")
    if markdown is not None:
        written.append(directory / LATEST_MARKDOWN)
        _atomic_write(written[1], markdown)
    return written


def read_latest(directory: Path) -> EvaluationReport | None:
    """The latest report, ``None`` when none exists. Raises when the file is unreadable."""
    path = directory / LATEST_JSON
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise EvaluationReportInvalidError(
            f"The evaluation report could not be read ({type(exc).__name__})."
        ) from exc
    try:
        return EvaluationReport.model_validate_json(raw)
    except ValidationError as exc:
        raise EvaluationReportInvalidError(
            "The stored evaluation report is corrupt or uses an unsupported schema; "
            "re-run `python -m app.evals.run`."
        ) from exc
