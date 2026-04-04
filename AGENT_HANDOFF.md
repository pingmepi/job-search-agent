# Agent Handoff

Last updated: 2026-04-03

## Purpose
This file is the short-lived operational handoff between sessions/windows when context gets full. Keep it concise and current.

## Snapshot
- Project: `job-search-agent`
- Linear project: https://linear.app/karans/project/job-search-agent-d5014a28b093
- Active phase: Phase 3 complete. V2 mutation pipeline + ArticleAgent shipped. Phase 4 planning.
- Current test baseline: `222+ passed` with `.venv/bin/pytest -q` (new test files added for ArticleAgent and bullet relevance since last count)
- Current CI gate: `PASSED` with `.venv/bin/python main.py ci-gate` (fixture-based; all 5 thresholds green)
- Active execution ticket: `KAR-62` (Pending)
- Deployment: Railway (PostgreSQL + Docker). Webhook live.
- Milestone targets:
  - Phase 0 (2026-03-01) — complete
  - Phase 1 (2026-03-15) — complete
  - Phase 2 (2026-04-05) — in progress
  - Phase 3 (2026-04-30)

## What Was Just Completed
- **KAR-73: ArticleAgent.** New `agents/article/agent.py` — summarizes article content and surfaces job-search signals (companies, hiring, skills, funding). Router integration + 4 unit tests.
- **V2 mutation pipeline.** REWRITE/SWAP/GENERATE ops with JD-relevant bullet bank pre-filtering (top-12), profile context injection, and selective revert on truthfulness failure.
- **Bullet relevance scoring.** `agents/inbox/bullet_relevance.py` — tag overlap (60%) + keyword overlap (40%) scoring for JD-aware bullet selection.
- **Per-bullet truthfulness guard.** Granular per-bullet checking replaces all-or-nothing fallback. Common-word skip set reduces false positives.
- **Executor simplification.** Extracted `_load_profile` helper, fixed `reverted_count` scope bug, `Counter` usage.
- **run_steps audit trail.** Per-step input/output logging via `run_steps` table. `python main.py runs <id> --steps`.
- **PostgreSQL migration.** SQLite → PostgreSQL (`psycopg2`) for production concurrency.
- **Operations fixes.** Railway PORT healthcheck, stdout logging, PDF delivery via Telegram, truthfulness false positive reduction.

## What Is Next
1. KAR-62: Phase 3 SaaS readiness scoping.
2. KAR-72: Persist raw Telegram webhook events to `data/raw_events/`.
3. KAR-74: Default memory agent fallback behavior.

## Known Risks / Gaps
- URL ingestion behavior is incomplete relative to PRD expectations (readability fallback, field extraction hardening).
- Pre-existing test failure in `test_run_pipeline_compile_fallback_rolls_back_to_base_resume` may be resolved by single-page enforcement removal — needs verification.
- `.venv` not present in repo — tests must be run after recreating the virtual environment.

## Quick Start For New Agent
1. Read `BUILD_LOG.md` for full project evolution.
2. Read `TRACKER.md` for current ticket status.
3. Read `PRD.md` sections 2, 3, 6 for requirements.
4. Run tests: `.venv/bin/pytest -q`
5. Run CI gate: `.venv/bin/python main.py ci-gate`
6. Pick next ticket from `TRACKER.md` execution order.
7. Update `TRACKER.md`, this file, and `BUILD_LOG.md` after each phase.

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
