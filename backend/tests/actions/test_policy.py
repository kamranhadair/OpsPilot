"""The deterministic V1 action policy: allow-list and proposal grounding rules."""

import pytest
from pydantic import ValidationError

from app.models.enums import ActionType
from app.schemas.actions import ActionProposalOutput
from app.services.actions.policy import (
    ALLOWED_ACTION_TYPES,
    find_completion_claims,
    is_allowed_action_type,
    validate_proposal,
)
from tests.actions.conftest import proposal

ANOM = "ANOM-000001"
MTR = "MTR-000001"
SEG = "SEG-000001"
EVT = "EVT-000001"
BRIEF_IDS = {ANOM, MTR, SEG}


def _codes(output: ActionProposalOutput, allowed: set[str] = BRIEF_IDS) -> list[str]:
    issues = validate_proposal(output, allowed_ids=allowed, persisted_ids=allowed)
    return [i.code for i in issues]


def test_open_investigation_is_the_only_allowed_type() -> None:
    assert frozenset({ActionType.OPEN_INVESTIGATION}) == ALLOWED_ACTION_TYPES
    assert set(ActionType) == {ActionType.OPEN_INVESTIGATION}
    assert is_allowed_action_type("open_investigation")


def test_grounded_proposal_has_no_issues() -> None:
    assert _codes(proposal([ANOM, SEG, MTR])) == []


@pytest.mark.parametrize(
    "action_type", ["open_jira_ticket", "execute", "", "OPEN_INVESTIGATION", "approve"]
)
def test_unsupported_action_type_is_rejected(action_type: str) -> None:
    assert _codes(proposal([ANOM], action_type=action_type)) == ["UNSUPPORTED_ACTION_TYPE"]


def test_unknown_evidence_id_is_rejected_and_never_repaired() -> None:
    output = proposal([ANOM, "ANOM-999999"])
    issues = validate_proposal(output, allowed_ids=BRIEF_IDS, persisted_ids=BRIEF_IDS)
    assert [(i.code, i.evidence_id) for i in issues] == [("EVIDENCE_NOT_IN_BRIEF", "ANOM-999999")]
    assert output.evidence_ids == [ANOM, "ANOM-999999"]


def test_evidence_outside_the_brief_is_rejected_even_if_it_exists() -> None:
    other = "SEG-000777"
    issues = validate_proposal(
        proposal([ANOM, other]), allowed_ids=BRIEF_IDS, persisted_ids=BRIEF_IDS | {other}
    )
    assert [i.code for i in issues] == ["EVIDENCE_NOT_IN_BRIEF"]


def test_unresolved_evidence_is_rejected() -> None:
    issues = validate_proposal(
        proposal([ANOM, SEG]), allowed_ids=BRIEF_IDS, persisted_ids={ANOM, MTR}
    )
    assert [(i.code, i.evidence_id) for i in issues] == [("EVIDENCE_UNRESOLVED", SEG)]


def test_a_proposal_must_cite_an_anomaly() -> None:
    assert _codes(proposal([MTR, SEG])) == ["ANOMALY_EVIDENCE_MISSING"]


def test_empty_evidence_fails_structurally() -> None:
    with pytest.raises(ValidationError):
        proposal([])


@pytest.mark.parametrize(
    "overrides",
    [
        {"title": "   "},
        {"description": ""},
        {"rationale": "\n\t "},
        {"investigation_steps": ["Review the segment", "  "]},
        {"investigation_steps": []},
    ],
)
def test_blank_text_fails_structurally(overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        proposal([ANOM], **overrides)


def test_non_blank_text_is_kept_exactly_as_written() -> None:
    assert proposal([ANOM], title="  Investigate billing ").title == "  Investigate billing "


def test_extra_fields_fail_structurally() -> None:
    with pytest.raises(ValidationError):
        proposal([ANOM], approved=True)


@pytest.mark.parametrize("field", ["title", "description", "rationale"])
def test_causal_wording_with_events_in_context_is_rejected(field: str) -> None:
    output = proposal([ANOM, EVT], **{field: "The spike was caused by the deployment."})
    issues = validate_proposal(
        output, allowed_ids=BRIEF_IDS | {EVT}, persisted_ids=BRIEF_IDS | {EVT}
    )
    assert [(i.code, i.field, i.phrase) for i in issues] == [
        ("CAUSAL_LANGUAGE", field, "caused by")
    ]


@pytest.mark.parametrize(
    ("field", "text", "phrase"),
    [
        ("rationale", "The spike was caused by EMEA Billing customers.", "caused by"),
        ("description", "Volume rose because of the enterprise tier.", "because of"),
        ("title", "Backlog growth resulted from slow responses", "resulted from"),
    ],
)
def test_causal_wording_is_rejected_without_any_event_evidence(
    field: str, text: str, phrase: str
) -> None:
    # Segments and anomalies show association only, so causation is never supported in V1.
    issues = validate_proposal(
        proposal([ANOM, SEG], **{field: text}), allowed_ids=BRIEF_IDS, persisted_ids=BRIEF_IDS
    )
    assert [(i.code, i.field, i.phrase) for i in issues] == [("CAUSAL_LANGUAGE", field, phrase)]


def test_causal_wording_in_a_step_is_rejected() -> None:
    output = proposal([ANOM], investigation_steps=["Confirm the spike is DUE TO the release"])
    assert _codes(output) == ["CAUSAL_LANGUAGE"]


def test_cautious_wording_with_events_is_allowed() -> None:
    output = proposal(
        [ANOM, EVT],
        rationale="The spike coincided with a deployment that occurred after the baseline; "
        "the timing is temporally associated and warrants investigation.",
    )
    assert _codes(output, BRIEF_IDS | {EVT}) == []


@pytest.mark.parametrize(
    "text",
    [
        "The investigation has been opened.",
        "An investigation was created for billing.",
        "We have escalated this to engineering.",
        "This was already investigated.",
        "OpsPilot has executed the action.",
    ],
)
def test_claiming_the_action_already_happened_is_rejected(text: str) -> None:
    issues = validate_proposal(
        proposal([ANOM], description=text), allowed_ids=BRIEF_IDS, persisted_ids=BRIEF_IDS
    )
    assert [(i.code, i.field) for i in issues] == [("ACTION_CLAIMED_COMPLETE", "description")]


@pytest.mark.parametrize(
    "text",
    [
        "Open an investigation into billing volume.",
        "Check whether the incident was opened before the spike.",
        "Confirm if a fix has been deployed.",
    ],
)
def test_future_or_evidence_descriptions_are_not_completion_claims(text: str) -> None:
    assert find_completion_claims(text) == []


def test_every_issue_is_reported() -> None:
    output = proposal(
        ["MTR-999999"], action_type="page_oncall", title="Investigation has been opened"
    )
    assert sorted(_codes(output)) == sorted(
        [
            "UNSUPPORTED_ACTION_TYPE",
            "EVIDENCE_NOT_IN_BRIEF",
            "ANOMALY_EVIDENCE_MISSING",
            "ACTION_CLAIMED_COMPLETE",
        ]
    )
