"""Deterministic claim validation: pure unit tests, no database or model."""

from datetime import timedelta

import pytest

from app.models.enums import BriefStatus, ClaimType, ClaimValidationStatus
from app.schemas.briefs import DraftClaim
from app.schemas.evidence import EvidenceBundle, WindowOut
from app.services.briefs.validator import (
    PROHIBITED_CAUSAL_PHRASES,
    BriefValidationResult,
    find_causal_phrases,
    normalize_text,
    validate_brief,
)
from tests.evidence.test_schema import CURRENT, bundle

ALL_IDS = {"MTR-000001", "ANOM-000001", "SEG-000001", "EVT-000001"}


def claim(text: str, *ids: str) -> DraftClaim:
    return DraftClaim(claim_type=ClaimType.OBSERVATION, text=text, evidence_ids=list(ids))


def run(
    *claims: DraftClaim,
    headline: str = "Billing volume is elevated",
    summary: str = "Volume rose against baseline.",
    evidence: EvidenceBundle | None = None,
    persisted: set[str] | None = None,
    window: WindowOut = CURRENT,
) -> BriefValidationResult:
    return validate_brief(
        headline=headline,
        summary=summary,
        claims=list(claims),
        bundle=evidence if evidence is not None else bundle(),
        persisted_ids=ALL_IDS if persisted is None else persisted,
        brief_window=window,
    )


def codes(result: BriefValidationResult) -> list[str]:
    return [i.code for i in result.all_issues]


def test_all_known_ids_make_a_valid_brief() -> None:
    result = run(
        claim("Volume rose 100%.", "MTR-000001", "ANOM-000001"),
        claim("EMEA holds most of the change.", "SEG-000001"),
        claim("A deploy coincided with the spike.", "EVT-000001"),
    )
    assert result.status is BriefStatus.VALID
    assert all(c.status is ClaimValidationStatus.VALID for c in result.claims)
    assert result.all_issues == []


def test_unknown_id_invalidates_claim_and_brief_without_repair() -> None:
    result = run(claim("Volume rose.", "MTR-999999"))
    assert result.status is BriefStatus.INVALID
    (issue,) = result.claims[0].issues
    assert issue.code == "EVIDENCE_NOT_IN_BUNDLE" and issue.evidence_id == "MTR-999999"
    assert result.all_issues[0].claim_ordinal == 0


def test_persisted_id_outside_the_bundle_allow_list_is_invalid() -> None:
    result = run(claim("x", "MTR-000002"), persisted=ALL_IDS | {"MTR-000002"})
    assert codes(result) == ["EVIDENCE_NOT_IN_BUNDLE"]


def test_bundle_id_missing_from_persisted_evidence_is_unresolved() -> None:
    result = run(claim("x", "MTR-000001"), persisted=ALL_IDS - {"MTR-000001"})
    assert codes(result) == ["EVIDENCE_UNRESOLVED"]


def test_empty_evidence_list_is_invalid() -> None:
    empty = DraftClaim.model_construct(claim_type=ClaimType.OBSERVATION, text="x", evidence_ids=[])
    assert codes(run(empty)) == ["EVIDENCE_MISSING"]


def test_duplicate_citations_are_tolerated_and_checked_once() -> None:
    result = run(claim("x", "MTR-000001", "MTR-000001"))
    assert result.status is BriefStatus.VALID
    bad = run(claim("x", "MTR-999999", "MTR-999999"))
    assert codes(bad) == ["EVIDENCE_NOT_IN_BUNDLE"]


def test_observed_fact_from_another_window_is_invalid_but_events_are_exempt() -> None:
    other = WindowOut(start=CURRENT.start + timedelta(days=1), end=CURRENT.end + timedelta(days=1))
    result = run(claim("x", "MTR-000001"), claim("y", "EVT-000001"), window=other)
    assert result.claims[0].issues[0].code == "EVIDENCE_WINDOW_MISMATCH"
    assert result.claims[1].status is ClaimValidationStatus.VALID


def test_one_valid_and_one_invalid_claim() -> None:
    result = run(claim("ok", "MTR-000001"), claim("bad", "ANOM-424242"))
    assert result.status is BriefStatus.INVALID
    assert [c.status for c in result.claims] == [
        ClaimValidationStatus.VALID,
        ClaimValidationStatus.INVALID,
    ]
    assert [i.claim_ordinal for i in result.all_issues] == [1]


def test_brief_without_claims_is_invalid() -> None:
    assert codes(run()) == ["BRIEF_HAS_NO_CLAIMS"]


# --- causal guardrail ----------------------------------------------------------------


@pytest.mark.parametrize("phrase", PROHIBITED_CAUSAL_PHRASES)
def test_every_prohibited_phrase_with_event_evidence_is_rejected(phrase: str) -> None:
    result = run(claim(f"The spike was {phrase} the deploy.", "EVT-000001", "MTR-000001"))
    assert result.status is BriefStatus.INVALID
    (issue,) = result.claims[0].issues
    assert issue.code == "CAUSAL_LANGUAGE_FOR_EVENT" and issue.phrase == phrase


@pytest.mark.parametrize(
    "text",
    [
        "Volume spiked, CAUSED BY the deploy.",
        "Volume spiked,  Caused\n  by the deploy.",
        "Volume spiked Due To the 2.4 release.",
        "Errors “resulted from” the release.",
        "The release Led To more tickets.",
    ],
)
def test_matching_is_normalized_and_case_insensitive(text: str) -> None:
    result = run(claim(text, "EVT-000001"))
    assert codes(result) == ["CAUSAL_LANGUAGE_FOR_EVENT"]


@pytest.mark.parametrize(
    "text",
    [
        "The spike coincided with the deploy.",
        "The spike occurred after the 2.4 release.",
        "Volume is temporally associated with the deploy.",
        "The deploy warrants investigation.",
        "Tickets were overdue tomorrow.",  # 'due to' must match whole words only
        "Invoices became due today.",
    ],
)
def test_cautious_wording_remains_allowed(text: str) -> None:
    assert run(claim(text, "EVT-000001")).status is BriefStatus.VALID


def test_causal_phrase_without_event_citation_is_not_an_event_claim() -> None:
    result = run(claim("Volume rose due to billing tickets.", "MTR-000001", "SEG-000001"))
    assert result.status is BriefStatus.VALID


@pytest.mark.parametrize("where", ["headline", "summary"])
def test_causal_narrative_is_invalid_when_events_are_in_evidence(where: str) -> None:
    text = "Spike caused by the deploy"
    ok = claim("ok", "MTR-000001")
    result = run(ok, headline=text) if where == "headline" else run(ok, summary=text)
    assert result.status is BriefStatus.INVALID
    (issue,) = result.brief_issues
    assert issue.code == "CAUSAL_LANGUAGE_IN_NARRATIVE"
    assert issue.field == where and issue.phrase == "caused by"
    assert result.claims[0].status is ClaimValidationStatus.VALID


def test_causal_narrative_without_events_in_evidence_is_allowed() -> None:
    result = run(
        claim("ok", "MTR-000001"),
        headline="Volume rose due to billing",
        evidence=bundle(related_events=[]),
    )
    assert result.status is BriefStatus.VALID


def test_normalization_and_detection_helpers() -> None:
    assert normalize_text("  Due’s \n TO ") == "due's to"
    assert find_causal_phrases("nothing here") == []
    assert find_causal_phrases("It LED TO x, because of y") == ["led to", "because of"]
