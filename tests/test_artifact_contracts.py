"""Tests for canonical artifact contracts and persistence."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.artifacts import write_json_artifact
from core.contracts import (
    SCHEMA_VERSION,
    build_eval_output_artifact,
    build_job_extraction_artifact,
    build_resume_output_artifact,
)


def test_build_job_extraction_artifact_requires_company() -> None:
    with pytest.raises(ValueError):
        build_job_extraction_artifact(
            run_id="run-1",
            input_mode="text",
            jd_hash="abc",
            jd={"company": "", "role": "PM", "skills": []},
        )


def test_build_resume_and_eval_artifacts_include_schema_version() -> None:
    resume = build_resume_output_artifact(
        run_id="run-1",
        jd_hash="abc",
        resume_base="master_ai.tex",
        fit_score=80,
        compile_success=True,
        compile_rollback_used=False,
        condense_retries=0,
        pdf_path="/tmp/r.pdf",
        output_dir="/tmp/out",
        single_page_target_met=True,
        single_page_status="met",
        compile_outcome="mutated_success",
        fit_score_details={"selected_resume": "master_ai.tex"},
    )
    eval_output = build_eval_output_artifact(
        run_id="run-1",
        jd_hash="abc",
        eval_results={"compile_success": True},
    )

    assert resume.schema_version == SCHEMA_VERSION
    assert resume.single_page_target_met is True
    assert resume.compile_outcome == "mutated_success"
    assert resume.fit_score_details["selected_resume"] == "master_ai.tex"
    assert eval_output.schema_version == SCHEMA_VERSION


def test_build_resume_artifact_rejects_invalid_compile_outcome() -> None:
    with pytest.raises(ValueError):
        build_resume_output_artifact(
            run_id="run-1",
            jd_hash="abc",
            resume_base="master_ai.tex",
            fit_score=80,
            compile_success=False,
            compile_rollback_used=True,
            condense_retries=2,
            pdf_path=None,
            output_dir=None,
            compile_outcome="compile_failed",
        )


def test_write_json_artifact_uses_run_scoped_folder(tmp_path: Path) -> None:
    payload = {"run_id": "run-abc", "schema_version": SCHEMA_VERSION}
    path = write_json_artifact("run-abc", "job_extraction.json", payload, base_dir=tmp_path)

    assert path == tmp_path / "run-abc" / "job_extraction.json"
    assert path.exists()
    assert json.loads(path.read_text(encoding="utf-8"))["schema_version"] == SCHEMA_VERSION
