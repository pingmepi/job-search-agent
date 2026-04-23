# Agent Handoff

Last updated: 2026-04-23

## Purpose
This file is the short-lived operational handoff between sessions/windows when context gets full. Keep it concise and current.

## Snapshot
- Project: `job-search-agent`
- Linear project: https://linear.app/karans/project/job-search-agent-d5014a28b093
- Active phase: Phase 3 product workflow expansion in progress.
- Current test baseline: `251 passed, 37 skipped` with `.venv/bin/pytest -q -m "not live"`
- Current CI gate: `PASSED` with `.venv/bin/python main.py ci-gate` (fixture-based; all 5 thresholds green)
- Active execution ticket: `KAR-62` (Phase 3 product workflow expansion)
- Deployment: Railway (PostgreSQL + Docker). Webhook live.
- Pre-commit hooks: Active (ruff lint + format + pytest). Install with `bash scripts/install-hooks.sh`.

## What Was Just Completed (2026-04-23)
- **Enhanced Application Reporting**: Added `application_report.md` artifact generation with detailed grading (A-F), resume mutation summaries, and collateral status.
- **Automated Report Storage**: Integrated report uploads to the application-specific Google Drive folders alongside resumes and collateral.
- **Integrity Tooling**: Added `python main.py pipeline-check` for database and artifact consistency verification.
- **Telegram Vetting**: Implemented provenance tracking for Telegram-originated jobs, marking them as `user_vetted` in the DB.
- **Roadmap Refinement**: Reframed Phase 3 around product workflow expansion (scanner, dashboard, reports) to improve operator visibility.

## Previously Completed (2026-04-08)
- **Full codebase hardening (17 fixes).** Security: pickle→JSON token, SSRF protection, 5MB response cap, webhook secret redaction, chat_id allowlist, path traversal guard, URL encoding. Performance: connection pooling, parallel cost resolution. Correctness: Drive closure bug, lock race condition, dataclass fields, column validation, shared JSON util. Maintainability: decomposed eval handler, removed dead db_path, moved stale script.
- **32 new tests (251 total).** JSON utils (10), drafts (5), Google auth (6), SSRF (4), E2E pipeline (7 mock + 2 live).

## What Is Next
1. KAR-62: Phase 3 product surface expansion (Dashboard / Scanner).
2. KAR-72: Persist raw Telegram webhook events to `data/raw_events/`.
3. KAR-74: Default memory agent fallback behavior.
4. KAR-75: Formal JSON artifacts for job/resume/eval outputs.
5. KAR-76: Auto-create Linear application issues from pipeline output.

## Known Risks / Gaps
- Follow-Up Agent adapter only shows status list via `/status` — never generates or shows drafts to user.
- URL ingestion behavior is incomplete relative to PRD expectations.
- LOW-severity code smells from audit: unbounded JD cache, Image.open without `with`, singleton thread safety.

## Quick Start For New Agent
1. Read `BUILD_LOG.md` for full project evolution.
2. Read `TRACKER.md` for current ticket status.
3. Read `PRD.md` sections 2, 3, 6 for requirements.
4. Install hooks: `bash scripts/install-hooks.sh`
5. Run tests: `.venv/bin/pytest -q`
6. Run CI gate: `.venv/bin/python main.py ci-gate`
7. After opening PR: run `/review-check` to see Codex feedback, `/review-fix` to auto-address.

### Handoff Entry - 2026-04-23
- Completed: Application reports, Drive report upload, pipeline integrity check, Telegram vetting signal.
- Changed files: `app.py`, `core/report_markdown.py`, `integrations/drive.py`, `agents/inbox/executor.py`, `core/db.py`, `TRACKER.md`, `PRD.md`.
- Tests run: `pytest` (251 passed).
- Linear updates: `KAR-62` progress logged.
- Next recommended action: Implement `KAR-72` (Raw event persistence) or begin Dashboard UI.
