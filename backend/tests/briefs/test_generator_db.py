"""BriefService persistence, trace and boundary behaviour against the test database."""

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.integrations.llm.base import (
    LLMMalformedOutputError,
    LLMNotConfiguredError,
    LLMRateLimitedError,
    LLMTimeoutError,
)
from app.integrations.llm.prompts import build_user_message
from app.models import Brief, BriefClaim, LLMTrace
from app.models.enums import (
    AnomalyStatus,
    BriefStatus,
    ClaimType,
    ClaimValidationStatus,
    TraceStatus,
)
from app.repositories.anomaly_repository import AnomalyRepository
from app.schemas.briefs import DraftClaim
from app.schemas.evidence import EvidenceBundle
from app.services.briefs.errors import (
    BriefEvidenceUnavailableError,
    BriefNotFoundError,
    NoValidatedBriefError,
)
from app.services.briefs.generator import BriefService
from app.services.evidence.assembler import EvidenceBundleAssembler
from tests.briefs.conftest import FakeBriefClient, draft_output, make_settings
from tests.evidence.conftest import detect_billing_volume
from tests.metrics.conftest import World

pytestmark = pytest.mark.db


def _count(session: Session, model: type) -> int:
    return session.execute(select(func.count()).select_from(model)).scalar_one()


def _service(session: Session, client: FakeBriefClient, **settings: object) -> BriefService:
    return BriefService(session, make_settings(**settings), lambda: client)


def test_response_persists_ordered_claims_with_per_claim_validation(
    volume_world: World, clean_briefs: Session
) -> None:
    anomaly_id = detect_billing_volume(volume_world)
    claims = (
        DraftClaim(claim_type=ClaimType.OBSERVATION, text="first", evidence_ids=[anomaly_id]),
        DraftClaim(
            claim_type=ClaimType.INFERENCE,
            text="second",
            evidence_ids=["MTR-999999", anomaly_id],  # unknown ID must be kept verbatim
        ),
        DraftClaim(claim_type=ClaimType.OBSERVATION, text="third", evidence_ids=[anomaly_id]),
    )
    client = FakeBriefClient(draft_output(*claims, attention=["check billing"]))

    response = _service(clean_briefs, client).generate()

    assert response.status == BriefStatus.INVALID  # one fabricated ID invalidates the brief
    assert response.attention_items == ["check billing"]
    assert [c.text for c in response.claims] == ["first", "second", "third"]
    stored = BriefService(clean_briefs, make_settings()).get(response.id)
    assert [c.ordinal for c in stored.claims] == [0, 1, 2]
    assert stored.claims[1].evidence_ids == ["MTR-999999", anomaly_id]
    assert [c.validation_status for c in stored.claims] == [
        ClaimValidationStatus.VALID,
        ClaimValidationStatus.INVALID,
        ClaimValidationStatus.VALID,
    ]
    assert [i.code for i in stored.claims[1].validation_errors] == ["EVIDENCE_NOT_IN_BUNDLE"]
    assert [(i.code, i.claim_ordinal) for i in stored.validation_errors] == [
        ("EVIDENCE_NOT_IN_BUNDLE", 1)
    ]
    assert stored.model_name == "test-model"
    assert not hasattr(stored, "attention_items")


def test_success_records_one_linked_trace(volume_world: World, clean_briefs: Session) -> None:
    detect_billing_volume(volume_world)
    response = _service(clean_briefs, FakeBriefClient(draft_output())).generate()

    trace = clean_briefs.execute(select(LLMTrace)).scalar_one()
    assert trace.brief_id == response.id
    assert trace.status == TraceStatus.SUCCESS
    assert (trace.input_tokens, trace.output_tokens, trace.latency_ms) == (123, 45, 7)
    assert trace.operation == "brief_generation"
    assert trace.error_code is None


def test_model_receives_exactly_the_assembled_bundle(
    volume_world: World, clean_briefs: Session
) -> None:
    detect_billing_volume(volume_world)
    client = FakeBriefClient(draft_output())

    _service(clean_briefs, client).generate()

    expected = EvidenceBundleAssembler(clean_briefs, event_lookback_hours=72).assemble(None)
    assert len(client.bundles) == 1
    received = client.bundles[0]
    assert isinstance(received, EvidenceBundle)
    assert received.signature == expected.signature
    assert received.allowed_evidence_ids == expected.allowed_evidence_ids
    # The user message is the bundle and nothing else (no raw ticket rows).
    assert build_user_message(received) == expected.model_dump_json()


@pytest.mark.parametrize(
    "error",
    [
        LLMTimeoutError("timed out"),
        LLMRateLimitedError("slow down"),
        LLMMalformedOutputError("bad shape"),
    ],
)
def test_provider_failure_records_error_trace_and_no_brief(
    volume_world: World, clean_briefs: Session, error: Exception
) -> None:
    detect_billing_volume(volume_world)
    with pytest.raises(type(error)):
        _service(clean_briefs, FakeBriefClient(error=error)).generate()  # type: ignore[arg-type]

    trace = clean_briefs.execute(select(LLMTrace)).scalar_one()
    assert trace.status == TraceStatus.ERROR
    assert trace.error_code == error.code  # type: ignore[attr-defined]
    assert trace.brief_id is None
    assert _count(clean_briefs, Brief) == 0
    assert _count(clean_briefs, BriefClaim) == 0


