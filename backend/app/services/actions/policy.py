"""Deterministic V1 action policy: the allow-list and proposal grounding rules.

Nothing here calls a model, queries the database or rewrites text/IDs. The caller
supplies the brief's citable evidence IDs and the subset that exists in persisted
evidence. A proposal is rejected when it:

- names an action type outside the allow-list;
- cites no evidence, cites an ID the source brief did not cite, or cites an ID that no
  longer resolves;
- cites no anomaly (an investigation must be anchored to a detected anomaly);
- uses prohibited causal wording anywhere. Unlike brief claims (Spec 10), this is not
  conditional on event evidence: no V1 evidence type supports causal analysis
  (segments and anomalies show association, events show temporal proximity), so any
  causal assertion in a proposal is unsupported;
- claims the action has already happened (the system has not executed anything).
"""

import re
from collections.abc import Collection

from app.models.enums import ActionType, EvidenceType
from app.schemas.actions import ActionProposalIssue, ActionProposalOutput, ProposalField
from app.services.briefs.validator import find_causal_phrases, normalize_text

# V1 allow-list. Adding an action type is a deliberate code change, never a model choice.
ALLOWED_ACTION_TYPES: frozenset[ActionType] = frozenset({ActionType.OPEN_INVESTIGATION})

_DONE_VERBS = "opened|created|started|launched|executed|completed|assigned|escalated|filed"
# Matched on normalized text. Each pattern asserts that *this* action already took place;
# nouns like "incident" are excluded because evidence may truthfully say one was opened.
_COMPLETION_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"\b(?:investigation|action|proposal)\s+"
        rf"(?:has been|have been|was|were|is now|is already)\s+(?:{_DONE_VERBS})\b"
    ),
    re.compile(rf"\balready\s+(?:been\s+)?(?:{_DONE_VERBS}|investigated)\b"),
    re.compile(rf"\b(?:we|i|opspilot)\s+(?:have|has)\s+(?:{_DONE_VERBS})\b"),
)


def _prefix(evidence_type: EvidenceType) -> str:
    return f"{evidence_type.value}-"


def find_completion_claims(text: str) -> list[str]:
    """Matched phrases asserting that an action has already occurred."""
    normalized = normalize_text(text)
    return [m.group(0) for pattern in _COMPLETION_PATTERNS for m in pattern.finditer(normalized)]


def is_allowed_action_type(action_type: str) -> bool:
    return action_type in {t.value for t in ALLOWED_ACTION_TYPES}


def _texts(output: ActionProposalOutput) -> list[tuple[ProposalField, str]]:
    texts: list[tuple[ProposalField, str]] = [
        ("title", output.title),
        ("description", output.description),
        ("rationale", output.rationale),
    ]
    texts.extend(("investigation_steps", step) for step in output.investigation_steps)
    return texts


def validate_proposal(
    output: ActionProposalOutput,
    *,
    allowed_ids: Collection[str],
    persisted_ids: Collection[str],
) -> list[ActionProposalIssue]:
    """Every reason ``output`` must not be persisted; empty means grounded."""
    issues: list[ActionProposalIssue] = []

    if not is_allowed_action_type(output.action_type):
        issues.append(
            ActionProposalIssue(
                code="UNSUPPORTED_ACTION_TYPE",
                message=f"{output.action_type!r} is not an allowed V1 action type.",
                field="action_type",
            )
        )

    cited = list(dict.fromkeys(output.evidence_ids))
    if not cited:
        issues.append(
            ActionProposalIssue(
                code="EVIDENCE_MISSING", message="A proposal must cite at least one ID."
            )
        )
    for evidence_id in cited:
        if evidence_id not in allowed_ids:
            issues.append(
                ActionProposalIssue(
                    code="EVIDENCE_NOT_IN_BRIEF",
                    message=f"{evidence_id} is not evidence cited by the source brief.",
                    evidence_id=evidence_id,
                )
            )
        elif evidence_id not in persisted_ids:
            issues.append(
                ActionProposalIssue(
                    code="EVIDENCE_UNRESOLVED",
                    message=f"{evidence_id} cannot be resolved in persisted evidence.",
                    evidence_id=evidence_id,
                )
            )
    if cited and not any(i.startswith(_prefix(EvidenceType.ANOMALY)) for i in cited):
        issues.append(
            ActionProposalIssue(
                code="ANOMALY_EVIDENCE_MISSING",
                message="An investigation must cite at least one detected anomaly (ANOM-).",
            )
        )

    for field, text in _texts(output):
        for phrase in find_causal_phrases(text):
            issues.append(
                ActionProposalIssue(
                    code="CAUSAL_LANGUAGE",
                    message=f"The {field} asserts causation ({phrase!r}); V1 evidence "
                    "supports association or temporal proximity only.",
                    phrase=phrase,
                    field=field,
                )
            )
        for phrase in find_completion_claims(text):
            issues.append(
                ActionProposalIssue(
                    code="ACTION_CLAIMED_COMPLETE",
                    message=f"The {field} claims the action already occurred ({phrase!r}).",
                    phrase=phrase,
                    field=field,
                )
            )
    return issues
