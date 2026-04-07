# Build Log

Chronological record of how the Job Search Agent was built — decisions, issues, solutions, and milestones. Updated as the codebase evolves.

Last updated: 2026-04-08

---

## Timeline

### Project Init (2026-02-16)

**Commit:** `e2569b3` — Implement webhook-based Telegram service

The project started as a Telegram bot that receives job descriptions (text, URL, or screenshot) and produces tailored application packages. The initial commit established:
- FastAPI webhook endpoint for Telegram updates (no polling)
- Basic message routing
- Core project structure: `agents/`, `core/`, `docs/`

### Core Hardening Sprint (2026-02-17)

**Commits:** `667a13f`, `c4c993d`, `40f2d5e`, `a4703b5`

Implemented 7 hardening tickets in a single day (KAR-49/50/51/53/54/55/57):
- **URL ingestion** with fetch + screenshot fallback when extraction fails
- **OCR pipeline** with confidence thresholds and low-quality screenshot fallback
- **Follow-up scheduler** with dry-run/loop controls and escalation tiers
- **Profile grounding checks** to validate agent responses against source data
- **Eval logging** for tracking pipeline quality
- **Webhook E2E tests** with realistic Telegram payloads

**Issue hit:** Malformed webhook payloads caused uncaught exceptions. Fixed by returning 400 status with validation.

**Issue hit:** OCR confidence was unreliable on low-quality screenshots. Added screenshot fallback UX — bot asks user for a clearer image.

### Operational Docs (2026-02-21)

**Commit:** `d623e0a` — Runtime runbooks, troubleshooting, monitoring

Added `docs/setup-and-test.md`, `docs/troubleshooting-and-debugging.md`, and monitoring scripts. These became the canonical ops references.

### Pipeline Intelligence (2026-02-25)

**Commit:** `20da486` — Wire soft evals, real costs, single-page enforcement, unlimited mutations

Major capability jump in a single commit:

- **Removed 3-mutation cap.** Original design limited resume edits to 3 bullets — too restrictive for full tailoring. Switched to unlimited mutations within editable regions, governed by density rules (max 5 bullets/role, min 1).
- **Soft evals integrated.** `score_resume_relevance` and `score_jd_accuracy` now run after every mutation for quality signal.
- **Single-page enforcement.** LLM-based condensing loop (2 retries) + margin adjustment fallback to keep resumes to one page.
- **Real cost tracking.** OpenRouter generation API for actual USD costs (deferred batch resolution to avoid inline latency).
- **Artifact bundling.** Per-application folders at `runs/artifacts/{company}_{role}_{hash}/`.
- **Drive/Calendar toggles.** Feature flags via `.env` for Google integrations.

**Test baseline:** 114 passing.

### Phase 1-3 Sprint (2026-03-04 to 2026-03-05)

**Commits:** `2110aca`, `b39a396`, `578b728` and planning docs

All three phases designed and implemented in a two-day sprint:

**Phase 1 — Intake Reliability:**
- Webhook event persistence with `webhook_events` table and lifecycle states (received → processing → processed → failed)
- Replay CLI: `python main.py replay-webhook --event-id <id>`
- Deterministic routing contracts

**Phase 2 — Resume Tailoring Safety:**
- `select_base_resume_with_details()` with fit-score breakdown
- Truthfulness guards: forbidden-claim detection for metrics and entities
- One-page enforcement with terminal-state fields (`single_page_target_met`, `compile_outcome`)
- Deterministic fallback-to-base when constraints unmet

**Phase 3 — Collateral & Delivery:**
- Outreach collateral generation: email, LinkedIn DM (<300 chars), referral template
- Google Drive upload with folder structure `Jobs/{Company}/{Role}/`
- Google Calendar integration for application tracking
- Production toggles for Drive/Calendar features

**Decision:** Completed all three phases same week rather than spacing them across milestones. The codebase was small enough that sequential implementation was faster than context-switching between phases.

### Quality Gates & Architecture Overhaul (2026-03-16)

**Commits:** `1ffb5ae` (KAR-60), `f95fa43` (KAR-61)

Two major structural changes:

**KAR-60 — Fixture-based CI Gating:**
- 12 curated eval fixtures replacing live-DB-dependent gating
- 5 thresholds: compile ≥95%, forbidden_claims=0, edit_violations=0, avg_cost ≤$0.15, avg_latency ≤60s
- CI gate: `python main.py ci-gate` — deterministic, reproducible
- 59 new tests. Baseline: 173 passing.

