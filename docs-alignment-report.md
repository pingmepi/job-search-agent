# Docs Alignment Report — job-search-agent

Scanned 9 primary doc surfaces against ~93 Python source files on 2026-05-05 (post-fix pass).

Tool version: 1.0.0. Repo HEAD: `dbf469a` (branch `fix/telegram-length-eval-logging`, with uncommitted doc fixes applied).

## Summary
- HIGH: 0
- MED:  0
- LOW:  2     (cosmetic, archival)

All HIGH and MED findings from the 2026-05-05 pre-fix audit have been resolved. Two LOW findings remain in archival files and are tracked here for visibility but were intentionally not edited.

## Resolved in this pass

| Pre-fix | Category | Resolution |
|---|---|---|
| HIGH — README missing 8 CLI subcommands | stale-instruction | README.md "Common Commands" expanded to 15 entries; pointer to `docs/RUNBOOK.md` added. main.py docstring also extended with `runs`, `auth-google`, `encode-token`. |
| MED — test count 324 → 330 in 4 docs | test-claim-mismatch | Updated AGENT_HANDOFF.md, TRACKER.md, docs/PROJECT_OVERVIEW.md, docs/setup-and-test.md to `330 passed, 41 skipped`. |
| MED — TELEGRAM_DEMO_MODE undocumented | undocumented-feature | New "Features (2026-05-05)" stanza in CHANGELOG.md; AGENT_HANDOFF.md "What Completed This Session (2026-05-05)" block added. |
| MED — AGENT_HANDOFF.md 3 days behind | stale-instruction | "Last updated" bumped to 2026-05-05; new session block; previous session block preserved. |
| MED — PROJECT_OVERVIEW commit count 114 → 122 | version-drift | Updated to 122 (and skipped-tests row to 41). |

## Remaining LOW findings (intentionally not auto-edited)

### [LOW] dead-link — Conceptual "memory" / "execution_plan" references in archived docs
**File:** docs-review-2026-04-30.md:70, docs-review-2026-04-30.md:117, docs-review-2026-04-30.md:241, interview-prep/ai-engineer-llm.md:261, interview-prep/ai-engineer-llm.md:387
**Says:** Markdown links of the form `[memory 594](memory)` and `[docs/execution_plan](docs/execution_plan)`.
**Actually:** These resolve to the auto-memory observation system, not filesystem paths. `docs/execution_plan` exists as `docs/execution_plan.md`.
**Fix (deferred):** Either de-link the bracketed text or extend `docs/execution_plan` → `docs/execution_plan.md`. Both files are archival snapshots; editing in place would distort the captured-at-time record.

### [LOW] stale-instruction — TRACKER.md historical test baselines accumulating without rollup
**File:** TRACKER.md:71,87,91,94
**Says:** Multiple historical "Test baseline expanded to 222 passed", "114 passed", "98 passed" entries.
**Actually:** Each is correct as a snapshot but the file has no current-state header — a reader has to scan to find today's number.
**Fix (deferred):** Promote line 15 ("Test status: 330 passed, 41 skipped") into a "Current state" block at the top; demote historical lines to a "Baseline history" subsection. Skipped because it is a structural rewrite, not a correctness fix.

## Clean Areas
- `.env.example` keys all referenced in `core/config.py` (`OPENROUTER_API_KEY`, `TELEGRAM_*`, `WEBHOOK_*`, `PORT`, `MAX_CONDENSE_RETRIES`, `OCR_*`, `DATABASE_URL`, `ENFORCE_SINGLE_PAGE`, `GOOGLE_*`, `MAX_COST_PER_JOB`).
- `SCHEMA_VERSION = "1.1"` in core/contracts.py:9 has no stale `"1.0"` doc claim remaining.
- docs/RUNBOOK.md §4 includes `TELEGRAM_DEMO_MODE` and `MAX_CONDENSE_RETRIES`, matching `.env.example`.
- AGENTS.md agent inventory (Inbox/Profile/Followup/Article) matches `agents/` directory listing.
- README.md Quick Start commands all resolve.
- `docs/decisions.md` ADR log and `core/contracts.py` schema bump are mutually consistent.
- main.py module docstring covers all 15 dispatched subcommands.
- Test baseline `330 passed, 41 skipped` consistent across AGENT_HANDOFF, TRACKER, PROJECT_OVERVIEW, setup-and-test.
