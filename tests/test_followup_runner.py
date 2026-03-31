from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import psycopg2
import psycopg2.extras
import pytest

from agents.followup.runner import run_followup_cycle, run_scheduler
from core.db import get_run, init_db


def _insert_old_job(database_url: str, company: str, *, follow_up_count: int = 0) -> None:
    old_date = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
    conn = psycopg2.connect(database_url, cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO jobs
               (company, role, jd_hash, status, follow_up_count, created_at, updated_at)
               VALUES (%s, 'Engineer', 'hash', 'applied', %s, %s, %s)""",
            (company, follow_up_count, old_date, old_date),
        )
        conn.commit()
    finally:
        conn.close()


def _read_follow_up_count(database_url: str, company: str) -> int:
    conn = psycopg2.connect(database_url, cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur = conn.cursor()
        cur.execute("SELECT follow_up_count FROM jobs WHERE company = %s", (company,))
        row = cur.fetchone()
        return row["follow_up_count"]
    finally:
        conn.close()


def test_run_followup_cycle_dry_run(db):
    _insert_old_job(db, "DryRunCo")

    result = run_followup_cycle(dry_run=True)

    assert result["dry_run"] is True
    assert result["count"] == 1
    run = get_run(result["run_id"])
    assert run is not None
    assert run["status"] == "completed"
    assert run["eval_results"]["dry_run"] is True


def test_run_followup_cycle_persists_progress(db, monkeypatch):
    _insert_old_job(db, "PersistCo")

    monkeypatch.setattr(
        "agents.followup.agent.generate_followup_draft",
        lambda _: "draft",
    )

    result = run_followup_cycle()

    assert result["count"] == 1
    assert result["jobs"][0]["follow_up_count_after"] == 1
    assert _read_follow_up_count(db, "PersistCo") == 1


def test_run_scheduler_runs_multiple_cycles(db):
    calls = []

    def _sleep(seconds: float) -> None:
        calls.append(seconds)

    results = run_scheduler(
        interval_minutes=5,
        max_cycles=2,
        dry_run=True,
        sleep_fn=_sleep,
    )

    assert len(results) == 2
    assert calls == [300]


def test_run_scheduler_requires_positive_interval(db):
    with pytest.raises(ValueError, match="interval_minutes"):
        run_scheduler(interval_minutes=0, max_cycles=1)
