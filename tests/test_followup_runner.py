from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from agents.followup.runner import run_followup_cycle, run_scheduler
from core.db import get_run, init_db


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "runner.db"
    init_db(path)
    return path


def _insert_old_job(db_path: Path, company: str, *, follow_up_count: int = 0) -> None:
    old_date = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            """INSERT INTO jobs
               (company, role, jd_hash, status, follow_up_count, created_at, updated_at)
               VALUES (?, 'Engineer', 'hash', 'applied', ?, ?, ?)""",
            (company, follow_up_count, old_date, old_date),
        )


def test_run_followup_cycle_dry_run(db_path: Path):
    _insert_old_job(db_path, "DryRunCo")

    result = run_followup_cycle(db_path=db_path, dry_run=True)

    assert result["dry_run"] is True
    assert result["count"] == 1
    run = get_run(result["run_id"], db_path=db_path)
    assert run is not None
    assert run["status"] == "completed"
    assert run["eval_results"]["dry_run"] is True


def test_run_followup_cycle_persists_progress(db_path: Path, monkeypatch):
    _insert_old_job(db_path, "PersistCo")

    monkeypatch.setattr(
        "agents.followup.agent.generate_followup_draft",
        lambda _: "draft",
    )

    result = run_followup_cycle(db_path=db_path)

    assert result["count"] == 1
    assert result["jobs"][0]["follow_up_count_after"] == 1
    with sqlite3.connect(str(db_path)) as conn:
        row = conn.execute(
            "SELECT follow_up_count FROM jobs WHERE company = ?",
            ("PersistCo",),
        ).fetchone()
    assert row == (1,)


def test_run_scheduler_runs_multiple_cycles(db_path: Path):
    calls = []

    def _sleep(seconds: float) -> None:
        calls.append(seconds)

    results = run_scheduler(
        db_path=db_path,
        interval_minutes=5,
        max_cycles=2,
        dry_run=True,
        sleep_fn=_sleep,
    )

    assert len(results) == 2
    assert calls == [300]


def test_run_scheduler_requires_positive_interval(db_path: Path):
    with pytest.raises(ValueError, match="interval_minutes"):
        run_scheduler(db_path=db_path, interval_minutes=0, max_cycles=1)
