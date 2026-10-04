"""Action proposal: validated brief -> model -> deterministic policy -> pending approval.

The model only drafts. The backend decides whether the brief may be acted on, which
evidence is citable, whether the draft is grounded, and the resulting state. A
proposal ends in ``pending_approval``; nothing here approves, rejects or executes an
action, and no external system is called.
"""

import logging
import time
from collections.abc import Callable

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.integrations.llm.base import ActionLLMClient, LLMError, LLMNotConfiguredError
from app.models.action import ProposedAction
from app.models.brief import Brief, BriefClaim
from app.models.enums import (
    ActionStatus,
    ActionType,
    ActorType,
    BriefStatus,
    ClaimValidationStatus,
    EvidenceType,
    TraceStatus,
)
from app.models.observability import LLMTrace
from app.repositories.action import ActionRepository
from app.repositories.audit_log import AuditLogRepository
from app.repositories.brief import BriefRepository, LLMTraceRepository
from app.schemas.actions import (
    ActionListOut,
    ActionOut,
    ActionProposalContext,
    ActionProposalIssue,
    ActionSourceBriefOut,
    ContextClaim,
)
from app.schemas.evidence import WindowOut
from app.services.actions.errors import (
    ActionAlreadyProposedError,
    ActionNotFoundError,
    ActionProposalRejectedError,
    BriefNotValidError,
    NoActionableAnomalyError,
    SourceBriefNotFoundError,
)
from app.services.actions.policy import ALLOWED_ACTION_TYPES, validate_proposal
from app.services.actions.state_machine import ensure_transition
from app.services.evidence.resolver import EvidenceResolver
from app.services.evidence_ids import parse_evidence_id

OPERATION = "action_proposal"
ENTITY = "proposed_action"

logger = logging.getLogger(__name__)


def action_out(action: ProposedAction, brief: Brief) -> ActionOut:
    return ActionOut(
        id=action.id,
        action_type=action.action_type,
        title=action.title,
        description=action.description,
        rationale=action.rationale,
        investigation_steps=list(action.investigation_steps_json),
        evidence_ids=list(action.evidence_ids_json),
        status=action.status,
        source_brief=ActionSourceBriefOut(
            id=brief.id,
            headline=brief.headline,
            status=brief.status,
            analysis_window_start=brief.analysis_window_start,
            analysis_window_end=brief.analysis_window_end,
        ),
        created_at=action.created_at,
        updated_at=action.updated_at,
    )


def _is_anomaly(evidence_id: str) -> bool:
    return evidence_id.startswith(f"{EvidenceType.ANOMALY.value}-")


def _loggable_issue(issue: ActionProposalIssue) -> dict[str, str | None]:
    """Code, field and evidence ID only, and the ID only when well formed.

    ``evidence_id`` on a rejected proposal is whatever the model wrote, so a malformed
    value (arbitrary length, newlines) never reaches logs or the audit trail.
    """
    evidence_id = issue.evidence_id
    if evidence_id is not None and parse_evidence_id(evidence_id) is None:
        evidence_id = "<malformed>"
    return {"code": issue.code, "field": issue.field, "evidence_id": evidence_id}


