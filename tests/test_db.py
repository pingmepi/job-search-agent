"""Tests for core/db.py — SQLite schema + CRUD."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from core.db import (
    init_db,
    insert_job,
    get_job,
    get_jobs_needing_followup,
    update_job,
    insert_run,
    complete_run,
    get_run,
)


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    """Create a fresh in-memory-like DB in a temp directory."""
    path = tmp_path / "test.db"
    init_db(path)
    return path


class TestSchema:
    def test_init_creates_db(self, db_path: Path):
        assert db_path.exists()

    def test_init_idempotent(self, db_path: Path):
        # Calling init again should not raise
        init_db(db_path)
        assert db_path.exists()


class TestJobsCRUD:
    def test_insert_and_get(self, db_path: Path):
        job_id = insert_job(
            "Acme Corp", "AI PM", "abc123",
            fit_score=85, resume_used="master_ai.tex",
            db_path=db_path,
        )
        assert job_id is not None
        assert job_id > 0

        job = get_job(job_id, db_path=db_path)
        assert job is not None
        assert job["company"] == "Acme Corp"
        assert job["role"] == "AI PM"
        assert job["jd_hash"] == "abc123"
        assert job["fit_score"] == 85

    def test_get_nonexistent(self, db_path: Path):
        assert get_job(9999, db_path=db_path) is None

    def test_update_job(self, db_path: Path):
        job_id = insert_job("TestCo", "PM", "hash1", db_path=db_path)
        update_job(job_id, status="interviewing", fit_score=90, db_path=db_path)
        job = get_job(job_id, db_path=db_path)
        assert job["status"] == "interviewing"
        assert job["fit_score"] == 90

    def test_followup_detection(self, db_path: Path):
        import sqlite3
        # Insert a job with created_at 10 days ago
        from datetime import datetime, timedelta, timezone
        old_date = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
        with sqlite3.connect(str(db_path)) as conn:
            conn.execute(
                """INSERT INTO jobs
                   (company, role, jd_hash, status, created_at, updated_at)
                   VALUES (?, ?, ?, 'applied', ?, ?)""",
                ("OldCo", "PM", "hash_old", old_date, old_date),
            )
        results = get_jobs_needing_followup(db_path=db_path)
        assert len(results) >= 1
        assert results[0]["company"] == "OldCo"


class TestRunsCRUD:
    def test_insert_and_complete(self, db_path: Path):
        insert_run("run-001", "inbox", db_path=db_path)
        run = get_run("run-001", db_path=db_path)
        assert run is not None
        assert run["status"] == "started"
        assert run["eval_results"] is None

        complete_run(
            "run-001",
            status="completed",
            eval_results={"compile_success": True, "forbidden_claims": 0},
            tokens_used=1500,
            cost_estimate=0.03,
            latency_ms=2500,
            db_path=db_path,
        )
        run = get_run("run-001", db_path=db_path)
        assert run["status"] == "completed"
        assert run["eval_results"]["compile_success"] is True
        assert run["tokens_used"] == 1500

    def test_get_nonexistent_run(self, db_path: Path):
        assert get_run("nope", db_path=db_path) is None
