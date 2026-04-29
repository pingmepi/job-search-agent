from __future__ import annotations

import json

from core.db import complete_run, get_run, insert_run
from evals.feedback_report import annotate_run_feedback, build_feedback_report


def test_annotate_run_feedback_updates_db(db, monkeypatch, tmp_path):
    insert_run("run-feedback", "inbox")
    complete_run(
        "run-feedback",
        status="completed",
        eval_results={"compile_success": True},
        task_type="inbox_apply",
        task_outcome="success",
        error_types=[],
    )

    class _Settings:
        runs_dir = tmp_path

    artifact_dir = tmp_path / "artifacts" / "run-feedback"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = artifact_dir / "eval_output.json"
    artifact_path.write_text(
        json.dumps(
            {
                "run_id": "run-feedback",
                "schema_version": "1.0",
                "created_at": "2026-01-01T00:00:00+00:00",
                "jd_hash": "abc",
                "task_type": "inbox_apply",
                "task_outcome": "success",
                "error_types": [],
                "eval_results": {"compile_success": True},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("evals.feedback_report.get_settings", lambda: _Settings())

    annotate_run_feedback("run-feedback", feedback_label="not_helpful", feedback_reason="wrong")

    run = get_run("run-feedback")
    assert run is not None
    assert run["feedback_label"] == "not_helpful"
    assert run["feedback_reason"] == "wrong"

    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert payload["feedback_label"] == "not_helpful"
    assert payload["feedback_reason"] == "wrong"


def test_build_feedback_report_counts_multi_error_runs(db):
    insert_run("run-a", "inbox")
    complete_run(
        "run-a",
        status="completed",
        eval_results={"compile_success": True},
        task_type="inbox_apply",
        task_outcome="partial",
        error_types=["tool_timeout", "parse_error"],
        prompt_versions=["resume_mutate:v3"],
        models_used=["openai/gpt-4o-mini"],
    )
    insert_run("run-b", "inbox")
    complete_run(
        "run-b",
        status="completed",
        eval_results={"compile_success": True},
        task_type="inbox_apply",
        task_outcome="success",
        error_types=[],
    )
    insert_run("run-c", "inbox")
    complete_run(
        "run-c",
        status="completed",
        eval_results={"compile_success": False},
        task_type="followup",
        task_outcome="fail",
        error_types=None,
    )

    report = build_feedback_report(days=30)
    assert report["total_runs"] >= 3
    assert report["outcomes"]["partial"] >= 1
    assert report["outcomes"]["success"] >= 1
    assert report["outcomes"]["fail"] >= 1
    assert ("tool_timeout", 1) in report["top_error_types"]
    assert ("parse_error", 1) in report["top_error_types"]
    assert report["no_error_runs"] >= 1
    assert report["null_error_type_runs"] >= 1
