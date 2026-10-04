"""Suites that need no database: metric fixtures, citation/causation and action grounding.

Meta-tests replace the production validator/policy/engine with broken versions and
assert the evaluator turns red, so a broken check can never look green.
"""

from collections.abc import Collection, Sequence
from decimal import Decimal
from typing import Any

import pytest

from app.evals.run import run_evaluation
from app.evals.suites import actions, brief_guardrails, metrics
from app.models.enums import BriefStatus
from app.schemas.actions import ActionProposalIssue, ActionProposalOutput
from app.services.actions import policy
from app.services.briefs import validator
from app.services.briefs.validator import BriefValidationResult
from tests.evals.conftest import offline_context


def by_id(results: Sequence[Any]) -> dict[str, Any]:
    return {r.case_id: r for r in results}


def test_metric_fixtures_pass_through_the_real_engine() -> None:
    results = metrics.run(offline_context())
    assert results and all(r.status == "pass" for r in results), [
        (r.case_id, r.failure_reason) for r in results if r.status != "pass"
    ]
    zero = by_id(results)["metric.volume_zero_baseline"]
    assert "change_pct=null" in (zero.observed or "")


def test_broken_metric_engine_turns_fixtures_red(monkeypatch: pytest.MonkeyPatch) -> None:
    real = metrics.compute_metric

    def off_by_one(*args: Any, **kwargs: Any) -> Any:
        result = real(*args, **kwargs)
        if result.baseline_value is None:
            return result
        return type(result)(**{**result.__dict__, "baseline_value": result.baseline_value + 1})

    monkeypatch.setattr(metrics, "compute_metric", off_by_one)
    results = metrics.run(offline_context())
    assert any(r.status == "fail" for r in results)
    failed = next(r for r in results if r.status == "fail")
    assert "baseline_value" in (failed.failure_reason or "")


def test_brief_guardrail_cases_pass_with_the_real_validator() -> None:
    results = by_id(brief_guardrails.run(offline_context()))
    assert all(r.status == "pass" for r in results.values())
    assert "EVIDENCE_NOT_IN_BUNDLE" in results["citation.fabricated_id"].evidence
    assert "EVIDENCE_UNRESOLVED" in results["citation.unresolved_id"].evidence
    assert "CAUSAL_LANGUAGE_FOR_EVENT" in results["causal.unsupported_caused_by"].evidence
    assert "CAUSAL_LANGUAGE_IN_NARRATIVE" in results["causal.narrative_due_to"].evidence
    assert results["causal.grounded_correlation"].evidence == []


def test_validator_that_accepts_everything_fails_citation_and_causal_cases(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def accept_all(**kwargs: Any) -> BriefValidationResult:
        return BriefValidationResult(status=BriefStatus.VALID, claims=[])

    monkeypatch.setattr(validator, "validate_brief", accept_all)
    results = by_id(brief_guardrails.run(offline_context()))
    for case_id in (
        "citation.fabricated_id",
        "citation.unresolved_id",
        "causal.unsupported_caused_by",
        "causal.narrative_due_to",
    ):
        assert results[case_id].status == "fail", case_id
    assert results["causal.grounded_correlation"].status == "pass"


def test_validator_that_rejects_everything_fails_the_correlation_control(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def reject_all(**kwargs: Any) -> BriefValidationResult:
        return BriefValidationResult(status=BriefStatus.INVALID, claims=[])

    monkeypatch.setattr(validator, "validate_brief", reject_all)
    results = by_id(brief_guardrails.run(offline_context()))
    assert results["causal.grounded_correlation"].status == "fail"
    assert results["citation.grounded_ids"].status == "fail"
    # Rejected, but for no recorded reason: expected issue codes are missing.
    assert results["citation.fabricated_id"].status == "fail"


def test_action_grounding_cases_pass_with_the_real_policy() -> None:
    results = by_id(actions.run(offline_context()))
    assert all(r.status == "pass" for r in results.values())
    assert "EVIDENCE_NOT_IN_BRIEF" in results["action.ungrounded_evidence"].evidence


def test_policy_that_accepts_everything_fails_ungrounded_cases(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def accept_all(
        output: ActionProposalOutput,
        *,
        allowed_ids: Collection[str],
        persisted_ids: Collection[str],
    ) -> list[ActionProposalIssue]:
        return []

    monkeypatch.setattr(policy, "validate_proposal", accept_all)
    results = by_id(actions.run(offline_context()))
    assert results["action.ungrounded_evidence"].status == "fail"
    assert results["action.no_anomaly_evidence"].status == "fail"
    assert results["action.grounded_control"].status == "pass"


def test_crashing_check_is_an_error_not_a_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(**kwargs: Any) -> BriefValidationResult:
        raise RuntimeError("validator exploded")

    monkeypatch.setattr(validator, "validate_brief", boom)
    results = brief_guardrails.run(offline_context())
    assert {r.status for r in results} == {"error"}
    assert "validator exploded" in (results[0].failure_reason or "")


def test_whole_suite_crash_is_recorded_and_other_suites_still_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def broken_loader(directory: object = None) -> Any:
        raise ValueError("case file unreadable")

    monkeypatch.setattr(actions, "load_action_guardrails", broken_loader)
    report = run_evaluation(offline_context(), "ai")
    suite_error = next(c for c in report.cases if c.case_id == "suite.actions")
    assert suite_error.status == "error" and "case file unreadable" in (
        suite_error.failure_reason or ""
    )
    assert any(c.case_id == "citation.fabricated_id" and c.status == "pass" for c in report.cases)
    assert report.overall_status == "fail" and report.partial_failure


def test_exact_decimal_comparison_is_used() -> None:
    assert metrics._equal(Decimal("10"), Decimal("10.000000"))
    assert not metrics._equal(None, Decimal(0))
    assert metrics._equal(None, None)
