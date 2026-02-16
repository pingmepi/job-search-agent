"""
Telemetry logger — writes per-run eval results to runs/ as JSON and to SQLite.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.config import get_settings
from core.db import insert_run, complete_run


def generate_run_id() -> str:
    """Generate a unique run identifier."""
    return f"run-{uuid.uuid4().hex[:12]}"


def log_run(
    agent: str,
    eval_results: dict[str, Any],
    *,
    job_id: int | None = None,
    tokens_used: int = 0,
    cost_estimate: float = 0.0,
    latency_ms: int = 0,
    input_mode: str | None = None,
    skip_upload: bool | None = None,
    skip_calendar: bool | None = None,
    errors: list[str] | None = None,
    context: dict[str, Any] | None = None,
) -> str:
    """
    Log a completed run to both SQLite and a JSON file in runs/.

    Returns the run_id.
    """
    run_id = generate_run_id()
    settings = get_settings()

    # ── SQLite ─────────────────────────────────────────
    insert_run(run_id, agent, job_id=job_id)
    complete_run(
        run_id,
        status="completed",
        eval_results=eval_results,
        tokens_used=tokens_used,
        cost_estimate=cost_estimate,
        latency_ms=latency_ms,
        input_mode=input_mode,
        skip_upload=skip_upload,
        skip_calendar=skip_calendar,
        errors=errors,
        context=context,
    )

    # ── JSON file ──────────────────────────────────────
    runs_dir = settings.runs_dir
    runs_dir.mkdir(parents=True, exist_ok=True)

    log_entry = {
        "run_id": run_id,
        "agent": agent,
        "job_id": job_id,
        "eval_results": eval_results,
        "tokens_used": tokens_used,
        "cost_estimate": cost_estimate,
        "latency_ms": latency_ms,
        "input_mode": input_mode,
        "skip_upload": skip_upload,
        "skip_calendar": skip_calendar,
        "errors": errors or [],
        "error_count": len(errors or []),
        "context": context or {},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    log_path = runs_dir / f"{run_id}.json"
    log_path.write_text(json.dumps(log_entry, indent=2), encoding="utf-8")

    return run_id
