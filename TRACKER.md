# Job Search Agent Tracker

Last updated: 2026-02-16

## Sources Of Truth
- PRD: `PRD.md`
- Linear project: `job-search-agent`
  - https://linear.app/karans/project/job-search-agent-d5014a28b093
- Linear tracker doc:
  - https://linear.app/karans/document/tracker-2026-02-16-20e846e0ca54

## Current Status
- Phase: Core pipeline hardening in progress.
- Test status: `98 passed` (`.venv/bin/pytest -q` on 2026-02-16).
- CI gate status: `FAILED` (`.venv/bin/python main.py ci-gate` on 2026-02-16; compile success rate `0.0%`, threshold `95%`).
- Repo has implemented fixes for mutation scope, artifact persistence, real eval checks, and Telegram orchestration.
- Active issue: `KAR-59` (`Todo`, due `2026-03-02`).

## Latest Progress (2026-02-16)
- Verified current build/test baseline: `98 passed`.
- Verified CI gating status: failing on compile success threshold only; other gates green.
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

## Pending Work
- [ ] KAR-59 Soft evals (resume relevance + JD extraction accuracy)
- [ ] KAR-60 Success criteria gates (10+ eval cases + CI thresholds)
- [ ] KAR-61 Phase 2 planner/executor separation
- [ ] KAR-62 Phase 3 SaaS readiness scoping
- [ ] KAR-72 Persist raw Telegram webhook events to `data/raw_events/`
- [ ] KAR-73 Add `ArticleAgent` routing and handler flow
- [ ] KAR-74 Implement default memory agent fallback behavior
- [ ] KAR-75 Define and persist formal JSON artifacts for job/resume/eval outputs
- [ ] KAR-76 Auto-create/update Linear application issue from pipeline output

## Merged From `docs/execution_plan` (Tracker Superset)
- [ ] Add webhook raw event persistence to `data/raw_events/` (`KAR-72`).
- [ ] Add router branch + handler flow for `ArticleAgent` (`KAR-73`).
- [ ] Add default memory/fallback agent behavior beyond current clarify response (`KAR-74`).
- [ ] Define and persist structured JSON artifacts for job posting, resume output, and eval result (partially covered by existing run logs; formal schema artifacts tracked in `KAR-75`).
- [ ] Auto-create/update Linear issue per generated application (`Apply - {Company} - {Role}` with resume/JD attachments) (`KAR-76`).
- [ ] URL extraction quality hardening (direct fetch + readability fallback + field extraction) (`KAR-50`).
- [ ] OCR hardening and failure handling (`KAR-52`).
- [ ] Eval expansion (skill coverage, keyword overlap, missing requirements, hallucination checks, compile integrity gate hardening) (`KAR-53`, `KAR-56`, `KAR-59`, `KAR-60`).
- [ ] Follow-up outcome feedback loop and adaptive optimization (Phase 2 direction; currently represented by `KAR-61`).
- [ ] Productization/SaaS readiness items (dockerization, configurable backends, public vs paid packaging scope) (`KAR-62`).

## Milestones (Linear)
- Phase 0 - Core Executor Hardening (target: 2026-03-01)
- Phase 1 - Intelligence Layer (target: 2026-03-15)
- Phase 2 - Planner Mode (target: 2026-04-05)
- Phase 3 - SaaS Readiness (target: 2026-04-30)

## Execution Order
1. KAR-59
2. KAR-60
3. KAR-61
4. KAR-62
5. KAR-72

## Notes
- Telegram ingestion now runs through webhook service endpoint `/telegram/webhook` (no polling runtime).
- Telegram handlers now derive `skip_upload` / `skip_calendar` from env toggles (`TELEGRAM_ENABLE_DRIVE_UPLOAD`, `TELEGRAM_ENABLE_CALENDAR_EVENTS`).
- Pipeline artifacts persist to `runs/artifacts/`.
- `docs/execution_plan` has been merged into this tracker; this file is the canonical superset for planning/execution.
- CI gate currently fails due to historical compile eval results in `runs` lowering compile success rate below threshold.
- Follow-up scheduler is now available via `python main.py followup-runner --once` (or loop mode).
- Local `.env` now includes bot credential wiring; `.env.example` includes `TELEGRAM_BOT_USERNAME` for onboarding consistency.
- Added `set_webhook.sh` for Telegram webhook registration (`drop_pending_updates=true` + `secret_token`).
