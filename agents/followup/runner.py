"""Scheduled runner for follow-up detection and draft generation."""

from __future__ import annotations

import logging
import time
from uuid import uuid4

from agents.followup.agent import detect_followups, generate_followup_draft_with_telemetry
from core.feedback import TASK_OUTCOME_FAIL, TASK_OUTCOME_SUCCESS, TASK_TYPE_FOLLOWUP, classify_error_types
from core.db import complete_run, insert_run

logger = logging.getLogger(__name__)


def _next_run_id() -> str:
    return f"followup-{uuid4().hex[:12]}"


def run_followup_cycle(
    *,
    dry_run: bool = False,
    persist_progress: bool = True,
) -> dict:
    """Execute a single follow-up scan/generation cycle and persist telemetry."""
    run_id = _next_run_id()
    insert_run(run_id, "followup_runner")

    try:
        prompt_versions: list[str] | None = [] if not dry_run else None
        models_used: list[str] | None = [] if not dry_run else None
        if dry_run:
            jobs = detect_followups()
            payload = [
                {
                    "job_id": job["id"],
                    "company": job["company"],
                    "role": job["role"],
                    "tier": job.get("tier_number", 0) + 1,
                }
                for job in jobs
            ]
        else:
            jobs = detect_followups()
            payload = []
            for job in jobs:
                draft, llm_resp = generate_followup_draft_with_telemetry(job)
                if prompt_versions is not None:
                    prompt_versions.append("followup_draft:inline_prompt:v1")
                if models_used is not None:
                    models_used.append(llm_resp.model)
                next_count = int(job.get("follow_up_count", 0) or 0)
                if persist_progress:
                    from agents.followup.agent import _persist_followup_progress

                    next_count = _persist_followup_progress(job)
                payload.append(
                    {
                        "job_id": job["id"],
                        "company": job["company"],
                        "role": job["role"],
                        "tier": job["tier_number"] + 1,
                        "draft": draft,
                        "follow_up_count_after": next_count,
                    }
                )

        summary = {
            "run_id": run_id,
            "dry_run": dry_run,
            "persist_progress": persist_progress,
            "count": len(payload),
            "jobs": payload,
        }
        complete_run(
            run_id,
            status="completed",
            eval_results={
                "followup_jobs_detected": len(payload),
                "dry_run": dry_run,
                "persist_progress": persist_progress,
            },
            task_type=TASK_TYPE_FOLLOWUP,
            task_outcome=TASK_OUTCOME_SUCCESS,
            error_types=[],
            prompt_versions=prompt_versions,
            models_used=models_used,
            context={"jobs": payload[:20]},
        )
        return summary
    except Exception as exc:
        logger.exception("Follow-up cycle failed")
        complete_run(
            run_id,
            status="failed",
            errors=[str(exc)],
            task_type=TASK_TYPE_FOLLOWUP,
            task_outcome=TASK_OUTCOME_FAIL,
            error_types=classify_error_types([str(exc)]),
            prompt_versions=None if dry_run else ["followup_draft:inline_prompt:v1"],
        )
        raise


def run_scheduler(
    *,
    interval_minutes: int,
    max_cycles: int | None = None,
    dry_run: bool = False,
    persist_progress: bool = True,
    sleep_fn=time.sleep,
) -> list[dict]:
    """Run follow-up cycles repeatedly at a fixed interval."""
    if interval_minutes <= 0:
        raise ValueError("interval_minutes must be > 0")

    results: list[dict] = []
    cycles = 0
    while True:
        result = run_followup_cycle(
            dry_run=dry_run,
            persist_progress=persist_progress,
        )
        results.append(result)
        cycles += 1

        if max_cycles is not None and cycles >= max_cycles:
            return results

        sleep_fn(interval_minutes * 60)
