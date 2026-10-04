"""Optional model-based citation-support judgement, reported apart from deterministic checks.

Runs only when ``EVAL_MODEL_ENABLED`` is true *and* the LLM is configured. Otherwise
the section is ``not_run`` with a reason; it is never counted as passed. Only claims
the deterministic validator accepts are judged, with just the evidence they cite.
"""

import time

from app.evals.cases import load_brief_guardrails
from app.evals.context import EvalContext
from app.integrations.llm.base import LLMError
from app.integrations.llm.openai_client import get_citation_judge_client
from app.integrations.llm.prompts import JUDGE_PROMPT_VERSION
from app.models.enums import BriefStatus, LLMOperation
from app.schemas.evaluations import (
    CaseResult,
    CitationJudgeRequest,
    EvalCategory,
    ModelBasedSection,
)
from app.services.observability.traces import LLMTraceRecorder

CATEGORY = EvalCategory.CITATION_VALIDITY
EXPECTED = "cited evidence supports the claim"


def run(ctx: EvalContext) -> ModelBasedSection:
    settings = ctx.settings
    if not settings.eval_model_enabled:
        return ModelBasedSection(
            status="not_run", reason="disabled: EVAL_MODEL_ENABLED is not true"
        )
    if not settings.llm_configured:
        return ModelBasedSection(
            status="not_run",
            reason="llm_not_configured: OPENAI_API_KEY and OPENAI_MODEL are required",
        )

    try:
        client = (ctx.judge_factory or (lambda: get_citation_judge_client(settings)))()
    except LLMError as exc:
        return ModelBasedSection(status="not_run", reason=f"{exc.code}: {exc.message}")

    fixture = load_brief_guardrails(ctx.cases_dir)
    bundle = fixture.evidence_bundle()
    items = {i.evidence_id: i for i in (*bundle.metrics, *bundle.anomalies, *bundle.contributors)}
    items.update({e.evidence_id: e for e in bundle.related_events})

    # Log-only traces: the evaluation session is always rolled back, so rows would vanish.
    traces = LLMTraceRecorder(None, settings)
    model_name: str | None = settings.openai_model
    results: list[CaseResult] = []
    for case in fixture.cases:
        if case.expected_status is not BriefStatus.VALID:
            continue
        for ordinal, claim in enumerate(case.claims):
            case_id = f"model.{case.case_id}.{ordinal}"
            title = f"Judge: {claim.text}"[:200]
            request = CitationJudgeRequest(
                claim_text=claim.text,
                cited_evidence=[items[i] for i in claim.evidence_ids if i in items],
            )
            started = time.monotonic()
            try:
                judged = client.judge_citation_support(request)
            except LLMError as exc:
                traces.failure(
                    LLMOperation.CITATION_JUDGE_EVAL,
                    exc,
                    model_name=settings.openai_model or "",
                    latency_ms=int((time.monotonic() - started) * 1000),
                    persist=False,
                )
                results.append(
                    CaseResult(
                        case_id=case_id,
                        title=title,
                        category=CATEGORY,
                        status="error",
                        expected=EXPECTED,
                        failure_reason=f"{exc.code}: {exc.message}",
                    )
                )
                continue
            traces.success(
                LLMOperation.CITATION_JUDGE_EVAL,
                model_name=judged.model_name,
                latency_ms=judged.latency_ms,
                input_tokens=judged.input_tokens,
                output_tokens=judged.output_tokens,
                persist=False,
            )
            model_name = judged.model_name
            supported = judged.output.verdict == "supported"
            results.append(
                CaseResult(
                    case_id=case_id,
                    title=title,
                    category=CATEGORY,
                    status="pass" if supported else "fail",
                    expected=EXPECTED,
                    observed=f"{judged.output.verdict}: {judged.output.rationale}",
                    failure_reason=None if supported else judged.output.rationale,
                    evidence=list(claim.evidence_ids),
                )
            )
    errored = bool(results) and all(r.status == "error" for r in results)
    return ModelBasedSection(
        status="error" if errored else "completed",
        reason="every judge call failed" if errored else None,
        model_name=model_name,
        prompt_version=JUDGE_PROMPT_VERSION,
        cases=results,
    )
