from __future__ import annotations

from evals.regression_dataset import get_regression_cases
from evals.regression_runner import format_regression_report, run_regression


def test_dataset_has_minimum_cases():
    cases = get_regression_cases()
    assert len(cases) >= 8
    assert len({c["id"] for c in cases}) == len(cases)
    for case in cases:
        assert "expected" in case
        assert case["input_mode"] in {"text", "image"}


def test_run_regression_with_mock_executor_passes():
    def _executor(case):
        # Pick the first allowed outcome from the case so the mock satisfies
        # each case's expected task_outcome_in (e.g. out_of_scope cases).
        allowed = case.get("expected", {}).get("task_outcome_in") or ["success"]
        outcome = allowed[0]
        compile_success = bool(case.get("expected", {}).get("compile_success", True))
        return {
            "run_id": f"run-{case['id']}",
            "pack_eval_results": {
                "compile_success": compile_success,
                "forbidden_claims_count": 0,
                "edit_scope_violations": 0,
                "keyword_coverage": 0.8,
                "soft_resume_relevance": 0.8,
            },
            "pack_errors": [],
            "db_run": {
                "task_outcome": outcome,
                "error_types": [],
                "eval_results": {
                    "compile_success": compile_success,
                    "forbidden_claims_count": 0,
                    "edit_scope_violations": 0,
                    "keyword_coverage": 0.8,
                    "soft_resume_relevance": 0.8,
                },
            },
        }

    report = run_regression(executor=_executor)
    assert report["total_cases"] >= 8
    assert report["failed"] == 0


def test_run_regression_case_filter():
    def _executor(case):
        return {
            "run_id": "run-1",
            "pack_eval_results": {
                "compile_success": True,
                "forbidden_claims_count": 0,
                "edit_scope_violations": 0,
            },
            "pack_errors": [],
            "db_run": {
                "task_outcome": "partial",
                "error_types": [],
                "eval_results": {
                    "compile_success": True,
                    "forbidden_claims_count": 0,
                    "edit_scope_violations": 0,
                },
            },
        }

    report = run_regression(case_id="edge_sparse_jd", executor=_executor)
    assert report["total_cases"] == 1
    assert report["results"][0]["id"] == "edge_sparse_jd"


def test_run_regression_assertion_failure_surface():
    def _executor(case):
        return {
            "run_id": "run-fail",
            "pack_eval_results": {
                "compile_success": False,
                "forbidden_claims_count": 2,
                "edit_scope_violations": 1,
                "keyword_coverage": 0.1,
            },
            "pack_errors": ["bad output"],
            "db_run": {
                "task_outcome": "fail",
                "error_types": ["bad_reasoning"],
                "eval_results": {
                    "compile_success": False,
                    "forbidden_claims_count": 2,
                    "edit_scope_violations": 1,
                    "keyword_coverage": 0.1,
                },
            },
        }

    report = run_regression(case_id="text_ai_pm_core", executor=_executor)
    assert report["failed"] == 1
    assert report["results"][0]["passed"] is False
    assert any("compile_success" in msg for msg in report["results"][0]["failures"])


def test_run_regression_soft_relevance_floor_failure():
    def _executor(case):
        return {
            "run_id": "run-soft-fail",
            "pack_eval_results": {
                "compile_success": True,
                "forbidden_claims_count": 0,
                "edit_scope_violations": 0,
                "keyword_coverage": 0.8,
                "soft_resume_relevance": 0.2,
            },
            "pack_errors": [],
            "db_run": {
                "task_outcome": "partial",
                "error_types": [],
                "eval_results": {
                    "compile_success": True,
                    "forbidden_claims_count": 0,
                    "edit_scope_violations": 0,
                    "keyword_coverage": 0.8,
                    "soft_resume_relevance": 0.2,
                },
            },
        }

    report = run_regression(case_id="text_ai_pm_core", executor=_executor)
    assert report["failed"] == 1
    assert report["results"][0]["passed"] is False
    assert any("soft_resume_relevance" in msg for msg in report["results"][0]["failures"])


def test_format_regression_report_renders_error_cells():
    report = {
        "suite": "inbox_regression_v1",
        "total_cases": 2,
        "passed": 1,
        "failed": 1,
        "duration_ms": 100,
        "results": [
            {
                "id": "a",
                "passed": True,
                "task_outcome": "success",
                "error_types": [],
                "failures": [],
            },
            {
                "id": "b",
                "passed": False,
                "task_outcome": None,
                "error_types": None,
                "failures": ["execution_error: boom"],
            },
        ],
    }
    output = format_regression_report(report)
    assert "| `a` | PASS | success | [] |" in output
    assert "| `b` | FAIL | - | null |" in output
    assert "execution_error: boom" in output


def test_run_regression_preflight_for_missing_runtime_env(monkeypatch):
    class _Settings:
        database_url = ""
        openrouter_api_key = ""

    monkeypatch.setattr("evals.regression_runner.get_settings", lambda: _Settings())
    monkeypatch.setattr(
        "evals.regression_runner._pipeline_executor",
        lambda _case: (_ for _ in ()).throw(RuntimeError("should not run")),
    )

    report = run_regression(case_id="text_ai_pm_core")

    assert report["total_cases"] == 1
    assert report["failed"] == 1
    assert report["results"][0]["passed"] is False
    assert report["results"][0]["run_id"] is None
    assert any("preflight_error:" in msg for msg in report["results"][0]["failures"])
    assert any("DATABASE_URL" in msg for msg in report["results"][0]["failures"])
    assert any("OPENROUTER_API_KEY" in msg for msg in report["results"][0]["failures"])
