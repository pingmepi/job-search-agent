# Job Search Agent — Project Overview

A multi-agent system that converts job postings into complete, tailored application packages via Telegram. Built solo over 7 weeks. Production on Railway.

---

## 1. Problem

Applying to jobs is a multi-step manual grind:

1. Read JD, figure out which resume base fits
2. Rewrite bullets to match the role's keywords and requirements
3. Compile the resume, check it's one page, fix formatting
4. Write a cover email, LinkedIn DM, referral note
5. Upload everything to Drive, create calendar reminders
6. Track the application, set follow-up reminders

Each application took ~1 hour. The steps are repetitive, the quality inconsistent, and the tracking fragile.

**Goal:** Automate the entire pipeline — not just "generate a cover letter" but the full workflow from JD ingestion to tracked, stored, follow-up-scheduled application package.

---

## 2. What Was Built

A Telegram bot. Send a job description (text, URL, or screenshot) → get back:
- Tailored resume PDF (LaTeX-compiled, mutations grounded in real experience)
- Markdown application report with A-F framing, selected base resume, and mutation summary
- Email draft, LinkedIn DM (<300 chars), referral note
- Google Drive folder with all artifacts
- Calendar events (apply deadline + follow-up reminder)
- Full telemetry: tokens, cost, latency, eval results per step

### System at a Glance

```
Telegram Message
    │
    ▼
┌─────────────────────────────────┐
│  Deterministic Router           │  Zero LLM calls
│  (pattern matching, <1ms)       │  Routes to correct agent
└──────────┬──────────────────────┘
           │
    ┌──────┼──────────┬──────────────┐
    ▼      ▼          ▼              ▼
 INBOX   PROFILE   FOLLOW-UP    ARTICLE
 AGENT    AGENT     AGENT        AGENT
    │
    ▼
┌─────────────────────────────────┐
│  Planner (deterministic)        │  Zero LLM calls
│  Builds 12-step tool plan       │  Based on input type
└──────────┬──────────────────────┘
           │
           ▼
┌─────────────────────────────────┐
│  Executor (13 step handlers)    │  All LLM calls here
│  Retry + graceful degradation   │  Errors → pack.errors
│                                 │
│  1. OCR (if screenshot)         │
│  2. JD extraction               │
│  3. Resume selection            │
│  4. Resume mutation             │
│  5. LaTeX compilation           │
│  6. Markdown report generation  │
│  7. Calendar events             │
│  8. Email draft                 │
│  9. LinkedIn DM                 │
│  10. Referral note              │
│  11. Drive upload               │
│  12. DB persistence             │
│  13. Eval logging               │
└─────────────────────────────────┘
           │
           ▼
┌─────────────────────────────────┐
│  PostgreSQL                     │
│  5 tables: jobs, runs,          │
│  run_steps, webhook_events,     │
│  article_signals                │
└─────────────────────────────────┘
```

### Four Agents

| Agent | What It Does | Status |
|-------|-------------|--------|
| **Inbox Agent** | Full pipeline: JD → resume → report → collateral → upload → log | Production, full telemetry |
| **Profile Agent** | Answers questions about me, grounded in profile.json + bullet bank. Forbidden-claim enforcement. | Production, run logging |
| **Follow-Up Agent** | Detects +7 day applications, generates escalation-aware drafts (3 tiers), persists progress | Implemented, UX pending |
| **Article Agent** | Summarizes articles, extracts job-search signals (hiring, funding, skills in demand) | Functional, signal persistence |

### Stack

| Layer | Technology |
|-------|-----------|
| Runtime | FastAPI (webhook, no polling) |
| LLM | OpenRouter (Claude Sonnet in prod, free-tier for dev) |
| OCR | Tesseract |
| Compilation | pdflatex (TexLive) |
| Storage | Google Drive (per-application folders) |
| Calendar | Google Calendar (apply + follow-up events) |
| Database | PostgreSQL (psycopg2, connection pooling) |
| Deployment | Railway + Docker (python:3.11-slim, ~400MB image) |
| Code Quality | ruff + pre-commit hooks + Codex PR reviews |
| Auth | Webhook secret verification + chat_id allowlist |

