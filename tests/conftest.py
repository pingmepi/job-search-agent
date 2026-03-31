"""Shared pytest fixtures for the inbox-agent test suite."""

from __future__ import annotations

import os

import psycopg2
import psycopg2.extras
import pytest

from core.db import init_db


@pytest.fixture
def db():
    """Ensure clean PostgreSQL tables for each test.

    Skips the test if DATABASE_URL is not set (CI/local without PG).
    Truncates all tables and resets sequences after each test so tests
    are independent regardless of execution order.
    """
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        pytest.skip("DATABASE_URL not set — skipping PostgreSQL tests")
    init_db()

    def _truncate() -> None:
        conn = psycopg2.connect(database_url, cursor_factory=psycopg2.extras.RealDictCursor)
        try:
            cur = conn.cursor()
            cur.execute(
                "TRUNCATE TABLE webhook_events, runs, jobs RESTART IDENTITY CASCADE"
            )
            conn.commit()
        finally:
            conn.close()

    _truncate()   # ensure clean state before the test
    yield database_url
    _truncate()   # clean up after the test
