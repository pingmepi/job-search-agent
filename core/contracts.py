"""Canonical JSON artifact contracts for pipeline outputs."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION = "1.0"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_non_empty(value: str, field_name: str) -> str:
    normalized = (value or "").strip()
    if not normalized:
        raise ValueError(f"{field_name} must be non-empty")
    return normalized


@dataclass
class JobExtractionArtifact:
    run_id: str
    schema_version: str
    created_at: str
    input_mode: str
    jd_hash: str
    company: str
    role: str
    location: str
    experience_required: str
    skills: list[str]
    description: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ResumeOutputArtifact:
    run_id: str
    schema_version: str
    created_at: str
    jd_hash: str
    resume_base: str
    fit_score: int
    compile_success: bool
    compile_rollback_used: bool
    condense_retries: int
    pdf_path: str | None
    output_dir: str | None
    report_md_path: str | None
    application_context_id: str | None
    application_output_dir: str | None
    selected_collateral: list[str]
    generated_collateral: list[str]
    collateral_generation_status: str
    collateral_generation_reason: str | None
    collateral_files: dict[str, str | None]
    drive_uploads: dict[str, Any]
    single_page_target_met: bool
    single_page_status: str
    compile_outcome: str | None
    fit_score_details: dict[str, Any]
    mutation_summary: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EvalOutputArtifact:
    run_id: str
    schema_version: str
    created_at: str
    jd_hash: str
    task_type: str | None
    task_outcome: str | None
    error_types: list[str] | None
    prompt_versions: list[str] | None
    models_used: list[str] | None
    feedback_label: str | None
    feedback_reason: str | None
    eval_results: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_job_extraction_artifact(
    *, run_id: str, input_mode: str, jd_hash: str, jd: dict[str, Any]
) -> JobExtractionArtifact:
    return JobExtractionArtifact(
        run_id=_ensure_non_empty(run_id, "run_id"),
        schema_version=SCHEMA_VERSION,
        created_at=_now_iso(),
        input_mode=_ensure_non_empty(input_mode, "input_mode"),
        jd_hash=_ensure_non_empty(jd_hash, "jd_hash"),
        company=_ensure_non_empty(str(jd.get("company", "")), "company"),
        role=_ensure_non_empty(str(jd.get("role", "")), "role"),
        location=str(jd.get("location", "")).strip(),
        experience_required=str(jd.get("experience_required", "")).strip(),
        skills=[str(skill).strip() for skill in jd.get("skills", []) if str(skill).strip()],
        description=str(jd.get("description", "")).strip(),
    )


def build_resume_output_artifact(
    *,
    run_id: str,
    jd_hash: str,
    resume_base: str,
    fit_score: int,
    compile_success: bool,
    compile_rollback_used: bool,
    condense_retries: int,
    pdf_path: str | None,
    output_dir: str | None,
    report_md_path: str | None = None,
    application_context_id: str | None = None,
    application_output_dir: str | None = None,
    selected_collateral: list[str] | None = None,
    generated_collateral: list[str] | None = None,
    collateral_generation_status: str = "not_requested",
    collateral_generation_reason: str | None = None,
    collateral_files: dict[str, str | None] | None = None,
    drive_uploads: dict[str, Any] | None = None,
    single_page_target_met: bool = False,
    single_page_status: str = "unknown",
    compile_outcome: str | None = None,
    fit_score_details: dict[str, Any] | None = None,
    mutation_summary: dict[str, Any] | None = None,
) -> ResumeOutputArtifact:
    if compile_outcome is not None and compile_outcome not in {
        "mutated_success",
        "fallback_success",
    }:
        raise ValueError(
            "compile_outcome must be one of mutated_success, fallback_success, or None"
        )
    allowed_keys = {"email", "linkedin", "referral"}
    normalized_collateral_files = collateral_files or {}
    unknown_keys = set(normalized_collateral_files) - allowed_keys
    if unknown_keys:
        raise ValueError("collateral_files contains unknown keys")
    return ResumeOutputArtifact(
        run_id=_ensure_non_empty(run_id, "run_id"),
        schema_version=SCHEMA_VERSION,
        created_at=_now_iso(),
        jd_hash=_ensure_non_empty(jd_hash, "jd_hash"),
        resume_base=_ensure_non_empty(resume_base, "resume_base"),
        fit_score=int(fit_score),
        compile_success=bool(compile_success),
        compile_rollback_used=bool(compile_rollback_used),
        condense_retries=int(condense_retries),
        pdf_path=pdf_path,
        output_dir=output_dir,
        report_md_path=report_md_path,
        application_context_id=application_context_id,
        application_output_dir=application_output_dir or output_dir,
        selected_collateral=selected_collateral or [],
        generated_collateral=generated_collateral or [],
        collateral_generation_status=_ensure_non_empty(
            collateral_generation_status, "collateral_generation_status"
        ),
        collateral_generation_reason=collateral_generation_reason,
        collateral_files={
            "email": normalized_collateral_files.get("email"),
            "linkedin": normalized_collateral_files.get("linkedin"),
            "referral": normalized_collateral_files.get("referral"),
        },
        drive_uploads=drive_uploads or {},
        single_page_target_met=bool(single_page_target_met),
        single_page_status=_ensure_non_empty(single_page_status, "single_page_status"),
        compile_outcome=compile_outcome,
        fit_score_details=fit_score_details or {},
        mutation_summary=mutation_summary or {},
    )


def build_eval_output_artifact(
    *,
    run_id: str,
    jd_hash: str,
    eval_results: dict[str, Any],
    task_type: str | None = None,
    task_outcome: str | None = None,
    error_types: list[str] | None = None,
    prompt_versions: list[str] | None = None,
    models_used: list[str] | None = None,
    feedback_label: str | None = None,
    feedback_reason: str | None = None,
) -> EvalOutputArtifact:
    return EvalOutputArtifact(
        run_id=_ensure_non_empty(run_id, "run_id"),
        schema_version=SCHEMA_VERSION,
        created_at=_now_iso(),
        jd_hash=_ensure_non_empty(jd_hash, "jd_hash"),
        task_type=task_type,
        task_outcome=task_outcome,
        error_types=error_types,
        prompt_versions=prompt_versions,
        models_used=models_used,
        feedback_label=feedback_label,
        feedback_reason=feedback_reason,
        eval_results=eval_results,
    )