---

## 3. Architecture Decisions & Trade-offs

Not every decision was obvious. Here are the ones that shaped the system:

### Deterministic router — zero LLM calls for routing

**Chose:** Regex/keyword pattern matching. Six targets: INBOX, PROFILE, FOLLOWUP, ARTICLE, AMBIGUOUS, CLARIFY.

**Rejected:** LLM-based intent classification.

**Why:** Routing happens on every message. LLM adds $0.001-0.01 per message, 200-500ms latency, and non-deterministic behavior (same message could route differently). Pattern matching is free, sub-millisecond, and 100% testable.

**Trade-off accepted:** Can't handle ambiguous intent. User sends something that doesn't match → falls to CLARIFY. Worth it for testability and zero cost.

### Planner/executor separation — testable plans without mocks

**Chose:** Split the pipeline into a deterministic planner (zero LLM, produces a step list) and an executor (runs each step with retry logic).

**Rejected:** Single monolithic pipeline function.

**Why:** The original pipeline was one function with 12 interleaved LLM calls, DB writes, and file operations. Testing required mocking everything. After the split, the planner is pure logic — testable with zero mocks. All LLM calls live in the executor's step handlers.

**Effect:** 49 new tests from this refactor alone. Step handlers can be added/removed independently.

### Fixture-based CI gate — not live DB metrics

**Chose:** 12 curated eval fixtures with 5 hard thresholds.

**Rejected:** Running evals against live production DB.

**Why:** Live DB had historical noise from dev/test runs. A bad exploratory run would make the CI gate flaky. Fixtures are deterministic and reproducible.

**Thresholds:**
- Compile success ≥ 95%
- Forbidden claims = 0 (zero tolerance)
- Edit scope violations = 0 (zero tolerance)
- Average cost ≤ $0.15/run
- Average latency ≤ 60s

**Current metrics:** 100% compile, 0 forbidden, 0 violations, $0.07/run, 33s avg.

### LLM outputs treated as untrusted data

**Trigger:** Three production bugs in one session, all from trusting LLM output:
1. `None` in JD skills list → crash in bullet scoring
2. Company name with `'` → Drive API query injection
3. Malformed JSON despite `json_mode=True` → article agent crash

**Decision:** Every LLM-extracted value gets boundary validation:
- `json.loads()` always wrapped in try/except
- Lists filtered for None before iteration
- Strings escaped before query interpolation
- Fallback paths log warnings (never silent)

**Effect:** Codified as a reusable Claude Code skill (`llm-output-hardening`) with 18 rules. Applied across all agents.

### Graceful degradation with visibility

**Pattern:** Non-fatal errors append to `pack.errors` and execution continues. Users get partial results instead of total failure.

**Problem discovered:** `_load_profile()` had `except Exception: return {}` — if profile.json was missing, mutations proceeded with no profile context. Zero errors, zero warnings. Quality silently eroded.

**Refinement:** Every fallback path now logs a warning. Graceful degradation is correct for reliability; but invisible degradation is worse than crashing.

### Single OAuth token — user-prompted simplification

**Original:** Two separate token files (`drive_token.pickle`, `calendar_token.pickle`), two env vars.

**User feedback:** "If I'm using OAuth, it has access to both APIs — why do I need two separate variables?"

**Fix:** Single `google_token.json` with both scopes, one `GOOGLE_TOKEN_B64` env var. Three modes: headless (load/refresh), interactive (browser), env-var bootstrap (Railway).

---

## 4. Challenges & How They Were Solved

### LLM Output Trust (the recurring theme)

The #1 source of production bugs. Three of six bugs in one audit session came from trusting LLM output:

