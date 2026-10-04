"""``GET /api/evaluations/latest`` and the ``python -m app.evals.run`` CLI."""

import json
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from app.api.routes.evaluations import get_evaluation_service
from app.evals import run as run_module
from app.evals.report import build_report
from app.evals.run import EXIT_INCOMPLETE, EXIT_REFUSED, main
from app.evals.store import write_report
from app.main import app
from app.schemas.evaluations import CaseResult, EvalCategory, ModelBasedSection, SeedInfo
from app.services.evaluations.service import EvaluationReportService
from tests.evals.conftest import eval_settings


@pytest.fixture
def reports_dir(tmp_path: Path) -> Iterator[Path]:
    app.dependency_overrides[get_evaluation_service] = lambda: EvaluationReportService(tmp_path)
    yield tmp_path
    app.dependency_overrides.pop(get_evaluation_service, None)


@pytest.fixture
def api(reports_dir: Path) -> Iterator[TestClient]:
    with TestClient(app) as client:
        yield client


def sample_report() -> object:
    return build_report(
        suite="all",
        generated_at=datetime(2026, 10, 4, 6, tzinfo=UTC),
        seed=SeedInfo(
            expected_version="1",
            case_version="1",
            observed_state="complete",
            observed_version="1",
            matches=True,
        ),
        cases=[
            CaseResult(
                case_id="citation.fabricated_id",
                title="Fabricated citation",
                category=EvalCategory.CITATION_VALIDITY,
                status="fail",
                expected="brief invalid",
                observed="brief valid",
                failure_reason="status valid, expected invalid",
            )
        ],
        replay=None,
        model_based=ModelBasedSection(status="not_run", reason="disabled"),
    )


def test_no_report_returns_explicit_not_run(api: TestClient) -> None:
    response = api.get("/api/evaluations/latest")
    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "not_run" and body["report"] is None
    assert "python -m app.evals.run" in body["message"]


def test_available_report_is_returned_typed(api: TestClient, reports_dir: Path) -> None:
    write_report(reports_dir, sample_report())  # type: ignore[arg-type]
    body = api.get("/api/evaluations/latest").json()
    assert body["state"] == "available"
    report = body["report"]
    assert report["overall_status"] == "fail"
    assert report["cases"][0]["failure_reason"] == "status valid, expected invalid"
    assert report["model_based"] == {
        "label": "model_based",
        "status": "not_run",
        "reason": "disabled",
        "model_name": None,
        "prompt_version": None,
        "cases": [],
    }
    citation = next(r for r in report["ratios"] if r["key"] == "citation_validity_rate")
    assert citation["value"] == 0.0 and citation["denominator"] == 1
    metric = next(r for r in report["ratios"] if r["key"] == "metric_fixture_pass_rate")
    assert metric["value"] is None


def test_corrupt_report_is_a_typed_500(api: TestClient, reports_dir: Path) -> None:
    (reports_dir / "latest.json").write_text(json.dumps({"schema_version": 1}))
    response = api.get("/api/evaluations/latest")
    assert response.status_code == 500
    assert response.json()["code"] == "EVAL_REPORT_INVALID"


def test_cli_refuses_outside_demo_environments(tmp_path: Path) -> None:
    code = main(["--reports-dir", str(tmp_path)], settings=eval_settings(environment="production"))
    assert code == EXIT_REFUSED
    assert not (tmp_path / "latest.json").exists()


def test_cli_with_unreachable_database_reports_not_run_and_exits_incomplete(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    dead = create_engine("postgresql+psycopg://nobody:nothing@127.0.0.1:1/none")
    code = main(["--suite", "all", "--reports-dir", str(tmp_path)], eval_settings(), dead)
    assert code == EXIT_INCOMPLETE
    report = json.loads((tmp_path / "latest.json").read_text())
    assert report["overall_status"] == "incomplete"
    assert report["seed"]["observed_state"] == "unavailable"
    db_cases = [c for c in report["cases"] if c["category"] == "approval_boundary"]
    assert db_cases and {c["status"] for c in db_cases} == {"not_run"}
    offline = [c for c in report["cases"] if c["category"] == "metric_correctness"]
    assert offline and {c["status"] for c in offline} == {"pass"}
    assert report["replay"]["status"] == "not_run"
    assert report["model_based"]["status"] == "not_run"
    assert (tmp_path / "latest.md").exists()
    assert "INCOMPLETE" in capsys.readouterr().out


def test_cli_suite_selection_and_no_markdown(tmp_path: Path) -> None:
    dead = create_engine("postgresql+psycopg://nobody:nothing@127.0.0.1:1/none")
    main(["--suite", "ai", "--no-markdown", "--reports-dir", str(tmp_path)], eval_settings(), dead)
    report = json.loads((tmp_path / "latest.json").read_text())
    assert report["suite"] == "ai" and report["replay"] is None
    assert {c["category"] for c in report["cases"]} == {
        "citation_validity",
        "causal_guardrail",
        "action_grounding",
    }
    assert report["overall_status"] == "pass"
    assert not (tmp_path / "latest.md").exists()


def test_cli_rejects_out_of_range_replay_days() -> None:
    with pytest.raises(SystemExit):
        run_module._parser().parse_args(["--replay-days", "0"])
