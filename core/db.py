"""
PostgreSQL database layer for inbox-agent.

Tables:
  - jobs           : tracks every job application (PRD §5.3)
  - runs           : telemetry per agent invocation
  - run_steps      : per-step audit trail for each run
  - webhook_events : raw webhook envelopes and processing lifecycle
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Generator

import psycopg2
import psycopg2.extras
import psycopg2.pool

from core.config import get_settings

# ── Connection pool ──────────────────────────────────────────────

_pool: psycopg2.pool.ThreadedConnectionPool | None = None

# ── Schema DDL ────────────────────────────────────────────────────

JOBS_DDL = """\
CREATE TABLE IF NOT EXISTS jobs (
    id              SERIAL PRIMARY KEY,
    company         TEXT    NOT NULL,
    role            TEXT    NOT NULL,
    jd_hash         TEXT    NOT NULL,
    fit_score       INTEGER,
    resume_used     TEXT,
    drive_link      TEXT,
    status          TEXT    DEFAULT 'applied',
    follow_up_count INTEGER DEFAULT 0,
    last_follow_up_at TEXT,
    created_at      TEXT    NOT NULL,
    updated_at      TEXT    NOT NULL
);
"""

RUNS_DDL = """\
CREATE TABLE IF NOT EXISTS runs (
    id              SERIAL PRIMARY KEY,
    run_id          TEXT    NOT NULL UNIQUE,
    agent           TEXT    NOT NULL,
    job_id          INTEGER REFERENCES jobs(id),
    status          TEXT    NOT NULL DEFAULT 'started',
    eval_results    TEXT,
    tokens_used     INTEGER,
    cost_estimate   REAL,
    latency_ms      INTEGER,
    input_mode      TEXT,
    skip_upload     INTEGER,
    skip_calendar   INTEGER,
    error_count     INTEGER,
    errors_json     TEXT,
    context_json    TEXT,
    created_at      TEXT    NOT NULL,
    completed_at    TEXT
);
"""

RUN_STEPS_DDL = """\
CREATE TABLE IF NOT EXISTS run_steps (
    id          SERIAL PRIMARY KEY,
    run_id      TEXT    NOT NULL,
    step_name   TEXT    NOT NULL,
    status      TEXT    NOT NULL DEFAULT 'started',
    input_json  TEXT,
    output_json TEXT,
    duration_ms INTEGER,
    error_text  TEXT,
    created_at  TEXT    NOT NULL
);
"""

RUN_STEPS_INDEX_DDL = "CREATE INDEX IF NOT EXISTS idx_run_steps_run_id ON run_steps (run_id);"

ARTICLE_SIGNALS_DDL = """\
CREATE TABLE IF NOT EXISTS article_signals (
    id          SERIAL PRIMARY KEY,
    run_id      TEXT NOT NULL,
    signal_text TEXT NOT NULL,
    created_at  TEXT NOT NULL
);
"""

WEBHOOK_EVENTS_DDL = """\
CREATE TABLE IF NOT EXISTS webhook_events (
    event_id          TEXT PRIMARY KEY,
    update_id         INTEGER,
    received_at       TEXT NOT NULL,
    headers_json      TEXT,
    payload_json      TEXT NOT NULL,
    secret_valid      INTEGER NOT NULL DEFAULT 0,
    processing_status TEXT NOT NULL DEFAULT 'received',
    run_id            TEXT,
    route_target      TEXT,
    error_text        TEXT,
    processed_at      TEXT
);
"""


# ── Helpers ───────────────────────────────────────────────────────


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _table_columns(cur: Any, table_name: str) -> set[str]:
    cur.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_name = %s",
        (table_name,),
    )
    return {row["column_name"] for row in cur.fetchall()}


def _apply_migrations(cur: Any) -> None:
    """Add columns that were introduced after initial schema creation."""
    jobs_cols = _table_columns(cur, "jobs")
    if "last_follow_up_at" not in jobs_cols:
        cur.execute("ALTER TABLE jobs ADD COLUMN IF NOT EXISTS last_follow_up_at TEXT")
    if "calendar_apply_event_id" not in jobs_cols:
        cur.execute("ALTER TABLE jobs ADD COLUMN IF NOT EXISTS calendar_apply_event_id TEXT")
    if "calendar_followup_event_id" not in jobs_cols:
        cur.execute("ALTER TABLE jobs ADD COLUMN IF NOT EXISTS calendar_followup_event_id TEXT")

    runs_cols = _table_columns(cur, "runs")
    for col, col_type in {
        "input_mode": "TEXT",
        "skip_upload": "INTEGER",
        "skip_calendar": "INTEGER",
        "error_count": "INTEGER",
        "errors_json": "TEXT",
        "context_json": "TEXT",
    }.items():
        if col not in runs_cols:
            cur.execute(f"ALTER TABLE runs ADD COLUMN IF NOT EXISTS {col} {col_type}")


def init_db() -> None:
    """Create tables if they don't exist."""
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(JOBS_DDL)
        cur.execute(RUNS_DDL)
        cur.execute(RUN_STEPS_DDL)
        cur.execute(RUN_STEPS_INDEX_DDL)
        cur.execute(WEBHOOK_EVENTS_DDL)
        cur.execute(ARTICLE_SIGNALS_DDL)
        _apply_migrations(cur)


