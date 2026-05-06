# Changelog

All notable changes to job-search-agent are recorded here. Dates use ISO format (YYYY-MM-DD).

## [Unreleased] — 2026-04-24 → 2026-05-05

A sprint focused on closing the **persona-misalignment regression** (run-144b1afaef4a, where a Portuguese sales-engineer JD silently rebranded the candidate's resume), tightening the eval/regression harness so similar drift is caught automatically, hardening Telegram message-length safety, and adding a recruiter-facing demo onboarding mode.

### Features (2026-05-05)

- **Recruiter demo onboarding mode (`TELEGRAM_DEMO_MODE`).** When the env flag is enabled, the Telegram bot serves a demo-tuned `/start` greeting on first contact and bypasses `TELEGRAM_ALLOWED_CHAT_IDS` so anyone can try the bot end-to-end. Standard mode (default) preserves the existing allowlist behavior. Wired in `core/config.py` and `agents/inbox/adapter.py`.

### Fixes (2026-05-02)

- **Telegram message-length hardening.** Added centralized Telegram-safe reply handling with summarize-retry + hard truncation fallback to prevent `Bad Request: message is too long` reply failures.
- **Final outbound collateral now constrained in-pipeline.** Email/LinkedIn/referral drafts are length-constrained before persistence so the final text intended for Telegram delivery is the same text saved to artifacts.
- **Eval + run-context coverage for final drafts.** `eval_results` now includes Telegram draft length metrics/audit, and run context now stores `final_collateral_drafts` plus `telegram_draft_audit` for operator traceability.
- **Regression tests added** for oversized reply behavior and condensed-final-draft logging/eval paths.

### New Features

- **Out-of-scope JD gate.** The pipeline now aborts before resume mutation when a JD scores too low against every template, instead of forcing a bad match through. New `task_outcome="out_of_scope"` is persisted to the DB so these runs show up in eval reports rather than vanishing.
- **Persona lock in resume mutation.** The `resume_mutate` prompt now requires the summary persona to come from `profile.identity.roles` / `profile.positioning` — never from the JD title. Closes the regression where a "Sales Engineer" JD rewrote the candidate's identity.
- **Multilingual + functional-skills JD extraction.** `jd_extract_v2` prompt handles non-English JDs and functional (non-tech) skills, with a single retry when the LLM returns `skills=[]` on a JD over 200 characters.
- **Skill-empty fallback signal.** When a JD has no extractable skills, templates are scored against tokenized `role + description` (capped at 0.5 so it never beats a real skills match).
- **Regression runner v1 + feedback-loop telemetry.** Production run outcomes feed back into a regression fixture suite; a new `edge_out_of_scope_pt_sales_engineer` fixture pins the persona-misalignment fix.
- **`eval-report` CLI command.** Summarize production runs from the terminal: outcomes, soft-eval scores, and run-level metadata.
- **Soft-eval improvements.** Judge prompts extracted to versioned files; repeat-averaging (median) reduces variance across soft-eval runs.

### Improvements

- **Honest retry telemetry.** JD-retry token usage is now aggregated even when the retry still returns empty skills, so cost reporting is accurate.
- **Inbox profile caching.** Profile loading is cached on the inbox path — fewer disk reads per run.
- **Grounding allowed-entities refined.** Expanded the profile-agent grounding allowlist to cut false-positive grounding violations.
- **Tighter fallback gate.** The out-of-scope gate now trips on weak fallback scores (not just zero), and requires ≥15% of fallback tokens to match — a single generic word can no longer sneak a JD past the gate.
- **Soft-eval hard floor.** A soft-resume-relevance score below 0.4 now demotes a run from `success` → `partial` automatically.
- **Regression soft-score floors enforced.** The regression runner fails when soft scores drop below per-fixture thresholds, catching silent quality regressions.
- **Docs alignment.** README, PRD, and `.env.example` reconciled with current code: the missing `MAX_CONDENSE_RETRIES` env var is documented, the agent count is corrected (4 → matches code), and a stale developer-machine path was removed.

### Bug Fixes

- **Resume blank-bullet recovery hardened** so empty bullets emitted by the LLM no longer survive into the rendered PDF.
- **Soft eval parsing hardened** against malformed judge output (null fields, partial JSON).
- **`OutOfScopeError` no longer skips DB persistence.** A minimal run record is written so `task_outcome=out_of_scope` reaches the DB, eval_log fires, and `get_run(pack.run_id)` stops returning `None` for Telegram error replies and the regression fixture.
- **`dataclasses.replace()`** replaces the fragile `type(response)(...)` reconstruction in retry paths.
- **Test mocks fixed** in `test_jd.py` and `test_drafts.py` (missing `LLMResponse.model` field); `test_regression_runner.py` mock made case-aware so non-success expected outcomes pass.

### Internal

- **PR #32 review-fix.** Greptile/Codex feedback on the Telegram length-safety system addressed: shared constants and `hard_truncate` extracted into `core/telegram_utils.py`, two diverging `_hard_truncate` impls unified, missing `label=` args added to `_reply_text` calls in adapter, summarize-attempts audit guarded inside `if condensed:`, and per-attempt generation labels added so condense-loop costs accumulate.
- **Docs-alignment fixes (2026-05-02 → 2026-05-05).** `SCHEMA_VERSION` bumped 1.0 → 1.1, duplicate `.env.example` keys removed, test-count snapshots refreshed across TRACKER / AGENT_HANDOFF / PROJECT_OVERVIEW / setup-and-test, README "Common Commands" expanded to cover all 15 `main.py` subcommands.
- Alignment cache (`.alignment-cache.json`) refreshed; docs-alignment audit run end-to-end with HIGH issues resolved.
- `ai-product-builder` interview-prep artifact added under `interview-prep/`.
- Test baseline: **330 passing, 41 skipped** at sprint close (up from 315 mid-sprint and 251 earlier in the project).

---

_Generated 2026-05-05 from commits `1e7b6bb..dbf469a`._
