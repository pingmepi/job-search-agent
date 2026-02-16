"""Scheduled runner for follow-up detection and draft generation."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from uuid import uuid4

from agents.followup.agent import detect_followups, generate_all_followups
from core.db import complete_run, insert_run

logger = logging.getLogger(__name__)


def _next_run_id() -> str:
    return f"followup-{uuid4().hex[:12]}"


def run_followup_cycle(
    *,
    db_path: Path | None = None,
    dry_run: bool = False,
    persist_progress: bool = True,
) -> dict:
    """Execute a single follow-up scan/generation cycle and persist telemetry."""
    run_id = _next_run_id()
    insert_run(run_id, "followup_runner", db_path=db_path)

    try:
        if dry_run:
            jobs = detect_followups(db_path=db_path)
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
            payload = generate_all_followups(
                db_path=db_path,
                persist_progress=persist_progress,
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
            context={"jobs": payload[:20]},
            db_path=db_path,
        )
        return summary
    except Exception as exc:
        logger.exception("Follow-up cycle failed")
        complete_run(
            run_id,
            status="failed",
            errors=[str(exc)],
            db_path=db_path,
        )
        raise


def run_scheduler(
    *,
    interval_minutes: int,
    max_cycles: int | None = None,
    db_path: Path | None = None,
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
            db_path=db_path,
            dry_run=dry_run,
            persist_progress=persist_progress,
        )
        results.append(result)
        cycles += 1

        if max_cycles is not None and cycles >= max_cycles:
            return results

        sleep_fn(interval_minutes * 60)
