from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path

from core.pipeline_checks import run_pipeline_checks


class _FakeCursor:
    def __init__(self, one_results, all_results):
        self._one_results = list(one_results)
        self._all_results = list(all_results)

    def execute(self, _query, _params=None):
        return None

    def fetchone(self):
        if not self._one_results:
            return {}
        return self._one_results.pop(0)

    def fetchall(self):
        if not self._all_results:
            return []
        return self._all_results.pop(0)


class _FakeConn:
    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self):
        return self._cursor


def test_run_pipeline_checks_passes_with_valid_artifacts(monkeypatch, tmp_path: Path) -> None:
    report_path = tmp_path / "application_report.md"
    report_path.write_text("# Report\n", encoding="utf-8")
    resume_artifact_path = tmp_path / "resume_output.json"
    resume_artifact_path.write_text(
        json.dumps({"report_md_path": str(report_path)}),
        encoding="utf-8",
    )
    context_json = json.dumps({"artifact_paths": {"resume_output": str(resume_artifact_path)}})

    cursor = _FakeCursor(
        one_results=[
            {"cnt": 0},  # missing required jobs
            {"dup_groups": 0},  # duplicates
            {"cnt": 0},  # completed runs with errors
            {"cnt": 0},  # completed runs without eval
            {"cnt": 0},  # fit_score out of range
            {"cnt": 0},  # missing drive links
            {"cnt": 0},  # missing calendar ids
        ],
        all_results=[
            [{"run_id": "run-1", "context_json": context_json}],
        ],
    )

    @contextmanager
    def _fake_get_conn():
        yield _FakeConn(cursor)

    monkeypatch.setattr("core.pipeline_checks.get_conn", _fake_get_conn)
    monkeypatch.setattr("core.pipeline_checks.get_jobs_needing_followup", lambda: [])

    result = run_pipeline_checks()

    assert result["ok"] is True
    assert result["errors"] == []
    assert result["stats"]["checked_resume_artifacts"] == 1
    assert result["stats"]["missing_report_files"] == 0


def test_run_pipeline_checks_flags_missing_report(monkeypatch, tmp_path: Path) -> None:
    missing_path = tmp_path / "missing_resume_output.json"
    context_json = json.dumps({"artifact_paths": {"resume_output": str(missing_path)}})
    cursor = _FakeCursor(
        one_results=[
            {"cnt": 0},
            {"dup_groups": 0},
            {"cnt": 0},
            {"cnt": 0},
            {"cnt": 0},
            {"cnt": 0},
            {"cnt": 0},
        ],
        all_results=[
            [{"run_id": "run-2", "context_json": context_json}],
        ],
    )

    @contextmanager
    def _fake_get_conn():
        yield _FakeConn(cursor)

    monkeypatch.setattr("core.pipeline_checks.get_conn", _fake_get_conn)
    monkeypatch.setattr("core.pipeline_checks.get_jobs_needing_followup", lambda: [])

    result = run_pipeline_checks()

    assert result["ok"] is False
    assert any("resume_output artifacts are missing" in msg for msg in result["errors"])
