# Agent Handoff

Last updated: 2026-04-30

## Purpose

Short-lived operational handoff between sessions. Keep this file concise. Move durable history to `BUILD_LOG.md` and architecture/policy choices to `docs/decisions.md`.

## Snapshot

- Project: `job-search-agent`
- Linear project: https://linear.app/karans/project/job-search-agent-d5014a28b093
- Active focus: out-of-scope JD hardening on `fix/out-of-scope-gate` (PR #31 scope)
- Test baseline (`.venv/bin/pytest -q -m "not live"`): `318 passed, 39 skipped, 2 deselected`
- CI gate (`.venv/bin/python main.py ci-gate`): `PASSED` (compile 100%, forbidden 0, edit violations 0, avg cost $0.0683, avg latency 33.4s)
- Deployment: Railway (Docker + PostgreSQL), Telegram webhook live

## What Completed This Session (2026-04-30)

- Soft-eval parser hardening fixed fenced-JSON judge outputs that were silently forcing soft scores to `0.0`.
- Regression runner gained preflight env checks and optional soft-score floor assertions.
- CI gate DB stats query fixed for psycopg2 cursor usage.
- Persona-mutation incident RCA completed; gates 1, 2, 4, and 5 shipped on `fix/out-of-scope-gate`.

## Current Risks / Gaps

- Out-of-scope protection from the persona-mutation incident is not fully closed: gate #3 (JD role allowlist) is still pending.
- Eval report artifact loading still depends on local `runs/artifacts/*`; Railway redeploys can drop historical files.
- Follow-Up Agent runner exists, but Telegram adapter still primarily exposes status instead of draft-generation UX.
- Google Calendar/Drive steps can fail on expired OAuth tokens; run `python main.py auth-google` when needed.

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
