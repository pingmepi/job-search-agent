# Job Search Agent Tracker

Last updated: 2026-04-23

## Sources Of Truth
- PRD: `PRD.md`
- Linear project: `job-search-agent`
  - https://linear.app/karans/project/job-search-agent-d5014a28b093
- Linear tracker doc:
  - https://linear.app/karans/document/tracker-2026-02-16-20e846e0ca54

## Current Status
- Phase: Phase 3 product workflow expansion in progress.
- Deployment: Railway (PostgreSQL + Docker). Webhook live.
- Test status: `251 passed, 37 skipped` (ruff lint clean, pre-commit hooks active). Live E2E: `pytest -m live`.
- CI gate status: `PASSED` (fixture-based gating, all 5 thresholds green).
- Pre-commit: ruff lint + format + pytest. Install: `bash scripts/install-hooks.sh`.
- Active issue: `KAR-62` (Phase 3 product workflow expansion).

## Latest Progress (2026-04-23)
- Added `application_report.md` artifact with A-F framing, selected base resume details, mutation summary, collateral status, and execution summary.
- Wired markdown report upload into the per-application Google Drive folder alongside the resume and generated collateral.
- Added `python main.py pipeline-check` for DB/artifact integrity checks, including report presence validation.
- Reframed roadmap work away from SaaS packaging and toward product surface expansion: reports, integrity checks, scanner, and dashboard.
- Marked Telegram-originated inbox submissions as manually vetted intake and persisted that provenance on `jobs.user_vetted`.

## Previous Progress (2026-04-08)
- Full codebase hardening: 17 fixes across security (7), performance (2), correctness (5), maintainability (3). Key: pickle→JSON tokens, SSRF protection, connection pooling, Drive closure bug, chat_id allowlist (`TELEGRAM_ALLOWED_CHAT_IDS`).
- 32 new tests (251 total): JSON utils, drafts, Google auth, SSRF, E2E pipeline. Live E2E opt-in with `pytest -m live`.
- `core/json_utils.py` — shared JSON extraction utility (deduplicated from jd.py + executor.py).
- `_handle_eval_log` decomposed into 5 focused helpers: `_resolve_costs`, `_run_hard_evals`, `_run_soft_evals`, `_persist_artifacts`, `_complete_run_record`.
- Removed dead `db_path` parameter from all DB function signatures.
- Made Google Drive & Calendar integration operational — shared OAuth module, headless-safe, `GOOGLE_TOKEN_B64` env-var bootstrap, tenacity retry, `python main.py auth-google` CLI command.
- Added pre-commit hooks — `scripts/pre-commit` runs ruff lint + format + pytest on staged files. `scripts/install-hooks.sh` for portable install. ruff added as dev dependency.
- Fixed 62 ruff lint issues (unused imports, unsorted imports, dead variable, empty f-strings). Reformatted 40 files.
- Added Codex review loop — `.claude/commands/review-fix.md` (auto-fix) and `review-check.md` (read-only).
- Profile Agent run logging — `run_profile_agent()` with insert_run/complete_run, tracks tokens, latency, ungrounded claims. 2 new tests.
- Article Agent run logging + signal persistence — `run_article_agent()` logs runs, persists signals to new `article_signals` table. 3 new tests.
- Bugfix: None in JD skills crashes `bullet_relevance.py` — guard `_normalize()`, filter None from skills list (`8abced8`).
- Bugfix: Company names with `'` break Drive API query — escape quotes (`1b9d822`).
- Bugfix: Malformed JSON from LLM crashes article agent — catch JSONDecodeError (`1b9d822`).
- Bugfix: `update.message` None on edge-case Telegram updates — early return guards (`1b9d822`).
- Bugfix: Executor `_parse_json_object` unhandled JSONDecodeError — wrap in try/except (`1b9d822`).
- Bugfix: Profile load failure silently degrades mutation quality — log warning (`1b9d822`).

## Previous Progress (2026-04-03)
- Implemented `KAR-73` ArticleAgent — `agents/article/agent.py` summarizes articles and surfaces job-search signals. Router integration + 4 unit tests.
- Added bullet bank relevance scoring (`agents/inbox/bullet_relevance.py`) — JD-aware pre-filtering with tag overlap (60%) + keyword overlap (40%).
- Built v2 mutation pipeline — REWRITE/SWAP/GENERATE ops, top-12 bullet pre-selection, profile context injection, selective revert on truthfulness failure (`43d56bf`).
- Added per-bullet truthfulness guard — granular checking replaces all-or-nothing fallback, common-word skip set reduces false positives (`6177cee`).
- Simplified executor — `_load_profile` extraction, `reverted_count` scope fix, `Counter` usage (`cfccfa3`).
- Added `run_steps` audit trail — per-step input/output logging via `run_steps` table, `python main.py runs <id> --steps` (`2712592`).
- Migrated persistence from SQLite to PostgreSQL (`psycopg2`) for production concurrency (`e18a794`).
- Deployed to Railway with Docker (python:3.11-slim + Tesseract + TexLive).
- Fixed Railway PORT healthcheck, stdout logging, PDF delivery via Telegram, truthfulness false positives (`d8c3a5c`, `244fa09`, `16c1cda`, `22eb3bf`).
- Removed single-page enforcement — multi-page accepted, page count tracked as metadata (`22eb3bf`).

