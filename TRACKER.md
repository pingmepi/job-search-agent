# Job Search Agent Tracker

Last updated: 2026-02-16

## Sources Of Truth
- PRD: `PRD.md`
- Linear project: `job-search-agent`
  - https://linear.app/karans/project/job-search-agent-d5014a28b093
- Linear tracker doc:
  - https://linear.app/karans/document/tracker-2026-02-15-20e846e0ca54

## Current Status
- Phase: Core pipeline hardening in progress.
- Test status: `66 passed` (`.venv/bin/pytest -q`).
- Repo has implemented fixes for mutation scope, artifact persistence, real eval checks, and Telegram orchestration.
- Active issue: `KAR-49` (`In Progress`, due `2026-02-22`).

## Completed Work
- [x] KAR-42 Enforce editable-region-only resume mutations
- [x] KAR-43 Persist compiled resume artifacts outside temp directories
- [x] KAR-44 Add regression test for mutation edit-scope guard
- [x] KAR-45 Make compile eval require existing artifact path
- [x] KAR-46 Wire Telegram inbox handlers to execute full pipeline
- [x] KAR-47 Offload sync pipeline from async Telegram event loop (`asyncio.to_thread`)
- [x] KAR-48 Compute real eval metrics for edit scope and forbidden claims
- [x] Local Telegram bot configuration updated (`TELEGRAM_TOKEN` + `TELEGRAM_BOT_USERNAME`) and settings model extended
- [x] KAR-65 Migrate Telegram ingestion to webhook service (FastAPI webhook + secret verification, no polling)

## Pending Work
- [ ] KAR-49 Increment follow-up counters when drafts are generated/sent
- [ ] KAR-50 Implement URL ingestion fetch and screenshot fallback
- [ ] KAR-51 Add integration tests for inbox pipeline and Telegram adapter
- [ ] KAR-52 FR-IA-2 OCR hardening and failure handling
- [ ] KAR-53 FR-IA-3 Persist fit score / keyword overlap
- [ ] KAR-54 FR-IA-5 Compile failure rollback behavior
- [ ] KAR-55 FR-IA-6/7 Enable Drive + Calendar in production flow
- [ ] KAR-56 FR-PA-1/2 Grounding evals + forbidden-claim tests
- [ ] KAR-57 FR-IA-9 Complete eval logging fields + token accounting
- [ ] KAR-58 FR-FU-1 Scheduled follow-up detection runner
- [ ] KAR-59 Soft evals (resume relevance + JD extraction accuracy)
- [ ] KAR-60 Success criteria gates (10+ eval cases + CI thresholds)
- [ ] KAR-61 Phase 2 planner/executor separation
- [ ] KAR-62 Phase 3 SaaS readiness scoping

## Milestones (Linear)
- Phase 0 - Core Executor Hardening (target: 2026-03-01)
- Phase 1 - Intelligence Layer (target: 2026-03-15)
- Phase 2 - Planner Mode (target: 2026-04-05)
- Phase 3 - SaaS Readiness (target: 2026-04-30)

## Execution Order
1. KAR-49
2. KAR-51
3. KAR-50
4. KAR-57
5. KAR-53

## Notes
- Telegram ingestion now runs through webhook service endpoint `/telegram/webhook` (no polling runtime).
- Telegram handlers currently call `run_pipeline(..., skip_upload=True, skip_calendar=True)` in adapter flow.
- Pipeline artifacts persist to `runs/artifacts/`.
- Follow-up logic still needs DB progression updates for tier advancement.
- Local `.env` now includes bot credential wiring; `.env.example` includes `TELEGRAM_BOT_USERNAME` for onboarding consistency.
- Added `set_webhook.sh` for Telegram webhook registration (`drop_pending_updates=true` + `secret_token`).