def _get_pool() -> psycopg2.pool.ThreadedConnectionPool:
    """Return the module-level connection pool, creating it on first call."""
    global _pool
    if _pool is None or _pool.closed:
        database_url = get_settings().database_url
        if not database_url:
            raise RuntimeError("DATABASE_URL is not set")
        _pool = psycopg2.pool.ThreadedConnectionPool(
            minconn=2,
            maxconn=10,
            dsn=database_url,
            cursor_factory=psycopg2.extras.RealDictCursor,
        )
    return _pool


def close_pool() -> None:
    """Close all pooled connections. Call on graceful shutdown."""
    global _pool
    if _pool is not None and not _pool.closed:
        _pool.closeall()
        _pool = None


@contextmanager
def get_conn() -> Generator[Any, None, None]:
    """Yield a pooled psycopg2 connection with RealDictCursor."""
    pool = _get_pool()
    conn = pool.getconn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


# ── Job CRUD ──────────────────────────────────────────────────────


def insert_job(
    company: str,
    role: str,
    jd_hash: str,
    *,
    fit_score: int | None = None,
    resume_used: str | None = None,
    drive_link: str | None = None,
    calendar_apply_event_id: str | None = None,
    calendar_followup_event_id: str | None = None,
) -> int:
    """Insert a new job row and return its id."""
    now = _now_iso()
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO jobs
               (company, role, jd_hash, fit_score, resume_used, drive_link,
                calendar_apply_event_id, calendar_followup_event_id, created_at, updated_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
               RETURNING id""",
            (
                company,
                role,
                jd_hash,
                fit_score,
                resume_used,
                drive_link,
                calendar_apply_event_id,
                calendar_followup_event_id,
                now,
                now,
            ),
        )
        row = cur.fetchone()
        return row["id"]


def get_job(job_id: int) -> dict[str, Any] | None:
    """Fetch a single job by id."""
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM jobs WHERE id = %s", (job_id,))
        row = cur.fetchone()
        return dict(row) if row else None


def get_jobs_needing_followup() -> list[dict[str, Any]]:
    """Return jobs where status='applied' and created_at is > 7 days ago."""
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """SELECT * FROM jobs
               WHERE status = 'applied'
                 AND created_at::timestamptz <= NOW() - INTERVAL '7 days'
               ORDER BY created_at ASC"""
        )
        return [dict(r) for r in cur.fetchall()]


_ALLOWED_JOB_COLUMNS = {
    "company",
    "role",
    "jd_hash",
    "fit_score",
    "resume_used",
    "drive_link",
    "status",
    "follow_up_count",
    "last_follow_up_at",
    "updated_at",
    "calendar_apply_event_id",
    "calendar_followup_event_id",
}


def update_job(job_id: int, **fields: Any) -> None:
    """Update arbitrary columns on a job row."""
    if not fields:
        return
    bad_cols = set(fields) - _ALLOWED_JOB_COLUMNS - {"updated_at"}
    if bad_cols:
        raise ValueError(f"Disallowed columns in update_job: {bad_cols}")
    fields["updated_at"] = _now_iso()
    set_clause = ", ".join(f"{k} = %s" for k in fields)
    values = list(fields.values()) + [job_id]
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(f"UPDATE jobs SET {set_clause} WHERE id = %s", values)


# ── Run CRUD ──────────────────────────────────────────────────────


def insert_run(
    run_id: str,
    agent: str,
    *,
    job_id: int | None = None,
) -> None:
    """Start a new run record."""
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO runs (run_id, agent, job_id, status, created_at)
               VALUES (%s, %s, %s, 'started', %s)""",
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
) -> None:
    """Mark a run as completed with eval results."""
    error_count = len(errors) if errors else 0
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """UPDATE runs
               SET status = %s, eval_results = %s, tokens_used = %s,
                   cost_estimate = %s, latency_ms = %s, input_mode = %s,
                   skip_upload = %s, skip_calendar = %s, error_count = %s,
                   errors_json = %s, context_json = %s, completed_at = %s
               WHERE run_id = %s""",
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


