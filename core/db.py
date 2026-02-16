"""
SQLite database layer for inbox-agent.

Tables:
  - jobs   : tracks every job application (PRD §5.3)
  - runs   : telemetry per agent invocation
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Generator

from core.config import get_settings

# ── Schema DDL ────────────────────────────────────────────────────

JOBS_DDL = """\
CREATE TABLE IF NOT EXISTS jobs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    company         TEXT    NOT NULL,
    role            TEXT    NOT NULL,
    jd_hash         TEXT    NOT NULL,
    fit_score       INTEGER,
    resume_used     TEXT,
    drive_link      TEXT,
    status          TEXT    DEFAULT 'applied',
    follow_up_count INTEGER DEFAULT 0,
    created_at      TEXT    NOT NULL,
    updated_at      TEXT    NOT NULL
);
"""

RUNS_DDL = """\
CREATE TABLE IF NOT EXISTS runs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          TEXT    NOT NULL UNIQUE,
    agent           TEXT    NOT NULL,
    job_id          INTEGER REFERENCES jobs(id),
    status          TEXT    NOT NULL DEFAULT 'started',
    eval_results    TEXT,
    tokens_used     INTEGER,
    cost_estimate   REAL,
    latency_ms      INTEGER,
    created_at      TEXT    NOT NULL,
    completed_at    TEXT
);
"""

RUNS_MIGRATIONS: dict[str, str] = {
    "input_mode": "TEXT",
    "skip_upload": "INTEGER",
    "skip_calendar": "INTEGER",
    "error_count": "INTEGER",
    "errors_json": "TEXT",
    "context_json": "TEXT",
}


# ── Helpers ───────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {row[1] for row in rows}


def _apply_migrations(conn: sqlite3.Connection) -> None:
    runs_columns = _table_columns(conn, "runs")
    for column, sql_type in RUNS_MIGRATIONS.items():
        if column not in runs_columns:
            conn.execute(f"ALTER TABLE runs ADD COLUMN {column} {sql_type}")


def init_db(db_path: Path | None = None) -> Path:
    """Create the database file + tables if they don't exist.  Returns the path."""
    path = db_path or get_settings().db_path
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(path)) as conn:
        conn.execute(JOBS_DDL)
        conn.execute(RUNS_DDL)
        _apply_migrations(conn)
    return path


@contextmanager
def get_conn(db_path: Path | None = None) -> Generator[sqlite3.Connection, None, None]:
    """Yield a connection with row_factory set to sqlite3.Row."""
    path = db_path or get_settings().db_path
    init_db(path)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


# ── Job CRUD ──────────────────────────────────────────────────────

