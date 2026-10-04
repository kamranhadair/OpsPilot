"""The model output contract is structural: it demands evidence IDs but never judges them."""

import pytest
from pydantic import ValidationError

from app.schemas.briefs import BriefDraftOutput

CLAIM: dict[str, object] = {
    "claim_type": "observation",
    "text": "t",
    "evidence_ids": ["MTR-000001"],
}
VALID: dict[str, object] = {
    "headline": "h",
    "summary": "s",
    "claims": [CLAIM],
    "attention_items": ["look"],
}


def test_valid_payload_parses() -> None:
    out = BriefDraftOutput.model_validate(VALID)
    assert out.claims[0].evidence_ids == ["MTR-000001"]


def test_unknown_evidence_id_is_accepted_here_and_left_untouched() -> None:
    payload = {**VALID, "claims": [{**CLAIM, "evidence_ids": ["MTR-999999"]}]}
    assert BriefDraftOutput.model_validate(payload).claims[0].evidence_ids == ["MTR-999999"]


@pytest.mark.parametrize("claim_type", ["observation", "inference"])
def test_claim_without_evidence_ids_is_rejected(claim_type: str) -> None:
    claim = {"claim_type": claim_type, "text": "t", "evidence_ids": []}
    with pytest.raises(ValidationError):
        BriefDraftOutput.model_validate({**VALID, "claims": [claim]})


@pytest.mark.parametrize(
    "mutation",
    [
        {"extra": 1},
        {"headline": ""},
        {"headline": "x" * 501},
        {"claims": [{"claim_type": "fact", "text": "t", "evidence_ids": ["MTR-000001"]}]},
        {"claims": [{"claim_type": "observation", "text": "", "evidence_ids": ["MTR-000001"]}]},
    ],
)
def test_malformed_payloads_are_rejected(mutation: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        BriefDraftOutput.model_validate({**VALID, **mutation})


@pytest.mark.parametrize("missing", ["headline", "summary", "claims", "attention_items"])
def test_missing_fields_are_rejected(missing: str) -> None:
    payload = {k: v for k, v in VALID.items() if k != missing}
    with pytest.raises(ValidationError):
        BriefDraftOutput.model_validate(payload)


def test_json_schema_requires_evidence_ids_per_claim() -> None:
    schema = BriefDraftOutput.model_json_schema()
    claim = schema["$defs"]["DraftClaim"]
    assert claim["properties"]["evidence_ids"]["minItems"] == 1
    assert "evidence_ids" in claim["required"]
    assert claim["additionalProperties"] is False
