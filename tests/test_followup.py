"""Tests for agents/followup/agent.py — Follow-Up Agent."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from core.db import init_db
from agents.followup.agent import (
    detect_followups,
    ESCALATION_TIERS,
    MAX_FOLLOW_UPS,
    generate_all_followups,
)


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "test.db"
    init_db(path)
    return path


def _insert_old_job(db_path: Path, company: str, days_ago: int, follow_up_count: int = 0):
    """Insert a job from N days ago."""
    old_date = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            """INSERT INTO jobs
               (company, role, jd_hash, status, follow_up_count, created_at, updated_at)
               VALUES (?, 'PM', 'hash', 'applied', ?, ?, ?)""",
            (company, follow_up_count, old_date, old_date),
        )


class TestFollowupDetection:
    def test_detects_old_jobs(self, db_path: Path):
        _insert_old_job(db_path, "OldCo", days_ago=10)
        jobs = detect_followups(db_path=db_path)
        assert len(jobs) == 1
        assert jobs[0]["company"] == "OldCo"

    def test_ignores_recent_jobs(self, db_path: Path):
        _insert_old_job(db_path, "NewCo", days_ago=3)
        jobs = detect_followups(db_path=db_path)
        assert len(jobs) == 0

    def test_escalation_tier(self, db_path: Path):
        _insert_old_job(db_path, "TierCo", days_ago=15, follow_up_count=1)
        jobs = detect_followups(db_path=db_path)
        assert len(jobs) == 1
        assert jobs[0]["tier_number"] == 1
        assert jobs[0]["escalation_tier"]["label"] == "2nd follow-up"

    def test_exhausted_tiers_excluded(self, db_path: Path):
        _insert_old_job(db_path, "DoneCo", days_ago=30, follow_up_count=MAX_FOLLOW_UPS)
        jobs = detect_followups(db_path=db_path)
        assert len(jobs) == 0

    def test_multiple_jobs_sorted(self, db_path: Path):
        _insert_old_job(db_path, "AlphaCo", days_ago=15)
        _insert_old_job(db_path, "BetaCo", days_ago=10)
        jobs = detect_followups(db_path=db_path)
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
    def test_generate_all_followups_persists_progress(self, db_path: Path, monkeypatch):
        _insert_old_job(db_path, "ProgressCo", days_ago=12, follow_up_count=1)

        def _fake_generate(_: dict) -> str:
            return "follow-up draft"

        monkeypatch.setattr(
            "agents.followup.agent.generate_followup_draft",
            _fake_generate,
        )

        results = generate_all_followups(db_path=db_path)
        assert len(results) == 1
        assert results[0]["follow_up_count_after"] == 2

        with sqlite3.connect(str(db_path)) as conn:
            row = conn.execute(
                "SELECT follow_up_count, last_follow_up_at FROM jobs WHERE company = ?",
                ("ProgressCo",),
            ).fetchone()
        assert row is not None
        assert row[0] == 2
        assert row[1] is not None

    def test_generate_all_followups_can_skip_progress_persistence(
        self,
        db_path: Path,
        monkeypatch,
    ):
        _insert_old_job(db_path, "NoPersistCo", days_ago=12, follow_up_count=0)

        def _fake_generate(_: dict) -> str:
            return "follow-up draft"

        monkeypatch.setattr(
            "agents.followup.agent.generate_followup_draft",
            _fake_generate,
        )

        results = generate_all_followups(db_path=db_path, persist_progress=False)
        assert len(results) == 1
        assert results[0]["follow_up_count_after"] == 0

        with sqlite3.connect(str(db_path)) as conn:
            row = conn.execute(
                "SELECT follow_up_count, last_follow_up_at FROM jobs WHERE company = ?",
                ("NoPersistCo",),
            ).fetchone()
        assert row is not None
        assert row[0] == 0
        assert row[1] is None