**KAR-61 — Planner/Executor Separation:**
- Monolithic `run_pipeline()` split into:
  - `agents/inbox/planner.py` — deterministic tool plan assembly, zero LLM calls
  - `agents/inbox/executor.py` — 12 step handlers with retry logic and graceful degradation
- Conditional step routing: OCR/collateral/upload/calendar based on input type
- `agents/inbox/agent.py` kept as thin backward-compatible adapter
- 49 new tests (25 planner, 24 executor). Baseline: 222 passing.

**Decision:** Planner has zero LLM calls by design. All intelligence lives in the executor. This makes the plan deterministic and testable without mocking LLM responses.

### Production Deployment (2026-03-31)

**Commits:** `e18a794`, `de69cf1` (PR #5)

- **SQLite → PostgreSQL migration.** SQLite couldn't handle concurrent webhook processing in production. Migrated to PostgreSQL via `psycopg2`. Schema preserved, queries adapted.
- **Railway deployment.** Dockerfile with python:3.11-slim, Tesseract OCR, TexLive (minimal — ~400MB, not full 3GB install).
- **railway.json** configuration for build/deploy.
- Test conftest.py updated to auto-skip DB tests when `DATABASE_URL` unset.

### Operations Fixes (2026-04-02)

**Commits:** `d8c3a5c`, `f7a3c1b`, `16c1cda`, `244fa09`, `22eb3bf`

First week of production surfaced several issues:

**Issue:** Railway healthcheck timeout. App listened on `WEBHOOK_PORT` (8000) but Railway injects a dynamic `PORT`.
**Fix:** `d8c3a5c` — Fallback chain: `PORT` → `WEBHOOK_PORT` → `8000`.

**Issue:** All Python logging showed as `[err]` in Railway dashboard.
**Fix:** `244fa09` — Route logging to stdout so Railway tags them as `[inf]`.

**Issue:** Users couldn't see compiled artifacts — bot only said "done" without attaching files.
**Fix:** `16c1cda` — Send PDF resume and collateral drafts back via Telegram message.

**Issue:** Truthfulness guard flagged JD-sourced terms as fabricated claims (false positives).
**Fix:** `22eb3bf` — Added JD text to the allowed corpus for truthfulness checks.

**Decision:** `22eb3bf` also removed single-page enforcement entirely. Multi-page resumes are now accepted with page count tracked as metadata. The condensing loop added complexity without clear value — most resumes fit one page naturally, and forcing it sometimes hurt readability.

**Feature:** `22eb3bf` — Added `python main.py runs` CLI for inspecting run history.

### V2 Mutation Pipeline (2026-04-02)

**Commits:** `2712592`, `70cd562`, `6177cee`, `43d56bf`, `cfccfa3`

Major upgrade to resume mutation quality:

**run_steps audit trail** (`2712592`):
- New `run_steps` PostgreSQL table logging per-step input/output, timing, and errors
- `python main.py runs <run_id> --steps` for full trace inspection
- Critical for debugging mutation quality issues

**Bullet bank relevance scoring** (`70cd562`):
- `agents/inbox/bullet_relevance.py` scores bullets against JD
- Tag overlap (60% weight) + keyword overlap (40% weight)
- `select_relevant_bullets()` returns top-N with scores
- Prevents sending irrelevant bullets to the LLM, improving mutation quality and reducing token usage

**Per-bullet truthfulness guard** (`6177cee`):
- Replaced all-or-nothing truthfulness check with per-bullet granularity
- Common-word skip set (Product, Senior, Led, etc.) to prevent false flags on generic terms
- Multi-word entity detection preserved (e.g., "Goldman Sachs" still caught)
- `allowed_tools` parameter integrated so tool names aren't flagged

**V2 mutation operations** (`43d56bf`):
- Three operation types: REWRITE (modify existing), SWAP (replace with bank entry), GENERATE (create new from profile)
- Bullet bank pre-filtered by JD relevance (top-12 selection)
- Profile positioning + allowed tools sent as LLM context
- Selective revert: only flagged bullets removed, clean mutations kept (was: full rollback to base resume)
- Full audit trail: mutation types, bank stats, per-bullet truthfulness results

**Executor simplification** (`cfccfa3`):
- Extracted `_load_profile(ctx)` helper — was duplicated 3x across handlers
- Fixed `reverted_count` scope bug — variable defined inside conditional block, referenced outside (potential NameError)
- Replaced manual counter loops with `collections.Counter`

### ArticleAgent (2026-04-03)

**Commit:** `d8f21e4` (KAR-73)

When the router detects article-style content (2+ indicators like "newsletter", "published", "subscribe", "medium.com" AND zero JD indicators), it previously sent a dead-end rejection message. Now routes to a real agent:

- `agents/article/agent.py` — `summarize(text)` calls Claude with JSON mode
- Returns formatted summary (3-4 bullets) + job-search signals (companies hiring, skills in demand, funding events)
- Adapter integration with graceful error handling
- 4 unit tests covering happy path, empty signals, missing keys, malformed JSON

### Google Drive & Calendar Integration (2026-04-06)

**Commits:** `8814640`, `03886ee`

Made the existing Drive/Calendar code operational for headless Railway deployment:

- `integrations/google_auth.py` — shared OAuth module with three modes: headless (load/refresh), interactive (browser), env-var bootstrap (GOOGLE_TOKEN_B64 decoded to disk on startup)
- Consolidated from two separate token files to a single `google_token.pickle` with both Drive + Calendar scopes, one env var
- `python main.py auth-google` CLI command for local token bootstrap
- Tenacity retry on Google API calls (429/500/503)
- Executor captures calendar event IDs and stores them in `jobs` table
- `docs/google-oauth-setup.md` — step-by-step setup guide

### Pre-commit Hooks & Code Quality (2026-04-07)

**Commit:** `61de9ea`

Zero automated code quality gates existed. Added two-layer self-correction loop:

**Layer 1 — Local pre-commit hook:**
- `scripts/pre-commit` — runs ruff lint, ruff format check, and pytest on staged `.py` files
- `scripts/install-hooks.sh` — portable installer (works from worktrees via `--git-common-dir`)
- `ruff>=0.4.0` added as dev dependency with config: `E/F/W/I` rules, line-length 100
- Fixed 62 lint issues (33 unused imports, 25 unsorted imports, 3 empty f-strings, 1 dead variable, 1 unused import)
- Reformatted 40 files for consistent style

**Layer 2 — Codex review loop:**
- `.claude/commands/review-fix.md` — reads Codex PR comments via `gh api`, applies fixes, pushes
- `.claude/commands/review-check.md` — read-only version showing comments grouped by file

### Agent Run Logging (2026-04-07)

**Commit:** `1580c49`

Profile and Article agents had zero observability. Added run logging to match Inbox Agent patterns:

**Profile Agent:**
- `answer_with_telemetry()` — returns LLMResponse alongside results (backward-compat preserved)
- `run_profile_agent()` — generates run_id, calls `insert_run`/`complete_run` with tokens, latency, ungrounded claim count as eval result
- Adapter wired to use logged version

**Article Agent:**
- `summarize_with_telemetry()` — returns LLMResponse alongside results
- `run_article_agent()` — generates run_id, logs run, persists signals to new `article_signals` table
- New `article_signals` table in `core/db.py` for job-search signal persistence
- Adapter now shows run_id to user

5 new tests (2 profile, 3 article) covering success and failure paths.

### Bugfixes (2026-04-07)

**Commits:** `8abced8`, `1b9d822`

Production crash and edge case hardening from python-patterns audit:

| Issue | Root Cause | Fix |
|-------|-----------|-----|
| `resume_mutate` crash: `'in <string>' requires string as left operand, not NoneType` | LLM-extracted JD skills can contain None values | Guard `_normalize()` against None, filter None from skills list |
| Company names with `'` break Drive API query (e.g., O'Reilly) | Unescaped single quotes in query string interpolation | Escape quotes before interpolation |
| Malformed JSON from LLM crashes article agent | Unguarded `json.loads` on LLM response | Catch JSONDecodeError, return empty results |
| `update.message` could be None on edge-case Telegram updates | Certain update types have no message attribute | Early return guard on all 5 handlers |
| Executor `_parse_json_object` unhandled JSONDecodeError | Final fallback `json.loads` not wrapped in try/except | Wrap so it falls through to ValueError (expected by retry logic) |
| Profile load failure silently degrades mutation quality | Bare except returns empty dict | Log warning so it's visible in telemetry |

---

## Issues & Solutions

| Date | Issue | Root Cause | Solution | Commit |
|------|-------|-----------|----------|--------|
| 2026-02-17 | Malformed webhook payloads crash server | No payload validation | Return 400 on bad payloads | `40f2d5e` |
| 2026-02-17 | OCR confidence unreliable on poor screenshots | Tesseract limits | Screenshot fallback UX | `667a13f` |
| 2026-02-25 | 3-mutation cap too restrictive | Original design constraint | Unlimited with density rules | `20da486` |
| 2026-03-16 | CI gate flaky (depends on live DB state) | Historical dev noise in DB | Fixture-based deterministic gating | `1ffb5ae` |
| 2026-03-31 | SQLite can't handle concurrent webhooks | File-level locking | PostgreSQL migration | `e18a794` |
| 2026-04-02 | Railway healthcheck timeout | Wrong PORT env var | Dynamic PORT fallback chain | `d8c3a5c` |
| 2026-04-02 | All logs show as errors in Railway | stderr routing | Route to stdout | `244fa09` |
| 2026-04-02 | Users can't see compiled artifacts | No Telegram file delivery | Send PDF + drafts via bot | `16c1cda` |
| 2026-04-02 | Truthfulness flags JD terms as fabricated | JD not in allowed corpus | Add JD text to corpus | `22eb3bf` |
| 2026-04-02 | reverted_count NameError in edge case | Variable scoped inside conditional | Extract to outer scope | `cfccfa3` |
| 2026-04-03 | Article content hits dead-end rejection | No article handler | ArticleAgent with summarization | `d8f21e4` |
| 2026-04-07 | resume_mutate crash on None JD skills | LLM returns None in skills list | Guard _normalize(), filter None | `8abced8` |
| 2026-04-07 | Drive API breaks on O'Reilly-style names | Unescaped single quotes in query | Escape quotes before interpolation | `1b9d822` |
| 2026-04-07 | Article agent crash on malformed JSON | Unguarded json.loads on LLM response | Catch JSONDecodeError, return empty | `1b9d822` |
| 2026-04-07 | Telegram handler crash on edge-case updates | update.message can be None | Early return guard on all handlers | `1b9d822` |

## Architectural Decisions

| # | Date | Decision | Rationale |
|---|------|----------|-----------|
| 1 | 2026-02-16 | Webhook-first (no polling) | Lower latency, Railway-compatible, production-grade |
| 2 | 2026-02-25 | Unlimited mutations with density rules | 3-cap was too restrictive; density rules prevent bloat |
| 9 | 2026-04-06 | Single OAuth token for Drive + Calendar | Two separate tokens/env vars was unnecessary duplication |
| 10 | 2026-04-07 | Pre-commit hooks over CI-only checks | Catch lint/test issues before they're pushed; faster feedback |
| 3 | 2026-02-25 | Deferred cost resolution | Inline cost API calls added 1-2s latency per LLM call |
| 4 | 2026-03-05 | Sprint all 3 phases in 2 days | Small codebase, faster than context-switching |
| 5 | 2026-03-16 | Deterministic planner (zero LLM calls) | Testable without mocks, reproducible plans |
| 6 | 2026-03-16 | Fixture-based CI gating | Live DB metrics had historical noise from dev runs |
| 7 | 2026-03-31 | SQLite → PostgreSQL | Concurrent webhook processing needed file-lock-free DB |
| 8 | 2026-04-02 | Remove single-page enforcement | Added complexity without value; most resumes fit naturally |

## Milestones

| Milestone | Date | Key Metric |
|-----------|------|------------|
| First working bot | 2026-02-16 | Webhook receives and routes messages |
| Core hardening complete | 2026-02-17 | 7 tickets, OCR/URL/follow-up pipelines |
| Pipeline intelligence | 2026-02-25 | 114 tests, real cost tracking, soft evals |
| Phases 1-3 complete | 2026-03-05 | Full intake → resume → collateral pipeline |
| Quality gates + architecture | 2026-03-16 | 222 tests, CI gate green, planner/executor split |
| Production deployment | 2026-03-31 | PostgreSQL + Railway + Docker |
| V2 mutation pipeline | 2026-04-02 | REWRITE/SWAP/GENERATE, per-bullet truthfulness |
| ArticleAgent | 2026-04-03 | 4th agent type, article summarization |
| Google integration operational | 2026-04-06 | Shared OAuth, headless-safe, env-var bootstrap |
| Pre-commit hooks + linting | 2026-04-07 | ruff enforced, 62 issues fixed, Codex review loop |
| Agent observability | 2026-04-07 | Profile + Article agents log to runs table |
| Edge case hardening | 2026-04-07 | 6 bugfixes from python-patterns audit, 219 tests |
