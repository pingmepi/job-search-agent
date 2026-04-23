"""Tests for core/db.py — PostgreSQL schema + CRUD."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import psycopg2
import psycopg2.extras

from core.db import (
    complete_run,
    get_job,
    get_jobs_needing_followup,
    get_run,
    get_webhook_event,
    init_db,
    insert_job,
    insert_run,
    insert_webhook_event,
    update_job,
    update_webhook_event,
)


class TestSchema:
    def test_init_idempotent(self, db):
        # Calling init again should not raise
        init_db()

    def test_init_applies_migrations(self, db):
        database_url = db
        conn = psycopg2.connect(database_url, cursor_factory=psycopg2.extras.RealDictCursor)
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_name = 'jobs'"
            )
            job_columns = {row["column_name"] for row in cur.fetchall()}

            cur.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_name = 'runs'"
            )
            run_columns = {row["column_name"] for row in cur.fetchall()}

            cur.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_name = 'webhook_events'"
            )
            webhook_columns = {row["column_name"] for row in cur.fetchall()}
        finally:
            conn.close()

        assert "last_follow_up_at" in job_columns
        assert "user_vetted" in job_columns
        assert "input_mode" in run_columns
        assert "skip_upload" in run_columns
        assert "skip_calendar" in run_columns
        assert "error_count" in run_columns
        assert "errors_json" in run_columns
        assert "context_json" in run_columns
        assert "event_id" in webhook_columns
        assert "payload_json" in webhook_columns
        assert "processing_status" in webhook_columns


class TestJobsCRUD:
    def test_insert_and_get(self, db):
        job_id = insert_job(
            "Acme Corp",
            "AI PM",
            "abc123",
            user_vetted=True,
            fit_score=85,
            resume_used="master_ai.tex",
        )
        assert job_id is not None
        assert job_id > 0

        job = get_job(job_id)
        assert job is not None
        assert job["company"] == "Acme Corp"
        assert job["role"] == "AI PM"
        assert job["jd_hash"] == "abc123"
        assert job["user_vetted"] == 1
        assert job["fit_score"] == 85

    def test_get_nonexistent(self, db):
        assert get_job(9999999) is None

    def test_update_job(self, db):
        job_id = insert_job("TestCo", "PM", "hash1")
        update_job(job_id, status="interviewing", fit_score=90)
        job = get_job(job_id)
        assert job["status"] == "interviewing"
        assert job["fit_score"] == 90

    def test_followup_detection(self, db):
        database_url = db
        old_date = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
        conn = psycopg2.connect(database_url, cursor_factory=psycopg2.extras.RealDictCursor)
        try:
            cur = conn.cursor()
            cur.execute(
                """INSERT INTO jobs
                   (company, role, jd_hash, status, created_at, updated_at)
                   VALUES (%s, %s, %s, 'applied', %s, %s)""",
                ("OldCo", "PM", "hash_old", old_date, old_date),
            )
            conn.commit()
        finally:
            conn.close()

        results = get_jobs_needing_followup()
        assert len(results) >= 1
        assert results[0]["company"] == "OldCo"


class TestRunsCRUD:
    def test_insert_and_complete(self, db):
        insert_run("run-001", "inbox")
        run = get_run("run-001")
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
            input_mode="text",
            skip_upload=True,
            skip_calendar=False,
            errors=["example error"],
            context={"company": "Acme", "jd_hash": "abc123"},
        )
        run = get_run("run-001")
        assert run["status"] == "completed"
        assert run["eval_results"]["compile_success"] is True
        assert run["tokens_used"] == 1500
        assert run["input_mode"] == "text"
        assert run["skip_upload"] == 1
        assert run["skip_calendar"] == 0
        assert run["error_count"] == 1
        assert run["errors"] == ["example error"]
        assert run["context"]["company"] == "Acme"

    def test_get_nonexistent_run(self, db):
        assert get_run("nope") is None


class TestWebhookEventsCRUD:
    def test_insert_update_and_get(self, db):
        insert_webhook_event(
            "evt-1",
            update_id=123,
            payload={"update_id": 123, "message": {"text": "hello"}},
            headers={"x-test": "1"},
        )
        update_webhook_event(
            "evt-1",
            processing_status="processed",
            mark_processed=True,
        )
        event = get_webhook_event(event_id="evt-1")
        assert event is not None
        assert event["update_id"] == 123
        assert event["processing_status"] == "processed"
        assert event["payload"]["message"]["text"] == "hello"