| Bug | Root Cause | Fix |
|-----|-----------|-----|
| `resume_mutate` crash | LLM returns `["python", null, "sql"]` — None in skills list | Guard `_normalize()`, filter None |
| Drive API breaks | Company name `O'Reilly` breaks `name = '{name}'` query | Escape quotes before interpolation |
| Article agent crash | `json_mode=True` returns non-JSON on free-tier models | Catch JSONDecodeError, return empty |

**Takeaway:** `json_mode` is a hint, not a contract. Every field extracted by JSON mode can be null, wrong type, or missing.

### Resume Mutation Quality (3 iterations)

**V1 (Feb):** 3-mutation cap. Too restrictive — resumes barely changed.

**V2 (Feb):** Unlimited mutations with density rules (max 5 bullets/role, min 1). Better, but all-or-nothing truthfulness check caused false positives (flagged JD terms like "data pipeline" as fabricated).

**V3 (Apr):** Per-bullet truthfulness with common-word skip set. Three mutation operations (REWRITE/SWAP/GENERATE). Bullet bank pre-filtered by JD relevance (top-12 selection). Selective revert — only flagged bullets removed, clean mutations kept.

**Effect:** False positive rate dropped significantly. Resumes are tailored without fabrication.

### Production Deployment (Railway)

Four issues in one day:

| Issue | Root Cause | Fix |
|-------|-----------|-----|
| Healthcheck timeout | App on `WEBHOOK_PORT`, Railway injects `PORT` | Fallback chain: PORT → WEBHOOK_PORT → 8000 |
| All logs show as errors | Python logging to stderr | Route to stdout |
| Users can't see artifacts | Bot said "done" without files | Send PDF + drafts via Telegram |
| SQLite locks on concurrent webhooks | File-level locking | Migrated to PostgreSQL |

**Takeaway:** Deploying is not shipping. Production surfaced issues that local dev never would.

### Security Hardening (code review audit)

A full python-patterns audit found 7 security issues:

| Severity | Issue | Fix |
|----------|-------|-----|
| Critical | Pickle deserialization → RCE | Switched to JSON token storage |
| High | SSRF — URL fetch hits cloud metadata | IP validation (reject private/loopback/link-local) |
| High | Unbounded response read → OOM | 5MB cap on `resp.read()` |
| High | Webhook secret stored in DB | Redact before persistence |
| Medium | No chat authorization | `TELEGRAM_ALLOWED_CHAT_IDS` allowlist |
| Low | Path traversal in prompt loader | Validate resolved path stays in prompts dir |
| Low | Generation ID not URL-encoded | `urllib.parse.quote()` |

---

## 5. Evaluation Framework

### Why Eval-First

Every LLM-powered system needs a way to know if it's getting better or worse. Without evals, you're shipping blind.

### Hard Evals (deterministic, pass/fail)

| Eval | What It Checks |
|------|---------------|
| Compile success | pdflatex exits 0 and PDF exists |
| JD schema valid | All required fields present and typed correctly |
| Edit scope | Mutations only within `%%BEGIN_EDITABLE` / `%%END_EDITABLE` markers |
| Forbidden claims | Per-bullet grounding check against profile + bullet bank + JD corpus |
| Draft length | LinkedIn DM ≤ 300 characters |
| Cost threshold | Total run cost ≤ $0.15 |

### Soft Evals (LLM-judged, scored 0-100)

| Eval | What It Measures |
|------|-----------------|
| Resume relevance | How well does the mutated resume match the JD? (LLM judge) |
| JD accuracy | How accurately were company/role/skills/description extracted? (LLM judge) |

### CI Gate

12 curated fixtures. 5 thresholds. Runs via `python main.py ci-gate`. Blocks release if any threshold fails.

**Current metrics (2026-04-08):**

| Metric | Threshold | Actual |
|--------|-----------|--------|
| Compile success | ≥ 95% | 100% |
| Forbidden claims | = 0 | 0 |
| Edit violations | = 0 | 0 |
| Avg cost | ≤ $0.15 | $0.07 |
| Avg latency | ≤ 60s | 33s |

