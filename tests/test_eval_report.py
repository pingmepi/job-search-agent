"""Tests for evals/report.py — eval trend report generation.

Tests build_report() and format_markdown() against synthetic
eval_output.json fixtures in a temp directory.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from evals.report import build_report, format_markdown


def _write_eval(tmp: Path, run_id: str, overrides: dict | None = None) -> Path:
    """Write a synthetic eval_output.json to a temp run directory."""
    run_dir = tmp / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    base = {
        "run_id": run_id,
        "schema_version": "1.0",
        "created_at": "2026-03-05T06:49:24+00:00",
        "jd_hash": "abc123",
        "task_type": "inbox_apply",
        "task_outcome": "success",
        "error_types": [],
        "prompt_versions": ["resume_mutate:v3"],
        "models_used": ["openai/gpt-4o-mini"],
        "feedback_label": None,
        "feedback_reason": None,
        "eval_results": {
            "compile_success": True,
            "forbidden_claims_count": 0,
            "edit_scope_violations": 0,
            "draft_length_ok": True,
            "cost_ok": True,
            "keyword_coverage": 0.3,
            "compile_rollback_used": False,
            "condense_retries": 0,
            "llm_total_tokens": 5000,
            "llm_total_cost": 0.01,
            "jd_schema_valid": True,
            "soft_resume_relevance": 0.85,
            "soft_jd_accuracy": 0.92,
        },
    }

    if overrides:
        base["eval_results"].update(overrides)

    path = run_dir / "eval_output.json"
    path.write_text(json.dumps(base), encoding="utf-8")
    return path


class TestBuildReport:
    """Test the report builder against synthetic artifacts."""

    def test_empty_directory(self, tmp_path):
        """No artifacts → empty report."""
        report = build_report(tmp_path)
        assert report["runs"] == []
        assert report["summary"] == {}

    def test_single_passing_run(self, tmp_path):
        """Single passing run produces correct metrics."""
        _write_eval(tmp_path, "run-001")
        report = build_report(tmp_path)

        assert len(report["runs"]) == 1
        assert report["summary"]["total_runs"] == 1
        assert report["summary"]["compile_rate"] == 1.0
        assert report["summary"]["total_forbidden_claims"] == 0
        assert report["summary"]["avg_resume_relevance"] == pytest.approx(0.85)

    def test_multiple_runs_aggregation(self, tmp_path):
        """Multiple runs aggregate correctly."""
        _write_eval(tmp_path, "run-001", {"soft_resume_relevance": 0.80})
        _write_eval(tmp_path, "run-002", {"soft_resume_relevance": 0.60})
        _write_eval(tmp_path, "run-003", {
            "compile_success": False,
            "soft_resume_relevance": 0.90,
        })

        report = build_report(tmp_path)
        s = report["summary"]

        assert s["total_runs"] == 3
        assert s["compile_rate"] == pytest.approx(2 / 3)
        assert s["avg_resume_relevance"] == pytest.approx(
            (0.80 + 0.60 + 0.90) / 3
        )
        assert s["min_resume_relevance"] == pytest.approx(0.60)
        assert s["max_resume_relevance"] == pytest.approx(0.90)

    def test_forbidden_claims_summed(self, tmp_path):
        """Forbidden claims across runs should sum."""
        _write_eval(tmp_path, "run-001", {"forbidden_claims_count": 2})
        _write_eval(tmp_path, "run-002", {"forbidden_claims_count": 1})

        report = build_report(tmp_path)
        assert report["summary"]["total_forbidden_claims"] == 3

    def test_error_types_handle_arrays_and_null(self, tmp_path):
        _write_eval(tmp_path, "run-none", {})
        _write_eval(tmp_path, "run-null", {})
        _write_eval(tmp_path, "run-timeout", {})

        run_null = tmp_path / "run-null" / "eval_output.json"
        payload_null = json.loads(run_null.read_text(encoding="utf-8"))
        payload_null["error_types"] = None
        run_null.write_text(json.dumps(payload_null), encoding="utf-8")

        run_timeout = tmp_path / "run-timeout" / "eval_output.json"
        payload_timeout = json.loads(run_timeout.read_text(encoding="utf-8"))
        payload_timeout["error_types"] = ["tool_timeout", "tool_timeout"]
        run_timeout.write_text(json.dumps(payload_timeout), encoding="utf-8")

        report = build_report(tmp_path)
        assert report["summary"]["no_error_runs"] == 1
        assert report["summary"]["null_error_type_runs"] == 1
        assert report["summary"]["error_type_counts"]["tool_timeout"] == 2

    def test_feedback_counts_aggregated(self, tmp_path):
        _write_eval(tmp_path, "run-helpful", {})
        _write_eval(tmp_path, "run-bad", {})

        helpful = tmp_path / "run-helpful" / "eval_output.json"
        helpful_payload = json.loads(helpful.read_text(encoding="utf-8"))
        helpful_payload["feedback_label"] = "helpful"
        helpful.write_text(json.dumps(helpful_payload), encoding="utf-8")

        bad = tmp_path / "run-bad" / "eval_output.json"
        bad_payload = json.loads(bad.read_text(encoding="utf-8"))
        bad_payload["feedback_label"] = "not_helpful"
        bad_payload["task_outcome"] = "partial"
        bad.write_text(json.dumps(bad_payload), encoding="utf-8")

        report = build_report(tmp_path)
        assert report["summary"]["helpful_count"] == 1
        assert report["summary"]["not_helpful_count"] == 1
        assert report["summary"]["partial_count"] == 1

    def test_malformed_json_skipped(self, tmp_path):
        """Malformed JSON files should be silently skipped."""
        run_dir = tmp_path / "run-bad"
        run_dir.mkdir()
        (run_dir / "eval_output.json").write_text("not json", encoding="utf-8")

        _write_eval(tmp_path, "run-good")

        report = build_report(tmp_path)
        assert len(report["runs"]) == 1


class TestFormatMarkdown:
    """Test the markdown formatter."""

    def test_empty_report_message(self):
        """Empty report should show warning."""
        md = format_markdown({"runs": [], "summary": {}})
        assert "No eval artifacts" in md

    def test_headers_present(self, tmp_path):
        """Markdown output should contain expected headers."""
        _write_eval(tmp_path, "run-001")
        report = build_report(tmp_path)
        md = format_markdown(report)

        assert "# Eval Trend Report" in md
        assert "## Summary" in md
        assert "## Per-Run Detail" in md

    def test_run_id_in_table(self, tmp_path):
        """Each run ID should appear in the per-run table."""
        _write_eval(tmp_path, "run-alpha")
        _write_eval(tmp_path, "run-beta")
        report = build_report(tmp_path)
        md = format_markdown(report)

        assert "run-alpha" in md
        assert "run-beta" in md

    def test_status_icons(self, tmp_path):
        """Compile success/failure should show correct icons."""
        _write_eval(tmp_path, "run-pass", {"compile_success": True})
        _write_eval(tmp_path, "run-fail", {"compile_success": False})
        report = build_report(tmp_path)
        md = format_markdown(report)

        # At least one ✅ and one ❌ should be present
        assert "✅" in md
        assert "❌" in md

    def test_error_array_and_null_rendered(self, tmp_path):
        _write_eval(tmp_path, "run-null")
        _write_eval(tmp_path, "run-array")
        report_path_null = tmp_path / "run-null" / "eval_output.json"
        payload_null = json.loads(report_path_null.read_text(encoding="utf-8"))
        payload_null["error_types"] = None
        report_path_null.write_text(json.dumps(payload_null), encoding="utf-8")

        report_path_array = tmp_path / "run-array" / "eval_output.json"
        payload_array = json.loads(report_path_array.read_text(encoding="utf-8"))
        payload_array["error_types"] = ["parse_error", "missing_context"]
        report_path_array.write_text(json.dumps(payload_array), encoding="utf-8")

        report = build_report(tmp_path)
        md = format_markdown(report)
        assert "null" in md
        assert "parse_error, missing_context" in md