@pytest.mark.parametrize("overrides", [{"openai_api_key": None}, {"openai_model": None}])
def test_missing_credentials_never_call_the_model_or_write_anything(
    volume_world: World, clean_briefs: Session, overrides: dict[str, object]
) -> None:
    detect_billing_volume(volume_world)
    client = FakeBriefClient(draft_output())

    with pytest.raises(LLMNotConfiguredError):
        _service(clean_briefs, client, **overrides).generate()

    assert client.bundles == []
    assert _count(clean_briefs, Brief) == 0
    assert _count(clean_briefs, LLMTrace) == 0


def test_blank_key_counts_as_not_configured() -> None:
    assert make_settings(openai_api_key="   ").llm_configured is False
    assert make_settings().llm_configured is True


def test_empty_bundle_does_not_call_the_model(clean_briefs: Session) -> None:
    client = FakeBriefClient(draft_output())
    with pytest.raises(BriefEvidenceUnavailableError):
        _service(clean_briefs, client).generate()
    assert client.bundles == []
    assert _count(clean_briefs, LLMTrace) == 0


def test_window_without_anomalies_still_reaches_the_model(
    volume_world: World, clean_briefs: Session
) -> None:
    detect_billing_volume(volume_world)
    rows, _ = AnomalyRepository(clean_briefs).list_with_snapshots(
        severity=None,
        status=AnomalyStatus.ACTIVE,
        metric_key=None,
        start=None,
        end=None,
        limit=200,
        offset=0,
    )
    for anomaly, _snapshot in rows:
        anomaly.status = AnomalyStatus.RESOLVED
    clean_briefs.flush()
    client = FakeBriefClient(draft_output())

    response = _service(clean_briefs, client).generate()

    assert response.claims == []
    assert len(client.bundles) == 1
    assert client.bundles[0].anomalies == []
    assert client.bundles[0].metrics


def test_get_and_latest_not_found(clean_briefs: Session) -> None:
    service = BriefService(clean_briefs, make_settings())
    with pytest.raises(BriefNotFoundError):
        service.get(999_999)
    with pytest.raises(NoValidatedBriefError):
        service.latest()


def _ok(anomaly_id: str) -> DraftClaim:
    return DraftClaim(claim_type=ClaimType.OBSERVATION, text="ok", evidence_ids=[anomaly_id])


def test_latest_returns_the_newest_validated_brief(
    volume_world: World, clean_briefs: Session
) -> None:
    anomaly_id = detect_billing_volume(volume_world)
    service = _service(clean_briefs, FakeBriefClient(draft_output(_ok(anomaly_id))))
    service.generate()
    second = service.generate()
    assert second.status == BriefStatus.VALID
    assert service.latest().id == second.id


def test_real_bundle_ids_validate_and_fabricated_ids_are_logged(
    volume_world: World, clean_briefs: Session, caplog: pytest.LogCaptureFixture
) -> None:
    anomaly_id = detect_billing_volume(volume_world)
    bundle = EvidenceBundleAssembler(clean_briefs, event_lookback_hours=72).assemble(None)
    every_id = DraftClaim(
        claim_type=ClaimType.OBSERVATION, text="all", evidence_ids=bundle.allowed_evidence_ids
    )
    valid = _service(clean_briefs, FakeBriefClient(draft_output(every_id))).generate()
    assert valid.status == BriefStatus.VALID
    assert valid.claims[0].validation_status == ClaimValidationStatus.VALID

    secret_text = "fabricated narrative text"
    bad = DraftClaim(
        claim_type=ClaimType.OBSERVATION, text=secret_text, evidence_ids=["SEG-999999"]
    )
    with caplog.at_level("WARNING", logger="app.services.briefs.generator"):
        invalid = _service(
            clean_briefs, FakeBriefClient(draft_output(_ok(anomaly_id), bad))
        ).generate()

    assert invalid.status == BriefStatus.INVALID
    stored = clean_briefs.get(Brief, invalid.id)
    assert stored is not None and stored.status == BriefStatus.INVALID
    errors = stored.validation_errors_json
    assert isinstance(errors, list)
    assert errors[0]["code"] == "EVIDENCE_NOT_IN_BUNDLE"
    assert _count(clean_briefs, LLMTrace) == 2
    assert f"Brief {invalid.id} failed validation" in caplog.text
    assert "EVIDENCE_NOT_IN_BUNDLE" in caplog.text and "SEG-999999" in caplog.text
    assert secret_text not in caplog.text


def test_brief_without_claims_is_invalid(volume_world: World, clean_briefs: Session) -> None:
    detect_billing_volume(volume_world)
    response = _service(clean_briefs, FakeBriefClient(draft_output())).generate()
    assert response.status == BriefStatus.INVALID
    assert [i.code for i in response.validation_errors] == ["BRIEF_HAS_NO_CLAIMS"]
