"""Action grounding through the Spec 11 proposal policy."""

from functools import partial

from app.evals.cases import ActionGuardrailCase, load_action_guardrails
from app.evals.context import EvalContext
from app.evals.results import guarded, verdict
from app.schemas.evaluations import CaseResult, EvalCategory
from app.services.actions import policy

CATEGORY = EvalCategory.ACTION_GROUNDING


def _check(case: ActionGuardrailCase, allowed: set[str], persisted: set[str]) -> CaseResult:
    # Looked up on the module so a test can substitute a broken policy.
    issues = policy.validate_proposal(case.proposal, allowed_ids=allowed, persisted_ids=persisted)
    codes: list[str] = [issue.code for issue in issues]
    rejected = bool(issues)
    missing = [code for code in case.expected_codes if code not in codes]
    expected = ("rejected" if case.expected_rejected else "accepted") + (
        f" with {', '.join(case.expected_codes)}" if case.expected_codes else ""
    )
    observed = ("rejected" if rejected else "accepted") + f"; issues: {', '.join(codes) or 'none'}"
    reasons = []
    if rejected is not case.expected_rejected:
        reasons.append(f"proposal was {'rejected' if rejected else 'accepted'}")
    if missing:
        reasons.append(f"missing issue codes {missing}")
    return verdict(
        case.case_id,
        case.title,
        CATEGORY,
        passed=not reasons,
        expected=expected,
        observed=observed,
        failure_reason="; ".join(reasons),
        evidence=codes,
    )


def run(ctx: EvalContext) -> list[CaseResult]:
    fixture = load_action_guardrails(ctx.cases_dir)
    allowed, persisted = set(fixture.brief_evidence_ids), set(fixture.persisted_ids)
    return [
        guarded(
            c.case_id,
            c.title,
            CATEGORY,
            "rejected" if c.expected_rejected else "accepted",
            partial(_check, c, allowed, persisted),
        )
        for c in fixture.cases
    ]
