"""Versioned evaluation cases: every file loads and the required categories are covered."""

import json
import shutil
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.evals import cases
from app.evals.run import AI_SUITES, DETERMINISTIC_SUITES, run_evaluation
from app.schemas.evaluations import EvalCategory
from app.services.demo_data.config import SEED_VERSION
from tests.evals.conftest import offline_context

SPEC_CASES = {
    "anomaly.planted_billing_volume",  # 1. planted Billing spike
    "normal.technical_final_day",  # 2. normal queue/day
    "contributor.emea_enterprise_top",  # 3. EMEA Enterprise attribution
    "citation.fabricated_id",  # 4. fabricated citation
    "causal.unsupported_caused_by",  # 5. unsupported causal wording
    "causal.grounded_correlation",  # 6. grounded correlation wording
    "action.ungrounded_evidence",  # 7. ungrounded action evidence
    "approval.execute_pending_blocked",  # 8. execute without approval
}


def all_case_ids() -> set[str]:
    golden = cases.load_anomaly_golden()
    return {
        *(c.case_id for c in cases.load_metric_fixtures().cases),
        *(c.case_id for c in golden.planted),
        *(c.case_id for c in golden.normal),
        *(c.case_id for c in cases.load_contributor_golden().cases),
        *(c.case_id for c in cases.load_brief_guardrails().cases),
        *(c.case_id for c in cases.load_action_guardrails().cases),
        *(c.case_id for c in cases.load_approval_cases().cases),
    }


def test_every_case_file_loads_and_ids_are_unique() -> None:
    ids = all_case_ids()
    assert ids >= SPEC_CASES
    total = (
        len(cases.load_metric_fixtures().cases)
        + len(cases.load_anomaly_golden().planted)
        + len(cases.load_anomaly_golden().normal)
        + len(cases.load_contributor_golden().cases)
        + len(cases.load_brief_guardrails().cases)
        + len(cases.load_action_guardrails().cases)
        + len(cases.load_approval_cases().cases)
    )
    assert total == len(ids)


def test_suites_cover_every_category() -> None:
    covered = {category for _, _, category in (*DETERMINISTIC_SUITES, *AI_SUITES)}
    report = run_evaluation(offline_context(), "all")
    assert {c.category for c in report.cases} == set(EvalCategory)
    assert covered <= set(EvalCategory)


def test_seeded_golden_cases_are_versioned_with_the_seed() -> None:
    assert cases.load_anomaly_golden().seed_version == SEED_VERSION
    assert cases.load_contributor_golden().seed_version == SEED_VERSION


def test_fixture_bundle_is_self_consistent() -> None:
    bundle = cases.load_brief_guardrails().evidence_bundle()
    assert bundle.allowed_evidence_ids == ["ANOM-000001", "EVT-000001", "MTR-000001", "SEG-000001"]


def test_malformed_case_file_fails_loudly(tmp_path: Path) -> None:
    shutil.copytree(cases.CASES_DIR, tmp_path, dirs_exist_ok=True)
    path = tmp_path / "metric_fixtures.json"
    data = json.loads(path.read_text())
    data["cases"][0]["baseline"] = data["cases"][0]["baseline"][:3]  # not 7 days
    path.write_text(json.dumps(data))
    with pytest.raises(ValidationError):
        cases.load_metric_fixtures(tmp_path)
