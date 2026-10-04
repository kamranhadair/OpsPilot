"""Deterministic validation of brief claims against the exact Evidence Bundle.

A parsed model response is not trustworthy until this passes. Nothing here calls a
model, queries the database or rewrites text/IDs: the caller supplies the bundle the
model received and the set of cited IDs that exist in persisted evidence.

A claim is invalid when it cites no evidence, cites an ID outside the bundle allow-list,
cites an ID that cannot be resolved in persisted evidence, cites an observed fact from a
different analysis window (V1 has no disclosure mechanism), or uses prohibited causal
wording while citing a contextual event. The headline/summary are checked for causal
wording whenever the bundle contains related events, since they carry no citations.
"""

import re
import unicodedata
from collections.abc import Collection, Sequence
from dataclasses import dataclass, field
from typing import Literal

from app.models.enums import BriefStatus, ClaimValidationStatus, EvidenceType
from app.schemas.briefs import DraftClaim, ValidationIssue
from app.schemas.evidence import EvidenceBundle, WindowOut

# V1 event-causation phrases. Matched as whole words on normalized text; never rewritten.
PROHIBITED_CAUSAL_PHRASES: tuple[str, ...] = (
    "caused by",
    "due to",
    "resulted from",
    "results from",
    "resulting from",
    "led to",
    "leads to",
    "leading to",
    "because of",
    "triggered by",
)

_PHRASE_PATTERNS = tuple(
    (phrase, re.compile(r"\b" + r"\s".join(map(re.escape, phrase.split())) + r"\b"))
    for phrase in PROHIBITED_CAUSAL_PHRASES
)
_TYPOGRAPHIC = str.maketrans(
    {
        "‘": "'",
        "’": "'",
        "“": '"',
        "”": '"',
        "‐": "-",
        "‑": "-",
        "‒": "-",
        "–": "-",
        "—": "-",
        " ": " ",
    }
)
_WHITESPACE = re.compile(r"\s+")


def normalize_text(text: str) -> str:
    """NFKC, ASCII punctuation, casefolded, single-spaced."""
    normalized = unicodedata.normalize("NFKC", text).translate(_TYPOGRAPHIC).casefold()
    return _WHITESPACE.sub(" ", normalized).strip()


def find_causal_phrases(text: str) -> list[str]:
    """The prohibited phrases present in ``text``, in list order."""
    normalized = normalize_text(text)
    return [phrase for phrase, pattern in _PHRASE_PATTERNS if pattern.search(normalized)]


@dataclass(frozen=True)
class ClaimValidation:
    status: ClaimValidationStatus
    issues: list[ValidationIssue]


@dataclass(frozen=True)
class BriefValidationResult:
    status: BriefStatus
    claims: list[ClaimValidation]
    brief_issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def all_issues(self) -> list[ValidationIssue]:
        """Brief-level issues followed by every claim issue tagged with its ordinal."""
        issues = list(self.brief_issues)
        for ordinal, claim in enumerate(self.claims):
            issues.extend(i.model_copy(update={"claim_ordinal": ordinal}) for i in claim.issues)
        return issues


def _unique(ids: Sequence[str]) -> list[str]:
    return list(dict.fromkeys(ids))


def _is_event(evidence_id: str) -> bool:
    return evidence_id.startswith(f"{EvidenceType.EVENT.value}-")


def _validate_claim(
    claim: DraftClaim,
    windows: dict[str, WindowOut | None],
    persisted_ids: Collection[str],
    brief_window: WindowOut,
) -> ClaimValidation:
    issues: list[ValidationIssue] = []
    cited = _unique(claim.evidence_ids)
    if not cited:
        issues.append(
            ValidationIssue(
                code="EVIDENCE_MISSING", message="A factual claim must cite at least one ID."
            )
        )
    for evidence_id in cited:
        if evidence_id not in windows:
            issues.append(
                ValidationIssue(
                    code="EVIDENCE_NOT_IN_BUNDLE",
                    message=f"{evidence_id} is not in the Evidence Bundle allow-list.",
                    evidence_id=evidence_id,
                )
            )
            continue
        if evidence_id not in persisted_ids:
            issues.append(
                ValidationIssue(
                    code="EVIDENCE_UNRESOLVED",
                    message=f"{evidence_id} cannot be resolved in persisted evidence.",
                    evidence_id=evidence_id,
                )
            )
        window = windows[evidence_id]
        if window is not None and window != brief_window:
            issues.append(
                ValidationIssue(
                    code="EVIDENCE_WINDOW_MISMATCH",
                    message=f"{evidence_id} belongs to a different analysis window.",
                    evidence_id=evidence_id,
                )
            )
    if any(_is_event(evidence_id) for evidence_id in cited):
        for phrase in find_causal_phrases(claim.text):
            issues.append(
                ValidationIssue(
                    code="CAUSAL_LANGUAGE_FOR_EVENT",
                    message=f"Claim cites a contextual event and asserts causation ({phrase!r}).",
                    phrase=phrase,
                )
            )
    status = ClaimValidationStatus.INVALID if issues else ClaimValidationStatus.VALID
    return ClaimValidation(status=status, issues=issues)


def validate_brief(
    *,
    headline: str,
    summary: str,
    claims: Sequence[DraftClaim],
    bundle: EvidenceBundle,
    persisted_ids: Collection[str],
    brief_window: WindowOut,
) -> BriefValidationResult:
    """Validate every claim and the narrative; the brief is valid only if nothing failed."""
    windows: dict[str, WindowOut | None] = {
        item.evidence_id: item.window
        for item in (*bundle.metrics, *bundle.anomalies, *bundle.contributors)
    }
    windows.update({event.evidence_id: None for event in bundle.related_events})

    results = [_validate_claim(c, windows, persisted_ids, brief_window) for c in claims]

    brief_issues: list[ValidationIssue] = []
    if not claims:
        brief_issues.append(
            ValidationIssue(
                code="BRIEF_HAS_NO_CLAIMS",
                message="A brief without evidence-backed claims cannot be validated.",
            )
        )
    if bundle.related_events:
        narrative: tuple[tuple[Literal["headline", "summary"], str], ...] = (
            ("headline", headline),
            ("summary", summary),
        )
        for name, text in narrative:
            for phrase in find_causal_phrases(text):
                brief_issues.append(
                    ValidationIssue(
                        code="CAUSAL_LANGUAGE_IN_NARRATIVE",
                        message=f"The {name} asserts causation ({phrase!r}) while related "
                        "events are in evidence.",
                        phrase=phrase,
                        field=name,
                    )
                )

    invalid = brief_issues or any(r.status is ClaimValidationStatus.INVALID for r in results)
    return BriefValidationResult(
        status=BriefStatus.INVALID if invalid else BriefStatus.VALID,
        claims=results,
        brief_issues=brief_issues,
    )
