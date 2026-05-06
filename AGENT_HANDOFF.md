# Agent Handoff

Last updated: 2026-05-05

## Purpose

Short-lived operational handoff between sessions. Keep this file concise. Move durable history to `BUILD_LOG.md` and architecture/policy choices to `docs/decisions.md`.

## Snapshot

- Project: `job-search-agent`
- Linear project: https://linear.app/karans/project/job-search-agent-d5014a28b093
- Active focus: `fix/telegram-length-eval-logging` — Telegram length safety refactored into `core/telegram_utils.py`; recruiter demo onboarding mode shipped (PR #33 follow-ups still open, see below)
- Test baseline (`.venv/bin/pytest -q -m "not live"`): `330 passed, 41 skipped`
- CI gate (`.venv/bin/python main.py ci-gate`): `PASSED` (compile 100%, forbidden 0, edit violations 0, avg cost $0.0683, avg latency 33.4s)
- Deployment: Railway (Docker + PostgreSQL), Telegram webhook live

## What Completed This Session (2026-05-05)

- Recruiter demo onboarding mode (`TELEGRAM_DEMO_MODE`) added: toggleable `/start` flow surfaces demo copy and bypasses `TELEGRAM_ALLOWED_CHAT_IDS` when enabled (commits `337e36a`, `dbf469a`).
- Docs-alignment fixes from the 2026-05-02 audit applied to `.env.example` (deduped keys), `core/contracts.py` (`SCHEMA_VERSION = "1.1"`), and test-count snapshots (commit `21be2cf`).
- Re-ran codebase-docs-alignment audit; 1 HIGH (README command list), 4 MED, 3 LOW. Findings applied across README, CHANGELOG, TRACKER, PROJECT_OVERVIEW, setup-and-test, and this file.

## Previous Session (2026-04-30)

- Soft-eval parser hardening fixed fenced-JSON judge outputs that were silently forcing soft scores to `0.0`.
- Regression runner gained preflight env checks and optional soft-score floor assertions.
- CI gate DB stats query fixed for psycopg2 cursor usage.
- Persona-mutation incident RCA completed; gates 1, 2, 4, and 5 shipped on `fix/out-of-scope-gate`.

## Current Risks / Gaps

- Out-of-scope protection from the persona-mutation incident is not fully closed: gate #3 (JD role allowlist) is still pending.
- Eval report artifact loading still depends on local `runs/artifacts/*`; Railway redeploys can drop historical files.
- Follow-Up Agent runner exists, but Telegram adapter still primarily exposes status instead of draft-generation UX.
- Google Calendar/Drive steps can fail on expired OAuth tokens; run `python main.py auth-google` when needed.

## Unresolved Review Comments — PR #33 (merged, follow-up branch needed)

Three P2 issues raised by Greptile on PR #33 were never addressed before merge. All in `agents/inbox/adapter.py`:

1. **Silent fallback masks missing attribute** — `agents/inbox/adapter.py:52` and `:116` use `getattr(settings, "telegram_demo_mode", False)`. `Settings` is a typed dataclass that always declares the field; direct attribute access (`settings.telegram_demo_mode`) would raise a clear `AttributeError` on a stale or wrong settings object instead of silently returning `False`.
2. **`demo_intro_sent` set unconditionally** — `agents/inbox/adapter.py:341` writes `context.user_data["demo_intro_sent"] = True` regardless of whether demo mode is enabled. If an operator later toggles demo mode on, users who already ran `/start` will skip the auto-greeting forever. Guard with `if _is_demo_mode_enabled():`.
3. **Greeting regex captures `start`/`help`** — `agents/inbox/adapter.py:98` `_GREETING_PATTERN` matches plain-text `start` and `help` as greetings. In demo mode, typing `help` (no slash) triggers the demo intro on first use, then falls through to the router on subsequent uses instead of returning help content. Remove `start` and `help` from the alternation.

## Next Recommended Actions

1. Implement gate #3: JD-role allowlist check immediately after `jd_extract`.
2. Add one regression case that must exit `out_of_scope` for a non-target role JD.
3. Make eval report loading DB-first with filesystem fallback.
4. Wire Follow-Up draft generation into Telegram UX (`/followup` flow).

## Where Detailed Context Lives

- Incident and timeline history: `BUILD_LOG.md` (2026-04-23, 2026-04-29, 2026-04-30 entries)
- Architecture/guardrail decisions: `docs/decisions.md`
- Operational commands and setup: `docs/RUNBOOK.md`
- Project/issue status: `TRACKER.md`
