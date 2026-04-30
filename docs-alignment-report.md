# Docs Alignment Report — job-search-agent

Scanned 9 doc surfaces (README.md, PRD.md, AGENTS.md, AGENT_HANDOFF.md, BUILD_LOG.md, TRACKER.md, .env.example, and `docs/*.md`) against the current code state on 2026-04-30. Repo HEAD: `7406eed` (working tree has uncommitted fixes from this audit).

## Summary
- HIGH: 0     (would mislead someone in setup, usage, or an interview answer)
- MED:  4     (noticeable, can trip a careful reader, doesn't break core understanding)
- LOW:  2     (cosmetic / stale-dated / minor inconsistency)

## Resolved This Pass (2026-04-30)
- **HIGH config-env-drift** — Added `TELEGRAM_ALLOWED_CHAT_IDS=` to [.env.example](.env.example) with comment on the comma-separated chat-ID allowlist.
- **HIGH config-env-drift** — Added `MAX_CONDENSE_RETRIES=3` to [.env.example](.env.example) under the LLM section.
- **MED version-drift** — Updated [PRD.md:6](PRD.md#L6) header and [PRD.md:34](PRD.md#L34) §2 preamble to declare four agents (Inbox, Profile, Follow-Up, Article) with pointer to `docs/PROJECT_OVERVIEW.md` as canonical.

## Findings

### [MED] stale-instruction — hardcoded user-specific path in setup docs
**File:** [docs/README.md:73](docs/README.md#L73)
**Says:** Step 3 setup block uses `cd /Users/karan/Desktop/job-search-agent`.
**Actually:** This path is the original author's local checkout. New contributors copy-pasting this command will fail. The README runbook is the canonical setup guide for the repo.
**Fix:** Replace with `cd <path-to-your-checkout>` or drop the `cd` line; environment cloning should be path-agnostic.

### [MED] stale-instruction — README quickstart `DATABASE_URL` example omits credentials
**File:** [README.md:49](README.md#L49)
**Says:** "`DATABASE_URL` — PostgreSQL connection string (e.g. `postgresql://localhost/inbox_agent`)"
**Actually:** [.env.example:30](.env.example#L30) uses `postgresql://user:password@localhost:5432/inbox_agent`. The README example will fail on any non-trust-auth Postgres install (which is the default on macOS Homebrew, Docker, Railway, and most cloud Postgres). New users following the quickstart will hit auth errors.
**Fix:** Use the full `postgresql://user:password@localhost:5432/inbox_agent` form to match `.env.example`, or point at `.env.example` for the canonical template.

### [MED] stale-comments-docstrings — test-baseline counts likely stale after recent commits
**File:** [AGENT_HANDOFF.md:12](AGENT_HANDOFF.md#L12)
**Says:** "Current test baseline: `251 passed, 37 skipped`."
**Actually:** This baseline figure also appears in [docs/PROJECT_OVERVIEW.md:304-305](docs/PROJECT_OVERVIEW.md#L304-L305) as 251 passing / 37 skipped. After commits `bf90a59` (feedback loop telemetry + regression runner) and `7406eed` (out-of-scope gate, persona lock, skill-empty fallback) added new tests, this number is likely stale — neither doc was updated.
**Fix:** Re-run `.venv/bin/pytest -q -m "not live"` and update both files with the current pass/skip counts.

### [MED] stale-comments-docstrings — PROJECT_OVERVIEW "What's Next" doesn't reflect current incident work
**File:** [docs/PROJECT_OVERVIEW.md:354-368](docs/PROJECT_OVERVIEW.md#L354-L368)
**Says:** Immediate priorities are Follow-Up Agent UX and draft cost tracking.
**Actually:** [AGENT_HANDOFF.md:57+](AGENT_HANDOFF.md#L57) documents the 2026-04-30 persona-mutation incident (run-144b1afaef4a) and identifies five missing pipeline gates. Branch `fix/out-of-scope-gate` and commit `7406eed` are actively addressing these — but the public PROJECT_OVERVIEW still presents Follow-Up UX as the headline next item.
**Fix:** Add an "Immediate" bullet for the persona-lock / out-of-scope gate work or note that priorities have shifted.

### [LOW] version-drift — "Current metrics (2026-04-08)" snapshot is stale-dated
**File:** [docs/PROJECT_OVERVIEW.md:275](docs/PROJECT_OVERVIEW.md#L275)
**Says:** "Current metrics (2026-04-08): Compile success 100%, Forbidden 0, Edit violations 0, Avg cost $0.07, Avg latency 33s."
**Actually:** Today is 2026-04-30; over three weeks have elapsed and the CI gate has run many times since (still PASSING per AGENT_HANDOFF.md). The numbers may still be accurate but the date label undermines the "current" claim.
**Fix:** Either re-run `python main.py ci-gate` and refresh the date, or relabel as "Snapshot 2026-04-08" and link to the current report.

### [LOW] version-drift — "Timeline | Duration | 51 days" treats 2026-04-08 as project end
**File:** [docs/PROJECT_OVERVIEW.md:302](docs/PROJECT_OVERVIEW.md#L302)
**Says:** "Timeline | Duration | 51 days (2026-02-16 → 2026-04-08)"
**Actually:** The project is still active — `git log` shows commits through 2026-04-30 including out-of-scope gate work. The 51-day figure was a milestone metric, but the framing implies the project ended.
**Fix:** Reframe as "Initial build duration" or update end date to current.

## Clean Areas

- README.md `## Commands` section fully matches `main.py` subcommand parsing (verified line-by-line; 11 commands, all argparse paths exist).
- `.env.example` LLM, Telegram, Google, Cost, Database sections — all variables read by `core/config.py` are now present (`TELEGRAM_ALLOWED_CHAT_IDS` and `MAX_CONDENSE_RETRIES` added 2026-04-30).
- `docs/README.md` `## 6) Start Webhook Service` and `## 6c) Pipeline Integrity Check` sections match `app.py` and `core/pipeline_checks.py` implementations.
- All 5 master resume templates referenced in PROJECT_OVERVIEW.md (`AI, Technical, Growth, Agentic, Founders`) exist on disk under `resumes/master_*.tex`.
- 5 PostgreSQL tables (`jobs`, `runs`, `run_steps`, `webhook_events`, `article_signals`) documented in PROJECT_OVERVIEW match `core/db.py` DDL.
- 56-entry bullet bank claim in PROJECT_OVERVIEW.md matches actual `profile/bullet_bank.json` length.
- Dockerfile `python:3.11-slim` base image matches PROJECT_OVERVIEW deployment claim.
- Pre-commit hook installer `bash scripts/install-hooks.sh` referenced in AGENT_HANDOFF and PROJECT_OVERVIEW exists at `scripts/install-hooks.sh`.
- `python main.py pipeline-check` referenced in docs/README.md and AGENT_HANDOFF — implementation present in `core/pipeline_checks.py` and main.py:297-313.
- PRD.md agent-count claim now matches code reality (four agents) as of 2026-04-30.
- Dead-link scan: 0 dead relative markdown links across 118 scanned markdown files.
