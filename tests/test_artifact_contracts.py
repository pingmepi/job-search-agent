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
        report_md_path="/tmp/out/application_report.md",
        application_context_id="acme_pm_abc123",
        application_output_dir="/tmp/out",
        selected_collateral=["email"],
        generated_collateral=["email"],
        collateral_generation_status="generated",
        collateral_generation_reason=None,
        collateral_files={"email": "/tmp/out/email_draft.txt", "linkedin": None, "referral": None},
        drive_uploads={"files": {"resume_pdf": {"status": "uploaded"}}},
        single_page_target_met=True,
        single_page_status="met",
        compile_outcome="mutated_success",
        fit_score_details={"selected_resume": "master_ai.tex"},
        mutation_summary={"mutations_count": 1},
    )
    eval_output = build_eval_output_artifact(
        run_id="run-1",
        jd_hash="abc",
        task_type="inbox_apply",
        task_outcome="success",
        error_types=[],
        prompt_versions=["resume_mutate:v3"],
        models_used=["openai/gpt-4o-mini"],
        eval_results={"compile_success": True},
    )

    assert resume.schema_version == SCHEMA_VERSION
    assert resume.single_page_target_met is True
    assert resume.compile_outcome == "mutated_success"
    assert resume.report_md_path == "/tmp/out/application_report.md"
    assert resume.mutation_summary["mutations_count"] == 1
    assert resume.application_context_id == "acme_pm_abc123"
    assert resume.collateral_files["email"] == "/tmp/out/email_draft.txt"
    assert resume.collateral_files["linkedin"] is None
    assert resume.fit_score_details["selected_resume"] == "master_ai.tex"
    assert eval_output.schema_version == SCHEMA_VERSION
    assert eval_output.task_outcome == "success"
    assert eval_output.error_types == []
    assert eval_output.prompt_versions == ["resume_mutate:v3"]


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


def test_build_resume_artifact_rejects_unknown_collateral_keys() -> None:
    with pytest.raises(ValueError):
        build_resume_output_artifact(
            run_id="run-1",
            jd_hash="abc",
            resume_base="master_ai.tex",
            fit_score=80,
            compile_success=True,
            compile_rollback_used=False,
            condense_retries=0,
            pdf_path="/tmp/r.pdf",
            output_dir="/tmp/out",
            collateral_files={"cover_letter": "/tmp/out/cover_letter.txt"},
        )


def test_write_json_artifact_uses_run_scoped_folder(tmp_path: Path) -> None:
    payload = {"run_id": "run-abc", "schema_version": SCHEMA_VERSION}
    path = write_json_artifact("run-abc", "job_extraction.json", payload, base_dir=tmp_path)

    assert path == tmp_path / "run-abc" / "job_extraction.json"
    assert path.exists()
    assert json.loads(path.read_text(encoding="utf-8"))["schema_version"] == SCHEMA_VERSION
