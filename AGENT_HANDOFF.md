# Agent Handoff

Last updated: 2026-04-08

## Purpose
This file is the short-lived operational handoff between sessions/windows when context gets full. Keep it concise and current.

## Snapshot
- Project: `job-search-agent`
- Linear project: https://linear.app/karans/project/job-search-agent-d5014a28b093
- Active phase: Phase 3 complete. Post-phase hardening and observability work done. Phase 4 planning.
- Current test baseline: `219 passed, 35 skipped` with `.venv/bin/pytest -q`
- Current CI gate: `PASSED` with `.venv/bin/python main.py ci-gate` (fixture-based; all 5 thresholds green)
- Active execution ticket: `KAR-62` (Pending)
- Deployment: Railway (PostgreSQL + Docker). Webhook live.
- Pre-commit hooks: Active (ruff lint + format + pytest). Install with `bash scripts/install-hooks.sh`.
- Codex: GitHub App auto-reviews PRs. Use `/review-check` and `/review-fix` commands.

## What Was Just Completed (2026-04-06 — 2026-04-08)
- **Google Drive & Calendar operational.** Shared OAuth module (`integrations/google_auth.py`), headless-safe with env-var bootstrap (`GOOGLE_TOKEN_B64`). CLI: `python main.py auth-google`. Tenacity retry on API calls.
- **Pre-commit hooks + ruff.** `scripts/pre-commit` runs lint, format check, and pytest on staged files. 62 lint issues fixed, 40 files reformatted. Codex review loop via `.claude/commands/review-fix.md`.
- **Profile Agent run logging.** `run_profile_agent()` logs tokens, latency, and ungrounded claim count to `runs` table. 2 new tests.
- **Article Agent run logging + signal persistence.** `run_article_agent()` logs runs and persists extracted signals to new `article_signals` table. 3 new tests.
- **6 bugfixes from python-patterns audit:**
  - None in JD skills crashes bullet_relevance scoring
  - Single quotes in company names break Drive API query
  - Malformed JSON from LLM crashes article agent
  - `update.message` None on edge-case Telegram updates
  - Executor `_parse_json_object` unhandled JSONDecodeError
  - Profile load failure silently degrades mutation quality

## What Is Next
1. KAR-62: Phase 3 SaaS readiness scoping.
2. Follow-Up Agent: Wire runner into Telegram adapter (P2 — runner exists with logging, just disconnected from UX).
3. Integration tests with real DB for agent run logging.
4. KAR-72: Persist raw Telegram webhook events.
5. KAR-74: Default memory agent fallback behavior.

## Known Risks / Gaps
- Follow-Up Agent adapter only shows status list via `/status` — never generates or shows drafts to user.
- URL ingestion behavior is incomplete relative to PRD expectations.
- LOW-severity code smells from audit: unbounded JD cache, Image.open without `with`, singleton thread safety.
- Draft LLM costs never tracked (`generation_id` not captured from draft calls).

## Quick Start For New Agent
1. Read `BUILD_LOG.md` for full project evolution.
2. Read `TRACKER.md` for current ticket status.
3. Read `PRD.md` sections 2, 3, 6 for requirements.
4. Install hooks: `bash scripts/install-hooks.sh`
5. Run tests: `.venv/bin/pytest -q`
6. Run CI gate: `.venv/bin/python main.py ci-gate`
7. Pick next ticket from `TRACKER.md` execution order.
8. After opening PR: run `/review-check` to see Codex feedback, `/review-fix` to auto-address.

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
