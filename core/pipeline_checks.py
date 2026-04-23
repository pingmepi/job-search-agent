"""Pipeline integrity checks over DB state and artifact files."""

from __future__ import annotations

import json
import os
from typing import Any

from core.db import get_conn, get_jobs_needing_followup


def _load_json(path: str) -> dict[str, Any] | None:
    if not path or not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except Exception:
        return None
    return None


def run_pipeline_checks(*, run_limit: int = 500) -> dict[str, Any]:
    """
    Validate pipeline consistency and artifact integrity.

    Returns a dict with:
    - errors: list[str]
    - warnings: list[str]
    - stats: dict[str, int]
    """
    errors: list[str] = []
    warnings: list[str] = []
    stats: dict[str, int] = {}

    with get_conn() as conn:
        cur = conn.cursor()

        cur.execute(
            """
            SELECT COUNT(*) AS cnt
            FROM jobs
            WHERE COALESCE(TRIM(company), '') = ''
               OR COALESCE(TRIM(role), '') = ''
               OR COALESCE(TRIM(jd_hash), '') = ''
            """
        )
        missing_required_jobs = int((cur.fetchone() or {}).get("cnt", 0))
        stats["missing_required_jobs"] = missing_required_jobs
        if missing_required_jobs:
            errors.append(f"{missing_required_jobs} jobs have missing company/role/jd_hash.")

        cur.execute(
            """
            SELECT COUNT(*) AS dup_groups
            FROM (
              SELECT LOWER(TRIM(company)) AS c, LOWER(TRIM(role)) AS r, jd_hash, COUNT(*) AS n
              FROM jobs
              GROUP BY LOWER(TRIM(company)), LOWER(TRIM(role)), jd_hash
              HAVING COUNT(*) > 1
            ) x
            """
        )
        duplicate_job_groups = int((cur.fetchone() or {}).get("dup_groups", 0))
        stats["duplicate_job_groups"] = duplicate_job_groups
        if duplicate_job_groups:
            errors.append(f"{duplicate_job_groups} duplicate job groups found.")

        cur.execute(
            "SELECT COUNT(*) AS cnt FROM runs WHERE status = 'completed' AND COALESCE(error_count, 0) > 0"
        )
        completed_with_errors = int((cur.fetchone() or {}).get("cnt", 0))
        stats["completed_runs_with_errors"] = completed_with_errors
        if completed_with_errors:
            warnings.append(f"{completed_with_errors} completed runs have non-zero errors.")

        cur.execute(
            "SELECT COUNT(*) AS cnt FROM runs WHERE status = 'completed' AND eval_results IS NULL"
        )
        completed_without_eval = int((cur.fetchone() or {}).get("cnt", 0))
        stats["completed_runs_without_eval"] = completed_without_eval
        if completed_without_eval:
            errors.append(f"{completed_without_eval} completed runs are missing eval_results.")

        cur.execute(
            """
            SELECT COUNT(*) AS cnt
            FROM jobs
            WHERE fit_score IS NOT NULL
              AND (fit_score < 0 OR fit_score > 100)
            """
        )
        out_of_range_fit_scores = int((cur.fetchone() or {}).get("cnt", 0))
        stats["out_of_range_fit_scores"] = out_of_range_fit_scores
        if out_of_range_fit_scores:
            errors.append(f"{out_of_range_fit_scores} jobs have fit_score outside 0-100.")

        cur.execute(
            """
            SELECT COUNT(*) AS cnt
            FROM runs r
            JOIN jobs j ON j.id = r.job_id
            WHERE r.status = 'completed'
              AND COALESCE(r.skip_upload, 0) = 0
              AND COALESCE(TRIM(j.drive_link), '') = ''
            """
        )
        missing_drive_links = int((cur.fetchone() or {}).get("cnt", 0))
        stats["missing_drive_links"] = missing_drive_links
        if missing_drive_links:
            warnings.append(
                f"{missing_drive_links} completed uploaded runs have missing drive links on jobs."
            )

        cur.execute(
            """
            SELECT COUNT(*) AS cnt
            FROM runs r
            JOIN jobs j ON j.id = r.job_id
            WHERE r.status = 'completed'
              AND COALESCE(r.skip_calendar, 0) = 0
              AND (
                COALESCE(TRIM(j.calendar_apply_event_id), '') = ''
                OR COALESCE(TRIM(j.calendar_followup_event_id), '') = ''
              )
            """
        )
        missing_calendar_ids = int((cur.fetchone() or {}).get("cnt", 0))
        stats["missing_calendar_ids"] = missing_calendar_ids
        if missing_calendar_ids:
            warnings.append(
                f"{missing_calendar_ids} calendar-enabled runs are missing calendar event ids."
            )

        cur.execute(
            """
            SELECT run_id, context_json
            FROM runs
            WHERE status = 'completed'
              AND context_json IS NOT NULL
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (run_limit,),
        )
        rows = cur.fetchall() or []

    missing_resume_artifacts = 0
    missing_report_paths = 0
    missing_report_files = 0
    checked_resume_artifacts = 0

    for row in rows:
        run_id = row.get("run_id")
        context_json = row.get("context_json")
        if not context_json:
            continue
        try:
            context = json.loads(context_json)
        except Exception:
            warnings.append(f"Run {run_id}: invalid context_json payload.")
            continue
        if not isinstance(context, dict):
            continue
        artifact_paths = context.get("artifact_paths") or {}
        if not isinstance(artifact_paths, dict):
            continue
        resume_artifact_path = artifact_paths.get("resume_output")
        if not resume_artifact_path:
            continue
        checked_resume_artifacts += 1
        resume_artifact = _load_json(str(resume_artifact_path))
        if resume_artifact is None:
            missing_resume_artifacts += 1
            continue
        report_md_path = resume_artifact.get("report_md_path")
        if not report_md_path:
            missing_report_paths += 1
            continue
        if not os.path.exists(str(report_md_path)):
            missing_report_files += 1

    stats["checked_resume_artifacts"] = checked_resume_artifacts
    stats["missing_resume_artifacts"] = missing_resume_artifacts
    stats["missing_report_paths"] = missing_report_paths
    stats["missing_report_files"] = missing_report_files

    if missing_resume_artifacts:
        errors.append(f"{missing_resume_artifacts} resume_output artifacts are missing/unreadable.")
    if missing_report_paths:
        errors.append(f"{missing_report_paths} resume_output artifacts are missing report_md_path.")
    if missing_report_files:
        errors.append(f"{missing_report_files} report_md files referenced by artifacts are missing.")

    followup_due = len(get_jobs_needing_followup())
    stats["followup_due"] = followup_due
    if followup_due:
        warnings.append(f"{followup_due} jobs currently need follow-up.")

    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "stats": stats,
    }