class ActionProposalService:
    def __init__(
        self,
        session: Session,
        settings: Settings,
        client_factory: Callable[[], ActionLLMClient] | None = None,
    ) -> None:
        self.session = session
        self.settings = settings
        self.client_factory = client_factory
        self.actions = ActionRepository(session)
        self.briefs = BriefRepository(session)
        self.traces = LLMTraceRepository(session)
        self.audit = AuditLogRepository(session)

    def propose(self, brief_id: int) -> ActionOut:
        """Draft, validate and persist one ``pending_approval`` proposal for ``brief_id``.

        Raises:
            SourceBriefNotFoundError: the brief does not exist.
            BriefNotValidError: the brief is not ``valid``; the model is not called.
            ActionAlreadyProposedError: the brief already has a proposal (one per brief).
            NoActionableAnomalyError: the brief cites no resolvable anomaly.
            LLMNotConfiguredError: no API key/model/client; nothing is called or written.
            LLMError: the provider failed; an error trace is recorded.
            ActionProposalRejectedError: the draft failed the deterministic policy;
                nothing is persisted except the trace and an audit event.
        """
        found = self.briefs.get_with_claims(brief_id)
        if found is None:
            raise SourceBriefNotFoundError(f"Brief {brief_id} does not exist.")
        brief, claims = found
        if brief.status is not BriefStatus.VALID:
            raise BriefNotValidError(
                f"Brief {brief_id} is '{brief.status.value}'; only a valid brief can be "
                "used to propose an action."
            )
        self._ensure_no_proposal(brief_id)

        valid_claims = [c for c in claims if c.validation_status is ClaimValidationStatus.VALID]
        brief_ids = sorted({i for c in valid_claims for i in c.evidence_ids_json})
        resolver = EvidenceResolver(self.session)
        persisted = resolver.existing(brief_ids)
        citable = [i for i in brief_ids if i in persisted]
        if not any(_is_anomaly(i) for i in citable):
            raise NoActionableAnomalyError(
                f"Brief {brief_id} cites no detected anomaly, so there is nothing to investigate."
            )
        # Checked after the brief-level gates so their more specific errors win.
        if not self.settings.llm_configured:
            raise LLMNotConfiguredError("OPENAI_API_KEY and OPENAI_MODEL must be configured.")
        if self.client_factory is None:
            raise LLMNotConfiguredError("No LLM client is available.")
        context = self._context(brief, valid_claims, citable, resolver)

        started = time.monotonic()
        try:
            result = self.client_factory().propose_action(context)
        except LLMError as exc:
            self.traces.add(
                LLMTrace(
                    brief_id=brief_id,
                    operation=OPERATION,
                    model_name=self.settings.openai_model or "",
                    latency_ms=max(0, int((time.monotonic() - started) * 1000)),
                    status=TraceStatus.ERROR,
                    error_code=exc.code,
                    error_message=exc.message[:1000],
                )
            )
            self.session.commit()
            raise
        self.traces.add(
            LLMTrace(
                brief_id=brief_id,
                operation=OPERATION,
                model_name=result.model_name,
                latency_ms=result.latency_ms,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                status=TraceStatus.SUCCESS,
            )
        )

        output = result.output
        issues = validate_proposal(output, allowed_ids=brief_ids, persisted_ids=persisted)
        if issues:
            # Codes, fields and well-formed IDs only: model text never reaches logs or audit.
            summary = [_loggable_issue(i) for i in issues]
            self.audit.append(
                actor_type=ActorType.AI,
                actor_id=result.model_name,
                event_type="action.proposal_rejected",
                entity_type="brief",
                entity_id=str(brief_id),
                payload={"issues": summary},
            )
            self.session.commit()
            logger.warning(
                "Action proposal for brief %s rejected: %s",
                brief_id,
                ", ".join(
                    str(i["code"]) + (f"({i['evidence_id']})" if i["evidence_id"] else "")
                    for i in summary
                ),
            )
            raise ActionProposalRejectedError(
                "The proposed action failed grounding/policy validation and was not saved.",
                issues,
            )

        action = ProposedAction(
            brief_id=brief_id,
            action_type=ActionType(output.action_type),
            title=output.title,
            description=output.description,
            rationale=output.rationale,
            investigation_steps_json=list(output.investigation_steps),
            evidence_ids_json=list(output.evidence_ids),
            status=ActionStatus.PROPOSED,
        )
        try:
            with self.session.begin_nested():
                self.actions.add(action)
        except IntegrityError:
            # A concurrent request won the one-proposal-per-brief race.
            self.session.commit()
            self._ensure_no_proposal(brief_id)
            raise
        self.audit.append(
            actor_type=ActorType.AI,
            actor_id=result.model_name,
            event_type="action.proposed",
            entity_type=ENTITY,
            entity_id=str(action.id),
            payload={
                "brief_id": brief_id,
                "action_type": action.action_type.value,
                "evidence_ids": list(action.evidence_ids_json),
                "status": ActionStatus.PROPOSED.value,
            },
        )
        ensure_transition(action.status, ActionStatus.PENDING_APPROVAL)
        action.status = ActionStatus.PENDING_APPROVAL
        self.session.flush()
        self.audit.append(
            actor_type=ActorType.SYSTEM,
            event_type="action.status_changed",
            entity_type=ENTITY,
            entity_id=str(action.id),
            payload={
                "from": ActionStatus.PROPOSED.value,
                "to": ActionStatus.PENDING_APPROVAL.value,
            },
        )
        self.session.commit()
        self.session.refresh(action)
        return action_out(action, brief)

    def get(self, action_id: int) -> ActionOut:
        found = self.actions.get_with_brief(action_id)
        if found is None:
            raise ActionNotFoundError(f"Action {action_id} does not exist.")
        return action_out(*found)

    def list_actions(
        self, *, status: ActionStatus | None, limit: int, offset: int
    ) -> ActionListOut:
        rows = self.actions.list_with_briefs(status=status, limit=limit, offset=offset)
        return ActionListOut(items=[action_out(a, b) for a, b in rows], limit=limit, offset=offset)

    def _ensure_no_proposal(self, brief_id: int) -> None:
        existing = self.actions.get_for_brief(brief_id)
        if existing is not None:
            raise ActionAlreadyProposedError(
                f"Brief {brief_id} already has proposal {existing.id}.", existing.id
            )

    def _context(
        self,
        brief: Brief,
        claims: list[BriefClaim],
        citable: list[str],
        resolver: EvidenceResolver,
    ) -> ActionProposalContext:
        return ActionProposalContext(
            brief_id=brief.id,
            analysis_window=WindowOut(
                start=brief.analysis_window_start, end=brief.analysis_window_end
            ),
            headline=brief.headline,
            summary=brief.summary,
            claims=[
                ContextClaim(
                    claim_type=c.claim_type, text=c.text, evidence_ids=list(c.evidence_ids_json)
                )
                for c in claims
            ],
            allowed_action_types=sorted(ALLOWED_ACTION_TYPES),
            allowed_evidence_ids=citable,
            evidence=[resolver.resolve(i) for i in citable],
        )
