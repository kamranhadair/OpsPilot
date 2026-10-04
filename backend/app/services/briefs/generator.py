"""Brief generation: bundle -> model -> parsed draft -> persisted brief, claims, trace
-> deterministic claim validation -> final valid/invalid state.

The model only narrates the Evidence Bundle. Nothing here computes or repairs evidence:
cited IDs are stored exactly as returned and judged by the claim validator against the
exact bundle the model received.
"""

import logging
from collections.abc import Callable

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.integrations.llm.base import BriefLLMClient, LLMError, LLMNotConfiguredError
from app.models.brief import Brief, BriefClaim
from app.models.enums import BriefStatus, ClaimValidationStatus, TraceStatus
from app.models.observability import LLMTrace
from app.repositories.brief import BriefRepository, LLMTraceRepository
from app.schemas.briefs import BriefClaimOut, BriefGenerateResponse, BriefOut, ValidationIssue
from app.services.briefs.errors import (
    BriefEvidenceUnavailableError,
    BriefNotFoundError,
    NoValidatedBriefError,
)
from app.services.briefs.validator import validate_brief
from app.services.evidence.assembler import EvidenceBundleAssembler
from app.services.evidence.resolver import EvidenceResolver

OPERATION = "brief_generation"

logger = logging.getLogger(__name__)


def _issues(raw: object) -> list[ValidationIssue]:
    return [ValidationIssue.model_validate(item) for item in raw] if isinstance(raw, list) else []


def _brief_out(brief: Brief, claims: list[BriefClaim]) -> BriefOut:
    return BriefOut(
        id=brief.id,
        analysis_window_start=brief.analysis_window_start,
        analysis_window_end=brief.analysis_window_end,
        headline=brief.headline,
        summary=brief.summary,
        status=brief.status,
        model_name=brief.model_name,
        validation_errors=_issues(brief.validation_errors_json),
        created_at=brief.created_at,
        claims=[
            BriefClaimOut(
                ordinal=c.ordinal,
                claim_type=c.claim_type,
                text=c.text,
                evidence_ids=list(c.evidence_ids_json),
                validation_status=c.validation_status,
                validation_errors=_issues(c.validation_errors_json),
            )
            for c in claims
        ],
    )


class BriefService:
    def __init__(
        self,
        session: Session,
        settings: Settings,
        client_factory: Callable[[], BriefLLMClient] | None = None,
    ) -> None:
        self.session = session
        self.settings = settings
        self.client_factory = client_factory
        self.briefs = BriefRepository(session)
        self.traces = LLMTraceRepository(session)

    def generate(self) -> BriefGenerateResponse:
        """Generate, persist and validate a brief from the current Evidence Bundle.

        The returned brief is ``valid`` or ``invalid``; validation errors are persisted.

        Raises:
            LLMNotConfiguredError: no API key/model; nothing is called or written.
            BriefEvidenceUnavailableError: no computed analysis window to narrate.
            LLMError: the provider failed; an error trace is recorded.
        """
        if not self.settings.llm_configured:
            raise LLMNotConfiguredError("OPENAI_API_KEY and OPENAI_MODEL must be configured.")

        bundle = EvidenceBundleAssembler(
            self.session, event_lookback_hours=self.settings.evidence_event_lookback_hours
        ).assemble(None)
        if bundle.analysis_window is None:
            raise BriefEvidenceUnavailableError(
                "No metrics have been computed, so there is no evidence to brief."
            )

        model_name = self.settings.openai_model or ""
        try:
            if self.client_factory is None:
                raise LLMNotConfiguredError("No LLM client is available.")
            result = self.client_factory().generate_brief(bundle)
        except LLMError as exc:
            self.traces.add(
                LLMTrace(
                    brief_id=None,
                    operation=OPERATION,
                    model_name=model_name,
                    latency_ms=0,
                    status=TraceStatus.ERROR,
                    error_code=exc.code,
                    error_message=exc.message[:1000],
                )
            )
            self.session.commit()
            raise

        window = bundle.analysis_window.current
        output = result.output
        brief = self.briefs.add(
            Brief(
                analysis_window_start=window.start,
                analysis_window_end=window.end,
                headline=output.headline,
                summary=output.summary,
                status=BriefStatus.DRAFT,
                model_name=result.model_name,
                validation_errors_json=[],
            )
        )
        claims = [
            BriefClaim(
                ordinal=ordinal,
                claim_type=claim.claim_type,
                text=claim.text,
                evidence_ids_json=list(claim.evidence_ids),
                validation_status=ClaimValidationStatus.PENDING,
                validation_errors_json=[],
            )
            for ordinal, claim in enumerate(output.claims)
        ]
        self.briefs.add_claims(brief.id, claims)

        cited = {i for claim in output.claims for i in claim.evidence_ids}
        validation = validate_brief(
            headline=output.headline,
            summary=output.summary,
            claims=output.claims,
            bundle=bundle,
            persisted_ids=EvidenceResolver(self.session).existing(cited),
            brief_window=window,
        )
        for claim, claim_result in zip(claims, validation.claims, strict=True):
            claim.validation_status = claim_result.status
            claim.validation_errors_json = [
                i.model_dump(exclude_none=True) for i in claim_result.issues
            ]
        brief.status = validation.status
        all_issues = validation.all_issues
        brief.validation_errors_json = [i.model_dump(exclude_none=True) for i in all_issues]
        self.session.flush()
        if validation.status is BriefStatus.INVALID:
            # Codes and IDs only: claim text never goes to the logs.
            logger.warning(
                "Brief %s failed validation: %s",
                brief.id,
                ", ".join(
                    f"{i.code}"
                    + (f"[claim {i.claim_ordinal}]" if i.claim_ordinal is not None else "")
                    + (f"({i.evidence_id})" if i.evidence_id else "")
                    for i in all_issues
                ),
            )

        self.traces.add(
            LLMTrace(
                brief_id=brief.id,
                operation=OPERATION,
                model_name=result.model_name,
                latency_ms=result.latency_ms,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                status=TraceStatus.SUCCESS,
            )
        )
        self.session.commit()
        return BriefGenerateResponse(
            **_brief_out(brief, claims).model_dump(), attention_items=list(output.attention_items)
        )

    def get(self, brief_id: int) -> BriefOut:
        found = self.briefs.get_with_claims(brief_id)
        if found is None:
            raise BriefNotFoundError(f"Brief {brief_id} does not exist.")
        return _brief_out(*found)

    def latest(self) -> BriefOut:
        """The newest *validated* brief; invalid and draft briefs are never returned here."""
        brief = self.briefs.latest_with_status(BriefStatus.VALID)
        if brief is None:
            raise NoValidatedBriefError("No validated brief is available.")
        return _brief_out(brief, self.briefs.claims_for(brief.id))