def insert_job(
    company: str,
    role: str,
    jd_hash: str,
    *,
    fit_score: int | None = None,
    resume_used: str | None = None,
    drive_link: str | None = None,
    db_path: Path | None = None,
) -> int:
    """Insert a new job row and return its id."""
    now = _now_iso()
    with get_conn(db_path) as conn:
        cur = conn.execute(
            """INSERT INTO jobs
               (company, role, jd_hash, fit_score, resume_used, drive_link, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (company, role, jd_hash, fit_score, resume_used, drive_link, now, now),
        )
        return cur.lastrowid  # type: ignore[return-value]


def get_job(job_id: int, *, db_path: Path | None = None) -> dict[str, Any] | None:
    """Fetch a single job by id."""
    with get_conn(db_path) as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return dict(row) if row else None


def get_jobs_needing_followup(*, db_path: Path | None = None) -> list[dict[str, Any]]:
    """Return jobs where status='applied' and created_at is > 7 days ago."""
    with get_conn(db_path) as conn:
        rows = conn.execute(
            """SELECT * FROM jobs
               WHERE status = 'applied'
                 AND datetime(created_at) <= datetime('now', '-7 days')
               ORDER BY created_at ASC"""
        ).fetchall()
        return [dict(r) for r in rows]


def update_job(job_id: int, *, db_path: Path | None = None, **fields: Any) -> None:
    """Update arbitrary columns on a job row."""
    if not fields:
        return
    fields["updated_at"] = _now_iso()
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [job_id]
    with get_conn(db_path) as conn:
        conn.execute(f"UPDATE jobs SET {set_clause} WHERE id = ?", values)


# ── Run CRUD ──────────────────────────────────────────────────────

def insert_run(
    run_id: str,
    agent: str,
    *,
    job_id: int | None = None,
    db_path: Path | None = None,
) -> None:
    """Start a new run record."""
    with get_conn(db_path) as conn:
        conn.execute(
            """INSERT INTO runs (run_id, agent, job_id, status, created_at)
               VALUES (?, ?, ?, 'started', ?)""",
            (run_id, agent, job_id, _now_iso()),
        )


def complete_run(
    run_id: str,
    *,
    status: str = "completed",
    eval_results: dict | None = None,
    tokens_used: int | None = None,
    cost_estimate: float | None = None,
    latency_ms: int | None = None,
    input_mode: str | None = None,
    skip_upload: bool | None = None,
    skip_calendar: bool | None = None,
    errors: list[str] | None = None,
    context: dict[str, Any] | None = None,
    db_path: Path | None = None,
) -> None:
    """Mark a run as completed with eval results."""
    error_count = len(errors) if errors else 0
    with get_conn(db_path) as conn:
        conn.execute(
            """UPDATE runs
               SET status = ?, eval_results = ?, tokens_used = ?,
                   cost_estimate = ?, latency_ms = ?, input_mode = ?,
                   skip_upload = ?, skip_calendar = ?, error_count = ?,
                   errors_json = ?, context_json = ?, completed_at = ?
               WHERE run_id = ?""",
            (
                status,
                json.dumps(eval_results) if eval_results else None,
                tokens_used,
                cost_estimate,
                latency_ms,
                input_mode,
                int(skip_upload) if skip_upload is not None else None,
                int(skip_calendar) if skip_calendar is not None else None,
                error_count,
                json.dumps(errors) if errors is not None else None,
                json.dumps(context) if context is not None else None,
                _now_iso(),
                run_id,
            ),
        )


def get_run(run_id: str, *, db_path: Path | None = None) -> dict[str, Any] | None:
    """Fetch a single run by run_id."""
    with get_conn(db_path) as conn:
        row = conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        if row:
            d = dict(row)
            if d.get("eval_results"):
                d["eval_results"] = json.loads(d["eval_results"])
            if d.get("errors_json"):
                d["errors"] = json.loads(d["errors_json"])
            if d.get("context_json"):
                d["context"] = json.loads(d["context_json"])
            return d
        return None


def get_db_stats(*, db_path: Path | None = None) -> dict[str, Any]:
    """Return a lightweight summary of persisted jobs/runs for quick debugging."""
    with get_conn(db_path) as conn:
        jobs_row = conn.execute(
            """SELECT
                   COUNT(*) AS total_jobs,
                   SUM(CASE WHEN status = 'applied' THEN 1 ELSE 0 END) AS applied_jobs,
                   SUM(CASE WHEN follow_up_count = 0 THEN 1 ELSE 0 END) AS follow_up_zero,
                   SUM(CASE WHEN fit_score IS NULL THEN 1 ELSE 0 END) AS fit_score_nulls,
                   SUM(CASE WHEN drive_link IS NULL OR drive_link = '' THEN 1 ELSE 0 END) AS drive_link_empty
               FROM jobs"""
        ).fetchone()
        runs_row = conn.execute(
            """SELECT
                   COUNT(*) AS total_runs,
                   SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) AS completed_runs,
                   SUM(CASE WHEN tokens_used IS NULL THEN 1 ELSE 0 END) AS tokens_nulls,
                   SUM(CASE WHEN latency_ms IS NULL THEN 1 ELSE 0 END) AS latency_nulls,
                   SUM(CASE WHEN error_count > 0 THEN 1 ELSE 0 END) AS runs_with_errors
               FROM runs"""
        ).fetchone()
        compile_row = conn.execute(
            """SELECT
                   SUM(CASE WHEN json_extract(eval_results, '$.compile_success') = 1 THEN 1 ELSE 0 END) AS compile_successes,
                   SUM(CASE WHEN json_extract(eval_results, '$.compile_success') = 0 THEN 1 ELSE 0 END) AS compile_failures
               FROM runs
               WHERE eval_results IS NOT NULL"""
        ).fetchone()

    jobs = dict(jobs_row) if jobs_row else {}
    runs = dict(runs_row) if runs_row else {}
    compile_stats = dict(compile_row) if compile_row else {}
    return {
        "db_path": str(db_path or get_settings().db_path),
        "jobs": jobs,
        "runs": runs,
        "compile": compile_stats,
    }