def get_run(run_id: str) -> dict[str, Any] | None:
    """Fetch a single run by run_id."""
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM runs WHERE run_id = %s", (run_id,))
        row = cur.fetchone()
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


def list_runs(*, limit: int = 20) -> list[dict[str, Any]]:
    """List recent runs with full audit data, newest first."""
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """SELECT r.*, j.company, j.role
               FROM runs r
               LEFT JOIN jobs j ON r.job_id = j.id
               ORDER BY r.created_at DESC
               LIMIT %s""",
            (limit,),
        )
        results = []
        for row in cur.fetchall():
            d = dict(row)
            if d.get("eval_results"):
                d["eval_results"] = json.loads(d["eval_results"])
            if d.get("errors_json"):
                d["errors"] = json.loads(d["errors_json"])
            if d.get("context_json"):
                d["context"] = json.loads(d["context_json"])
            results.append(d)
        return results


# ── Run Steps (audit trail) ──────────────────────────────────────


def insert_step(
    run_id: str,
    step_name: str,
    *,
    input_data: dict[str, Any] | None = None,
) -> None:
    """Record the start of a pipeline step."""
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO run_steps (run_id, step_name, status, input_json, created_at)
               VALUES (%s, %s, 'started', %s, %s)""",
            (
                run_id,
                step_name,
                json.dumps(input_data, default=str) if input_data else None,
                _now_iso(),
            ),
        )


def complete_step(
    run_id: str,
    step_name: str,
    *,
    output_data: dict[str, Any] | None = None,
    duration_ms: int | None = None,
    error: str | None = None,
) -> None:
    """Mark a pipeline step as completed or failed."""
    status = "failed" if error else "completed"
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """UPDATE run_steps
               SET status = %s, output_json = %s, duration_ms = %s, error_text = %s
               WHERE run_id = %s AND step_name = %s AND status = 'started'""",
            (
                status,
                json.dumps(output_data, default=str) if output_data else None,
                duration_ms,
                error,
                run_id,
                step_name,
            ),
        )


def get_run_steps(run_id: str) -> list[dict[str, Any]]:
    """Fetch all steps for a run, ordered by creation time."""
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """SELECT * FROM run_steps
               WHERE run_id = %s
               ORDER BY created_at ASC, id ASC""",
            (run_id,),
        )
        results = []
        for row in cur.fetchall():
            d = dict(row)
            if d.get("input_json"):
                d["input"] = json.loads(d["input_json"])
            if d.get("output_json"):
                d["output"] = json.loads(d["output_json"])
            results.append(d)
        return results


def get_db_stats() -> dict[str, Any]:
    """Return a lightweight summary of persisted jobs/runs for quick debugging."""
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """SELECT
                   COUNT(*) AS total_jobs,
                   SUM(CASE WHEN status = 'applied' THEN 1 ELSE 0 END) AS applied_jobs,
                   SUM(CASE WHEN follow_up_count = 0 THEN 1 ELSE 0 END) AS follow_up_zero,
                   SUM(CASE WHEN fit_score IS NULL THEN 1 ELSE 0 END) AS fit_score_nulls,
                   SUM(CASE WHEN drive_link IS NULL OR drive_link = '' THEN 1 ELSE 0 END) AS drive_link_empty
               FROM jobs"""
        )
        jobs_row = cur.fetchone()

        cur.execute(
            """SELECT
                   COUNT(*) AS total_runs,
                   SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) AS completed_runs,
                   SUM(CASE WHEN tokens_used IS NULL THEN 1 ELSE 0 END) AS tokens_nulls,
                   SUM(CASE WHEN latency_ms IS NULL THEN 1 ELSE 0 END) AS latency_nulls,
                   SUM(CASE WHEN error_count > 0 THEN 1 ELSE 0 END) AS runs_with_errors
               FROM runs"""
        )
        runs_row = cur.fetchone()

        cur.execute(
            """SELECT
                   SUM(CASE WHEN eval_results::jsonb->>'compile_success' = 'true' THEN 1 ELSE 0 END) AS compile_successes,
                   SUM(CASE WHEN eval_results::jsonb->>'compile_success' = 'false' THEN 1 ELSE 0 END) AS compile_failures
               FROM runs
               WHERE eval_results IS NOT NULL"""
        )
        compile_row = cur.fetchone()

        cur.execute(
            """SELECT
                   COUNT(*) AS total_events,
                   SUM(CASE WHEN processing_status = 'processed' THEN 1 ELSE 0 END) AS processed_events,
                   SUM(CASE WHEN processing_status = 'failed' THEN 1 ELSE 0 END) AS failed_events
               FROM webhook_events"""
        )
        webhook_row = cur.fetchone()

    return {
        "jobs": dict(jobs_row) if jobs_row else {},
        "runs": dict(runs_row) if runs_row else {},
        "compile": dict(compile_row) if compile_row else {},
        "webhook_events": dict(webhook_row) if webhook_row else {},
    }


# ── Article Signals ──────────────────────────────────────────────


def insert_article_signals(
    run_id: str,
    signals: list[str],
) -> None:
    """Persist article-extracted job-search signals."""
    if not signals:
        return
    now = _now_iso()
    with get_conn() as conn:
        cur = conn.cursor()
        for signal in signals:
            cur.execute(
                """INSERT INTO article_signals (run_id, signal_text, created_at)
                   VALUES (%s, %s, %s)""",
                (run_id, signal, now),
            )


# ── Webhook Event CRUD ───────────────────────────────────────────


def insert_webhook_event(
    event_id: str,
    *,
    update_id: int | None,
    payload: dict[str, Any],
    headers: dict[str, Any] | None = None,
    secret_valid: bool = True,
    processing_status: str = "received",
) -> None:
    """Persist an inbound webhook envelope."""
    now = _now_iso()
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO webhook_events
               (event_id, update_id, received_at, headers_json, payload_json, secret_valid, processing_status)
               VALUES (%s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (event_id) DO NOTHING""",
            (
                event_id,
                update_id,
                now,
                json.dumps(headers or {}),
                json.dumps(payload),
                int(secret_valid),
                processing_status,
            ),
        )


