# Agent Handoff

Last updated: 2026-02-16

## Purpose
This file is the short-lived operational handoff between sessions/windows when context gets full. Keep it concise and current.

## Snapshot
- Project: `job-search-agent`
- Linear project: https://linear.app/karans/project/job-search-agent-d5014a28b093
- Active phase: Post-review stabilization + remaining feature completion
- Current test baseline: `85 passed` with `.venv/bin/pytest -q` (2026-02-16)
- Current CI gate: `FAILED` with `.venv/bin/python main.py ci-gate` (compile success rate `0.0%`, threshold `95%`)
- Active execution ticket: `KAR-56` (Todo, due 2026-03-10)
- Milestone targets:
  - Phase 0 (2026-03-01)
  - Phase 1 (2026-03-15)
  - Phase 2 (2026-04-05)
  - Phase 3 (2026-04-30)

## What Was Just Completed
- Resume mutation edits constrained to editable markers.
- Regression test added for edit-scope guard.
- Compiled PDFs persisted outside temp dir (`runs/artifacts/`).
- Compile eval checks path existence.
- Telegram text/photo handlers run full pipeline path (with upload/calendar skipped in adapter).
- Blocking sync pipeline work moved off event loop via `asyncio.to_thread`.
- Eval fields now compute real edit-scope and forbidden-claim metrics.
- Telegram bot credentials wired locally via `.env` and example env updated with `TELEGRAM_BOT_USERNAME`.
- `Settings` now includes `telegram_bot_username` for explicit bot identity configuration.
- Telegram ingestion migrated from polling to webhook service (`/telegram/webhook`) with secret-token validation.
- Added webhook runtime (`app.py`), webhook registration script (`set_webhook.sh`), and health/auth tests.
- Follow-up progression now persists via DB updates (`follow_up_count` + `last_follow_up_at`) when drafts are generated.
- Added integration tests for inbox pipeline persistence + Telegram adapter route execution using mocks.
- URL ingestion now fetches page content from links and requests screenshot fallback when extraction fails.
- Eval logs now include full LLM token/cost accounting (OCR cleanup, JD extraction, mutation, drafts) plus `keyword_coverage`.
- Resume selection now persists `fit_score` on `jobs` rows using keyword overlap.
- Telegram adapter now supports env-guarded production toggles for Drive upload and Calendar events (`TELEGRAM_ENABLE_DRIVE_UPLOAD`, `TELEGRAM_ENABLE_CALENDAR_EVENTS`).
- Compile step now rolls back to base resume artifact if mutated LaTeX compile fails (`compile_rollback_used` eval field).

## What Is Next
1. KAR-56: Grounding evals + forbidden-claim coverage.
2. KAR-52: OCR hardening and failure handling.
3. KAR-58: Scheduled follow-up detection runner.
4. KAR-59: Soft evals (resume relevance + JD extraction accuracy).
5. KAR-60: Success criteria gates + CI threshold enforcement.

## Known Risks / Gaps
- Follow-up tier may repeat because progression is not persisted yet.
- URL ingestion behavior is incomplete relative to PRD expectations.
- Adapter runs with upload/calendar disabled in chat flow by design for now.
- PRD traceability expanded; new backlog items KAR-52..KAR-62 must be tracked in future phase updates.
- Production deployment now requires HTTPS + reverse proxy and Telegram webhook registration.

## Quick Start For New Agent
1. Read `TRACKER.md`.
2. Read `PRD.md` sections 2, 3, 6.
3. Run tests: `.venv/bin/pytest -q`.
4. Pick next ticket from `TRACKER.md` execution order.
5. Update both `TRACKER.md` and this file after each phase.

## Handoff Template
Use this block when ending a work phase:

```md
### Handoff Entry - YYYY-MM-DD
- Completed:
- Changed files:
- Tests run:
- Linear updates:
- Outstanding blockers:
- Next recommended action:
```