### Per-Run Telemetry

Every pipeline run logs:
- Token counts (prompt + completion per step)
- Real USD costs (resolved async via OpenRouter)
- Latency per step
- Input/output per step (run_steps audit trail)
- Eval results (all hard + soft evals)
- Errors encountered (with graceful degradation)
- Markdown report path plus mutation summary in run context / resume artifact

---

## 6. By the Numbers

| Category | Metric | Value |
|----------|--------|-------|
| Timeline | Duration | 51 days (2026-02-16 → 2026-04-08) |
| Code | Commits | 51 |
| Tests | Passing | 251 |
| Tests | Skipped (need DB) | 37 |
| Milestones | Count | 14 |
| Bugs fixed | Count | 24 (with root cause + fix documented) |
| Architecture | ADRs documented | 23 |
| Security | Fixes | 7 |
| Agents | Count | 4 (Inbox, Profile, Follow-Up, Article) |
| Pipeline | Steps | 12 |
| Resume variants | Count | 5 (AI, Technical, Growth, Agentic, Founders) |
| Bullet bank | Entries | 56 across 8 role families |
| Tools tracked | Count | 36 |
| CI gate | Fixtures | 12 |
| CI gate | Status | PASSED (all 5 thresholds green) |
| Cost | Per run | $0.07 avg |
| Latency | Per run | 33s avg |
| Compile | Success rate | 100% on fixtures |

---

## 7. What I Learned

### LLM outputs are untrusted data

This is the single most important lesson. Three of six bugs in one audit session came from trusting LLM responses. `json_mode=True` doesn't guarantee valid JSON. Extracted lists can contain null. Extracted strings can break queries.

**Rule:** Validate at the boundary. Every `json.loads()` wrapped. Every list filtered. Every string escaped. Every fallback logged.

### Eval design is the actual product work

Writing the eval framework took more thought than writing the pipeline. Deciding what "good" means (compile success? truthfulness? relevance?) forced clarity on product requirements. The evals are the spec.

### Graceful degradation needs visibility

Appending to `pack.errors` and continuing is the right reliability pattern. But silent degradation — where a step fails and nobody notices — is worse than crashing. Every fallback path needs a log line.

### Pre-commit hooks pay for themselves on day one

The hooks caught a broken integration test on the very first commit after installation. Without them, that would've reached the PR.

### Building agents is 20% prompting, 80% systems engineering

The LLM prompts are maybe 5 files. The other 95% is: error boundaries, retry logic, cost tracking, mutation constraints, eval design, database schema, deployment configuration, security hardening, test infrastructure.

### The "it should never happen" cases happen constantly

`update.message` being None. `json_mode` returning non-JSON. JD skills containing null. Every optional field WILL be null in production. Design for it.

---

## 8. What's Next

### Immediate
- **Follow-Up Agent UX:** Runner exists with full logging. Adapter only shows status — needs `/followup` command to generate and show drafts.
- **Draft cost tracking:** Draft LLM calls don't capture `generation_id`. Costs always show $0.00.

### Medium-term
- **Conversion tracking:** The real metric. Are tailored resumes getting more interviews? Need volume to measure.
- **Workflow product surface:** scanner, dashboard, integrity checks, and richer application artifacts for day-to-day operating use.

### Backlog
- Persist raw webhook events (KAR-72)
- Default memory agent fallback (KAR-74)
- Auto-create Linear issue per application (KAR-76)
- Formal JSON artifact schemas (KAR-75)

---

## 9. Repository

- **GitHub:** `pingmepi/job-search-agent`
- **Docs:** `BUILD_LOG.md` (evolution), `docs/decisions.md` (23 ADRs), `TRACKER.md` (status)
- **Run tests:** `.venv/bin/pytest -q -m "not live"`
- **Run CI gate:** `python main.py ci-gate`
- **Live E2E:** `OPENROUTER_API_KEY=... pytest -m live`
- **Install hooks:** `bash scripts/install-hooks.sh`