def update_webhook_event(
    event_id: str,
    *,
    processing_status: str | None = None,
    run_id: str | None = None,
    route_target: str | None = None,
    error_text: str | None = None,
    mark_processed: bool = False,
) -> None:
    """Update lifecycle fields for a persisted webhook event."""
    fields: dict[str, Any] = {}
    if processing_status is not None:
        fields["processing_status"] = processing_status
    if run_id is not None:
        fields["run_id"] = run_id
    if route_target is not None:
        fields["route_target"] = route_target
    if error_text is not None:
        fields["error_text"] = error_text
    if mark_processed:
        fields["processed_at"] = _now_iso()
    if not fields:
        return
    set_clause = ", ".join(f"{k} = %s" for k in fields)
    values = list(fields.values()) + [event_id]
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            f"UPDATE webhook_events SET {set_clause} WHERE event_id = %s",
            values,
        )


def get_webhook_event(
    *,
    event_id: str | None = None,
    update_id: int | None = None,
) -> dict[str, Any] | None:
    """Fetch one webhook event by event_id or latest by update_id."""
    if event_id is None and update_id is None:
        raise ValueError("Provide event_id or update_id")
    with get_conn() as conn:
        cur = conn.cursor()
        if event_id is not None:
            cur.execute(
                "SELECT * FROM webhook_events WHERE event_id = %s",
                (event_id,),
            )
        else:
            cur.execute(
                "SELECT * FROM webhook_events WHERE update_id = %s ORDER BY received_at DESC LIMIT 1",
                (update_id,),
            )
        row = cur.fetchone()
        if not row:
            return None
        data = dict(row)
        if data.get("headers_json"):
            data["headers"] = json.loads(data["headers_json"])
        if data.get("payload_json"):
            data["payload"] = json.loads(data["payload_json"])
        return data


def list_webhook_events(*, limit: int = 50) -> list[dict[str, Any]]:
    """List recent webhook events."""
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM webhook_events ORDER BY received_at DESC LIMIT %s",
            (limit,),
        )
        rows = cur.fetchall()
    events: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        if item.get("headers_json"):
            item["headers"] = json.loads(item["headers_json"])
        if item.get("payload_json"):
            item["payload"] = json.loads(item["payload_json"])
        events.append(item)
    return events
