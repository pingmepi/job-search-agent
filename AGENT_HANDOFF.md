# Agent Handoff

Last updated: 2026-02-16

## Purpose
This file is the short-lived operational handoff between sessions/windows when context gets full. Keep it concise and current.

## Snapshot
- Project: `job-search-agent`
- Linear project: https://linear.app/karans/project/job-search-agent-d5014a28b093
- Active phase: Post-review stabilization + remaining feature completion
- Current test baseline: `66 passed` with `.venv/bin/pytest -q`
- Active execution ticket: `KAR-49` (In Progress, due 2026-02-22)
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

## What Is Next
1. KAR-49: Persist follow-up progression (`follow_up_count` updates).
2. KAR-51: Add integration tests for pipeline + adapter with mocks.
3. KAR-50: URL ingestion fetch path + screenshot fallback UX.
4. KAR-57: Complete eval logging fields + full token accounting.
5. KAR-53: Persist fit score from resume selection.

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
