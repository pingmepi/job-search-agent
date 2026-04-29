# Docs Alignment Report — job-search-agent (`inbox-agent`)

Scanned 11 doc surfaces (root markdown + `/docs/`) against ~50 source files on 2026-04-29.
Skipped: `.planning/`, `.pytest_cache/`, `.claude/`, `node_modules/`, `inbox_agent.egg-info/`, `interview-prep/` (generated).

## Summary
- **HIGH:** 2 — would mislead someone in setup, usage, or an interview answer
- **MED:**  4 — noticeable, can trip a careful reader, doesn't break core understanding
- **LOW:**  2 — cosmetic, stale comment, minor inconsistency

---

## Findings

### [HIGH] config-env-drift — Three "ghost" env vars read by code but missing from `.env.example`

**File:** `.env.example` (whole file)
**Says:** Lists 19 env vars including all `OCR_*`, `TELEGRAM_*`, `WEBHOOK_*`, `MAX_COST_PER_JOB`, `DATABASE_URL`.
**Actually:** [core/config.py](core/config.py) reads three additional vars not in `.env.example`:
- `TELEGRAM_ALLOWED_CHAT_IDS` — [core/config.py:68](core/config.py#L68) (chat allowlist for security)
- `ENFORCE_SINGLE_PAGE` — [core/config.py:87](core/config.py#L87) (defaults `true` — controls resume single-page enforcement)
- `MAX_CONDENSE_RETRIES` — [core/config.py:90](core/config.py#L90) (defaults `3` — resume condense loop)

Onboarding works because all three have defaults, but a security-conscious self-hoster will want to set `TELEGRAM_ALLOWED_CHAT_IDS` and won't discover it from `.env.example`.
**Fix:** Add these three to `.env.example` with their defaults and a one-line comment each.

---

### [HIGH] stale-instruction — PRD §13.3 marks Phase 3 as "Todo" but Phase 3 features have shipped

**File:** [PRD.md:553](PRD.md#L553)
**Says:** `| Phase 3 Workflow Product Surface | KAR-62 | Todo |`
**Actually:** Phase 3 deliverables (PRD §[409-417](PRD.md#L409-L417)) are live:
- A–F markdown application reports → [docs/README.md:18](docs/README.md#L18) and `application_report.md` artifacts.
- Pipeline integrity checks → `python main.py pipeline-check` is documented and implemented in [core/pipeline_checks.py](core/pipeline_checks.py).
- Drive-centered artifact visibility → [README.md:5-9](README.md#L5-L9) describes Drive folder + report.

Either the table row is stale or "Portal scanner" + "Operator dashboard" (the unshipped sub-items) need to be split out as separate rows.
**Fix:** Update PRD §13.3 row to reflect partial completion (e.g. split Phase 3 into shipped sub-items vs. Portal scanner / Operator dashboard remaining).

---

### [MED] undocumented-feature — Six CLI subcommands not in README "## Commands"

**File:** [README.md:73-79](README.md#L73-L79)
**Says:** Lists six commands: `webhook`, `init-db`, `ci-gate`, `db-stats`, `pipeline-check`, `followup-runner --once`.
**Actually:** [main.py](main.py) exposes six additional subcommands:
- `runs [run_id] [--steps] [--limit N]` — list/inspect run history with step audit ([main.py:243-288](main.py#L243-L288))
- `replay-webhook --event-id|--update-id` — replay a stored Telegram update ([main.py:56-94](main.py#L56-L94))
- `eval-report [--json]` — print eval trend report ([main.py:296-300](main.py#L296-L300))
- `build-skill-index` — rebuild `profile/skill_index.json` ([main.py:302-305](main.py#L302-L305))
- `encode-token` — base64-encode Google OAuth token for Railway env ([main.py:307-325](main.py#L307-L325))
- `auth-google` — interactive Google OAuth flow ([main.py:327-338](main.py#L327-L338))

The module docstring lists most of these ([main.py:4-13](main.py#L4-L13)), so `python main.py` (no args) prints them. But the README is the discovery surface.
**Fix:** Extend README "## Commands" with the six missing entries, especially `auth-google` (required for Drive/Calendar setup) and `runs` (primary debugging tool).

---

### [MED] stale-comments-docstrings — `ci_gate.py` still references SQLite after Postgres migration

**File:** [evals/ci_gate.py:21-22](evals/ci_gate.py#L21-L22)
**Says:** `> Prints compile rate, forbidden claims, and edit violations from / actual SQLite run history for situational awareness.`
**Actually:** The codebase migrated to PostgreSQL ([PRD.md:148](PRD.md#L148): "PostgreSQL DB (migrated from SQLite)"). [core/db.py](core/db.py) uses `psycopg2`, and the runtime DB is Postgres on Railway.
**Fix:** Replace "SQLite" with "PostgreSQL" in the docstring.

---

### [MED] removed-api — PRD §11 Repository Structure omits `agents/article/`

**File:** [PRD.md:482-497](PRD.md#L482-L497)
**Says:** Repo structure shows `agents/{inbox, profile, followup}/` only.
**Actually:** `agents/article/` exists and is wired into the router ([core/router.py:82-91](core/router.py#L82-L91), `_ARTICLE_INDICATORS`) and PRD §3 itself documents the routing rule ("article content → Article Agent"). Article agent is also referenced in [docs/decisions.md:317](docs/decisions.md#L317) and `tests/test_article_agent.py`. Functional requirement FR-AA-1 is in PRD §13.1 marked "Done" against KAR-73.
**Fix:** Add `article/` to the §11 tree and add an "Agent 4 — Article Agent" subsection to §2 (or note it explicitly under Agent 1's responsibilities).

---

### [MED] stale-instruction — Quick Start path hardcoded to one developer's machine

**File:** [docs/README.md:65-66](docs/README.md#L65-L66)
**Says:** `cd /Users/karan/Desktop/job-search-agent`
**Actually:** Hardcoded absolute path is meaningless to anyone else, including future-you on a different machine, and including in CI / Docker contexts. The other setup docs ([docs/setup-and-test.md:7-8](docs/setup-and-test.md#L7-L8)) correctly say "Run from repo root" without a path.
**Fix:** Replace with `cd <repo-root>` or remove the line entirely.

---

### [LOW] config-env-drift — `LLM_FALLBACK_MODELS` example pinned to seven specific free-tier models

**File:** [.env.example:4](.env.example#L4) and [docs/README.md:86](docs/README.md#L86)
**Says:** A specific 7-model fallback chain (`qwen/qwen3-coder:free, llama-3.2-3b, llama-3.3-70b, mistral-small-3.1-24b, deepseek-r1, gpt-oss-120b, trinity-mini`).
**Actually:** [core/llm.py:65-76](core/llm.py#L65-L76) handles `"no endpoints found"` errors precisely *because* free-tier OpenRouter models churn frequently. A pinned 7-model list documented as "the example" will rot — likely already has, given OpenRouter's pace.
**Fix:** Trim the example to 1–2 models and add a sentence: "Free-tier models on OpenRouter rotate; check openrouter.ai/models before relying on these IDs."

---

### [LOW] version-drift — README and docs both target Python 3.9, ruff matches; clean

**File:** [pyproject.toml:5](pyproject.toml#L5), [docs/setup-and-test.md:31-33](docs/setup-and-test.md#L31-L33)
**Says:** `requires-python = ">=3.9"` (manifest); "Python 3.9.6" (sample setup output).
**Actually:** Aligned. `target-version = "py39"` in `[tool.ruff]` matches. No drift.
**Fix:** None. Listed for completeness — this is a clean area, not a finding.

---

## Clean Areas

- **Setup commands work end-to-end.** All commands in [README.md:29-69](README.md#L29-L69) and [docs/setup-and-test.md](docs/setup-and-test.md) (`pip install -e ".[dev]"`, `python main.py init-db`, `python main.py webhook`, `./set_webhook.sh`) map to real subcommands and scripts.
- **`.env.example` → `core/config.py` round-trip is clean for documented vars.** All 19 vars listed in `.env.example` are read by `core/config.py`. (The drift is in the other direction — code reads three more — see HIGH finding above.)
- **Eval gate thresholds match PRD §12.** `COMPILE_RATE_THRESHOLD=0.95`, `COST_THRESHOLD=0.15`, `LATENCY_THRESHOLD_MS=60_000`, `FORBIDDEN_CLAIMS_MAX=0`, `EDIT_VIOLATIONS_MAX=0` in [evals/ci_gate.py:36-40](evals/ci_gate.py#L36-L40) all match PRD §12 success criteria.
- **Functional-requirement traceability table (PRD §13.1) matches the codebase.** Spot-checked FR-IA-1 through FR-IA-9, FR-PA-1/2/3, FR-FU-1/2, FR-AA-1 — every "Done" row has corresponding implementation.
- **Webhook surface matches docs.** `GET /health`, `POST /telegram/webhook` are documented in [README.md:23-24](README.md#L23-L24) and [docs/README.md:131-132](docs/README.md#L131-L132); `app.py` exposes both.
- **No dead relative links in real docs.** `find_dead_doc_links.py` reported 113 hits, but all 113 are in the generated `interview-prep/ai-product-builder.md` and use GitHub line-anchor convention (`path#L42`) which the scanner doesn't recognize as a non-link. Production docs are clean.
- **Routing rules match between PRD and code.** PRD §3 routing table matches the rule order in [core/router.py:99-169](core/router.py#L99-L169) one-for-one.

---

## How to act on this

If you only do three things:
1. Add `TELEGRAM_ALLOWED_CHAT_IDS`, `ENFORCE_SINGLE_PAGE`, `MAX_CONDENSE_RETRIES` to `.env.example` (HIGH, 5 min).
2. Update PRD §13.3 Phase 3 row — A–F reports and pipeline-check shipped (HIGH, 5 min).
3. Extend README's `## Commands` list with the six missing subcommands (MED, 10 min).

The two MED stale references (`SQLite` in `ci_gate.py` docstring, missing `agents/article/` in PRD §11) are 1-line fixes worth bundling into the same PR.
