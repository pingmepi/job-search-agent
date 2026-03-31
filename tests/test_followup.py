"""Tests for agents/followup/agent.py — Follow-Up Agent."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import psycopg2
import psycopg2.extras
import pytest

from core.db import init_db
from agents.followup.agent import (
    detect_followups,
    ESCALATION_TIERS,
    MAX_FOLLOW_UPS,
    generate_all_followups,
)


def _insert_old_job(database_url: str, company: str, days_ago: int, follow_up_count: int = 0):
    """Insert a job from N days ago directly via psycopg2."""
    old_date = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()
    conn = psycopg2.connect(database_url, cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO jobs
               (company, role, jd_hash, status, follow_up_count, created_at, updated_at)
               VALUES (%s, 'PM', 'hash', 'applied', %s, %s, %s)""",
            (company, follow_up_count, old_date, old_date),
        )
        conn.commit()
    finally:
        conn.close()


def _read_job(database_url: str, company: str) -> dict:
    conn = psycopg2.connect(database_url, cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM jobs WHERE company = %s", (company,))
        return dict(cur.fetchone())
    finally:
        conn.close()


class TestFollowupDetection:
    def test_detects_old_jobs(self, db):
        _insert_old_job(db, "OldCo", days_ago=10)
        jobs = detect_followups()
        assert len(jobs) == 1
        assert jobs[0]["company"] == "OldCo"

    def test_ignores_recent_jobs(self, db):
        _insert_old_job(db, "NewCo", days_ago=3)
        jobs = detect_followups()
        assert len(jobs) == 0

    def test_escalation_tier(self, db):
        _insert_old_job(db, "TierCo", days_ago=15, follow_up_count=1)
        jobs = detect_followups()
        assert len(jobs) == 1
        assert jobs[0]["tier_number"] == 1
        assert jobs[0]["escalation_tier"]["label"] == "2nd follow-up"

    def test_exhausted_tiers_excluded(self, db):
        _insert_old_job(db, "DoneCo", days_ago=30, follow_up_count=MAX_FOLLOW_UPS)
        jobs = detect_followups()
        assert len(jobs) == 0

    def test_multiple_jobs_sorted(self, db):
        _insert_old_job(db, "AlphaCo", days_ago=15)
        _insert_old_job(db, "BetaCo", days_ago=10)
        jobs = detect_followups()
        assert len(jobs) == 2
        # Older first
        assert jobs[0]["company"] == "AlphaCo"


class TestEscalationTiers:
    def test_three_tiers_defined(self):
        assert len(ESCALATION_TIERS) == 3

    def test_tier_labels(self):
        assert ESCALATION_TIERS[0]["label"] == "1st follow-up"
        assert ESCALATION_TIERS[1]["label"] == "2nd follow-up"
        assert ESCALATION_TIERS[2]["label"] == "3rd follow-up"


class TestFollowupProgression:
    def test_generate_all_followups_persists_progress(self, db, monkeypatch):
        _insert_old_job(db, "ProgressCo", days_ago=12, follow_up_count=1)

        def _fake_generate(_: dict) -> str:
            return "follow-up draft"

        monkeypatch.setattr(
            "agents.followup.agent.generate_followup_draft",
            _fake_generate,
        )

        results = generate_all_followups()
        assert len(results) == 1
        assert results[0]["follow_up_count_after"] == 2

        row = _read_job(db, "ProgressCo")
        assert row["follow_up_count"] == 2
        assert row["last_follow_up_at"] is not None

    def test_generate_all_followups_can_skip_progress_persistence(
        self,
        db,
        monkeypatch,
    ):
        _insert_old_job(db, "NoPersistCo", days_ago=12, follow_up_count=0)

        def _fake_generate(_: dict) -> str:
            return "follow-up draft"

        monkeypatch.setattr(
            "agents.followup.agent.generate_followup_draft",
            _fake_generate,
        )

        results = generate_all_followups(persist_progress=False)
        assert len(results) == 1
        assert results[0]["follow_up_count_after"] == 0

        row = _read_job(db, "NoPersistCo")
        assert row["follow_up_count"] == 0
        assert row["last_follow_up_at"] is None
