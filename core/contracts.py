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

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EvalOutputArtifact:
    run_id: str
    schema_version: str
    created_at: str
    jd_hash: str
    eval_results: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_job_extraction_artifact(*, run_id: str, input_mode: str, jd_hash: str, jd: dict[str, Any]) -> JobExtractionArtifact:
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
) -> ResumeOutputArtifact:
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
    )


def build_eval_output_artifact(
    *,
    run_id: str,
    jd_hash: str,
    eval_results: dict[str, Any],
) -> EvalOutputArtifact:
    return EvalOutputArtifact(
        run_id=_ensure_non_empty(run_id, "run_id"),
        schema_version=SCHEMA_VERSION,
        created_at=_now_iso(),
        jd_hash=_ensure_non_empty(jd_hash, "jd_hash"),
        eval_results=eval_results,
    )
