"""Helpers that turn one case check into a ``CaseResult`` without ever hiding errors."""

import logging
from collections.abc import Callable

from app.schemas.evaluations import CaseResult, CaseTally, EvalCategory

logger = logging.getLogger(__name__)


def guarded(
    case_id: str,
    title: str,
    category: EvalCategory,
    expected: str,
    check: Callable[[], CaseResult],
) -> CaseResult:
    """Run ``check``; an unexpected exception becomes an ``error`` result, never a pass."""
    try:
        return check()
    except Exception as exc:  # noqa: BLE001 - the evaluator must report, not crash
        logger.warning("Evaluation case %s errored: %s", case_id, type(exc).__name__)
        return CaseResult(
            case_id=case_id,
            title=title,
            category=category,
            status="error",
            expected=expected,
            failure_reason=f"{type(exc).__name__}: {exc}"[:500],
        )


def not_run(
    case_id: str, title: str, category: EvalCategory, expected: str, reason: str
) -> CaseResult:
    return CaseResult(
        case_id=case_id,
        title=title,
        category=category,
        status="not_run",
        expected=expected,
        failure_reason=reason,
    )


def verdict(
    case_id: str,
    title: str,
    category: EvalCategory,
    *,
    passed: bool,
    expected: str,
    observed: str,
    failure_reason: str | None = None,
    evidence: list[str] | None = None,
    tally: CaseTally | None = None,
) -> CaseResult:
    return CaseResult(
        case_id=case_id,
        title=title,
        category=category,
        status="pass" if passed else "fail",
        expected=expected,
        observed=observed,
        failure_reason=None if passed else (failure_reason or f"Expected {expected}."),
        evidence=evidence or [],
        tally=tally,
    )