## Previous Progress (2026-03-16)
- Implemented `KAR-61` planner/executor separation.
- Decoupled tool planning from LLM context - `agents/inbox/planner.py` added for deterministic routing logic without any LLM calls.
- Migrated 12 execution step handlers with resilient retry logic and graceful degradation to `agents/inbox/executor.py`.
- Refactored `agents/inbox/agent.py` to be a thin adapter.
- Added comprehensive unit tests for planner and executor (49 new tests).
- Fixed monkeypatch issues in integration tests due to refactoring. Test baseline expanded to `222 passed`.
- Implemented `KAR-60` success criteria gates + CI threshold enforcement.
- CI gate now exits 0: compile 100%, forbidden 0, edit violations 0, avg cost $0.07, avg latency 33s.
- Removed 3-mutation cap — model can now make unlimited edits within editable regions.
- Added bullet density rules to resume mutation prompt (max 5/role, min 1, density by relevance).
- Created `resume_condense_v1.txt` prompt for post-compile overflow condensing.
- Added `get_pdf_page_count()` helper using pypdf for single-page PDF verification.
- Wired single-page enforcement loop into pipeline: compile → page check → LLM condense (2 retries) → margin fallback.
- Changed artifact output to per-application folders: `runs/artifacts/{company}_{role}_{hash}/`.
- Added draft file persistence: `email_draft.txt`, `linkedin_dm.txt`, `referral.txt` saved to output folder.
- Enabled Drive upload and Calendar events in `.env` (`TELEGRAM_ENABLE_DRIVE_UPLOAD=true`, `TELEGRAM_ENABLE_CALENDAR_EVENTS=true`).
- Added `pypdf>=4.0.0` to dependencies.
- Wired soft evals (`score_resume_relevance`, `score_jd_accuracy`) into pipeline — results logged in `eval_results`.
- Added 14 soft eval test cases in `tests/test_soft_evals.py`.
- Replaced placeholder cost estimate with real USD cost tracking via OpenRouter's `/api/v1/generation` endpoint.
- Cost resolution is deferred (batch at pipeline end) to avoid inline latency. Free models → `$0.00`.
- Updated and fixed integration tests. Test baseline: 114 passed.

## Previous Progress (2026-02-21)
- Synced local tracker against Linear issue states and due dates.
- Re-verified test baseline on `main`: `98 passed`.
- Re-ran CI gate and confirmed current failing signals are compile success threshold and forbidden-claims threshold.
- Added operational docs for setup/test flow and troubleshooting/issue debugging: `docs/setup-and-test.md`, `docs/troubleshooting-and-debugging.md`.
- Verified current build/test baseline: `98 passed`.
- Verified CI gating status: failing on compile success threshold and forbidden-claims threshold.
- Implemented `KAR-49` follow-up progression persistence (`follow_up_count` increment + `last_follow_up_at`) with migration + tests.
- Implemented `KAR-51` integration coverage for pipeline + adapter flow with mocked dependencies.
- Implemented `KAR-50` URL ingestion fetch path with screenshot fallback UX in Telegram adapter flow.
- Implemented `KAR-57` eval logging/token accounting completion across OCR cleanup, JD extraction, mutation, and draft generation.
- Implemented `KAR-53` fit score persistence from resume selection and keyword coverage eval logging.
- Implemented `KAR-55` adapter production toggles for Drive upload + Calendar event creation (`TELEGRAM_ENABLE_*` flags).
- Implemented `KAR-54` compile failure rollback to base resume artifact path with rollback eval flag.
- Implemented `KAR-56` profile-agent grounding hardening and forbidden-claim tests (entity + metric claim detection).
- Implemented `KAR-52` OCR quality hardening + low-confidence screenshot fallback messaging.
- Implemented `KAR-58` scheduled follow-up detection runner (`python main.py followup-runner`) with dry-run/loop controls and run telemetry persistence.
- Implemented `KAR-77` webhook API E2E coverage with realistic Telegram payload tests and malformed-payload handling (`400` instead of uncaught exception).
- Synced local tracker and Linear tracker doc with the same status snapshot.

