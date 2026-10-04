"""Citation validity and the causal-language guardrail through the Spec 10 validator."""

from functools import partial

from app.evals.cases import BriefGuardrailCase, load_brief_guardrails
from app.evals.context import EvalContext
from app.evals.results import guarded, verdict
from app.models.enums import BriefStatus
from app.schemas.evaluations import CaseResult
from app.schemas.evidence import EvidenceBundle
from app.services.briefs import validator


def _check(case: BriefGuardrailCase, bundle: EvidenceBundle) -> CaseResult:
    assert bundle.analysis_window is not None
    persisted = bundle.allowed_evidence_ids if case.persisted_ids is None else case.persisted_ids
    # Looked up on the module so a test can substitute a broken validator.
    result = validator.validate_brief(
        headline=case.headline,
        summary=case.summary,
        claims=case.claims,
        bundle=bundle,
        persisted_ids=set(persisted),
        brief_window=bundle.analysis_window.current,
    )
    codes: list[str] = [issue.code for issue in result.all_issues]
    missing = [code for code in case.expected_codes if code not in codes]
    unexpected = case.expected_status is BriefStatus.VALID and bool(codes)
    passed = result.status is case.expected_status and not missing and not unexpected
    expected = f"brief {case.expected_status.value}" + (
        f" with {', '.join(case.expected_codes)}" if case.expected_codes else ""
    )
    observed = f"brief {result.status.value}; issues: {', '.join(codes) or 'none'}"
    reasons = []
    if result.status is not case.expected_status:
        reasons.append(f"status {result.status.value}, expected {case.expected_status.value}")
    if missing:
        reasons.append(f"missing issue codes {missing}")
    if unexpected:
        reasons.append(f"unexpected issues {codes}")
    return verdict(
        case.case_id,
        case.title,
        case.category,
        passed=passed,
        expected=expected,
        observed=observed,
        failure_reason="; ".join(reasons),
        evidence=codes,
    )


def run(ctx: EvalContext) -> list[CaseResult]:
    fixture = load_brief_guardrails(ctx.cases_dir)
    bundle = fixture.evidence_bundle()
    return [
        guarded(
            c.case_id,
            c.title,
            c.category,
            f"brief {c.expected_status.value}",
            partial(_check, c, bundle),
        )
        for c in fixture.cases
    ]
