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