## Completed Work
- [x] KAR-42 Enforce editable-region-only resume mutations
- [x] KAR-43 Persist compiled resume artifacts outside temp directories
- [x] KAR-44 Add regression test for mutation edit-scope guard
- [x] KAR-45 Make compile eval require existing artifact path
- [x] KAR-46 Wire Telegram inbox handlers to execute full pipeline
- [x] KAR-47 Offload sync pipeline from async Telegram event loop (`asyncio.to_thread`)
- [x] KAR-48 Compute real eval metrics for edit scope and forbidden claims
- [x] KAR-63 FR-PA-3 Narrative selection by role-family
- [x] KAR-64 FR-FU-2 Follow-up draft generation with escalation tiers
- [x] Local Telegram bot configuration updated (`TELEGRAM_TOKEN` + `TELEGRAM_BOT_USERNAME`) and settings model extended
- [x] KAR-65 Migrate Telegram ingestion to webhook service (FastAPI webhook + secret verification, no polling)
- [x] KAR-49 Increment follow-up counters when drafts are generated/sent
- [x] KAR-51 Add integration tests for inbox pipeline and Telegram adapter
- [x] KAR-50 Implement URL ingestion fetch and screenshot fallback
- [x] KAR-57 FR-IA-9 Complete eval logging fields + token accounting
- [x] KAR-53 FR-IA-3 Persist fit score / keyword overlap
- [x] KAR-55 FR-IA-6/7 Enable Drive + Calendar in production flow
- [x] KAR-54 FR-IA-5 Compile failure rollback behavior
- [x] KAR-56 FR-PA-1/2 Grounding evals + forbidden-claim tests
- [x] KAR-52 FR-IA-2 OCR hardening and failure handling
- [x] KAR-58 FR-FU-1 Scheduled follow-up detection runner
- [x] KAR-77 Webhook API E2E realistic payload integration tests
- [x] KAR-60 Success criteria gates + CI thresholds (compile ≥ 95%, forbidden claims = 0, edit violations = 0, cost/latency reporting)
- [x] KAR-61 Phase 2 planner/executor separation
- [x] KAR-73 ArticleAgent — article summarization and job-search signal surfacing

## Pending Work
- [ ] KAR-62 Phase 3 product workflow expansion scoping
- [ ] KAR-72 Persist raw Telegram webhook events to `data/raw_events/`
- [ ] KAR-74 Implement default memory agent fallback behavior
- [ ] KAR-75 Define and persist formal JSON artifacts for job/resume/eval outputs
- [ ] KAR-76 Auto-create/update Linear application issue from pipeline output

## Merged From `docs/execution_plan` (Tracker Superset)
- [ ] Add webhook raw event persistence to `data/raw_events/` (`KAR-72`).
- [ ] Add default memory/fallback agent behavior beyond current clarify response (`KAR-74`).
- [ ] Define and persist structured JSON artifacts for job posting, resume output, and eval result (partially covered by existing run logs; formal schema artifacts tracked in `KAR-75`).
- [ ] Auto-create/update Linear issue per generated application (`Apply - {Company} - {Role}` with resume/JD attachments) (`KAR-76`).
- [ ] Phase 3 product workflow expansion items: scanner, dashboard, richer report artifacts, and operator integrity tooling (`KAR-62`).

## Milestones (Linear)
- Phase 0 - Core Executor Hardening (target: 2026-03-01)
- Phase 1 - Intelligence Layer (target: 2026-03-15)
- Phase 2 - Planner Mode (target: 2026-04-05)
- Phase 3 - Workflow Product Surface (target: 2026-04-30)

## Execution Order
1. KAR-62
2. KAR-72

## Notes
- Persistence: PostgreSQL via `psycopg2` (migrated from SQLite at commit `e18a794`).
- Deployed on Railway with Docker (`python:3.11-slim` + Tesseract + TexLive).
- Telegram ingestion runs through webhook service endpoint `/telegram/webhook` (no polling).
- Telegram inbox submissions are treated as vetted job posts and persisted with `jobs.user_vetted = 1`.
- Telegram handlers derive `skip_upload` / `skip_calendar` from env toggles.
- Pipeline artifacts persist to `runs/artifacts/`.
- CI gate: fixture-based, all 5 thresholds green. Historical live-DB noise is non-blocking.
- Follow-up scheduler: `python main.py followup-runner --once` (or loop mode).
- `docs/execution_plan` merged into this tracker; this file is the canonical superset.
- See `BUILD_LOG.md` for full project evolution history.
