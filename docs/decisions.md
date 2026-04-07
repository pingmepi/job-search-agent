# Architectural Decision Log

Every significant decision made during development, with context on what was considered, what was chosen, and why. Cross-referenced with commits, sessions, and BUILD_LOG.md entries.

Last updated: 2026-04-08

---

## ADR-01: Webhook-First Telegram Architecture

**Date:** 2026-02-16 | **Commit:** `e2569b3` | **Status:** Active

**Context:** Telegram bots can receive updates via long-polling or webhooks. We're deploying on Railway, which is container-based with no persistent processes.

**Considered:**
- **Long polling** — simpler to develop locally, no public URL needed. But: requires a persistent process, adds 1-2s latency per message, incompatible with Railway's ephemeral container model.
- **Webhook** — lower latency (~50ms), Railway-native, scales naturally with incoming traffic.

**Decision:** Webhook via FastAPI endpoint at `/telegram/webhook`.

**Consequences:**
- Local development requires ngrok or similar tunnel for testing
- Need webhook secret verification for security (`app.py` checks `X-Telegram-Bot-Api-Secret-Token`)
- Railway healthcheck hits the same port — needed PORT fallback chain later (ADR-12)

**References:** `app.py`, `agents/inbox/adapter.py`, BUILD_LOG.md §Timeline

---

## ADR-02: Deterministic Router — Zero LLM Calls

**Date:** 2026-02-16 | **Commit:** `e2569b3` | **Status:** Active

**Context:** Incoming Telegram messages need to be routed to the right agent (Inbox, Profile, Follow-Up, Article). The question: use an LLM to classify intent, or pattern matching?

**Considered:**
- **LLM-based classification** — handles ambiguous input well, adapts to new intents. But: adds $0.001-0.01 per message, 200-500ms latency, non-deterministic (same message could route differently).
- **Regex/keyword pattern matching** — zero cost, sub-millisecond, 100% reproducible, fully testable without mocks.

**Decision:** Deterministic router in `core/router.py`. Six targets: `INBOX`, `PROFILE`, `FOLLOWUP`, `ARTICLE`, `AMBIGUOUS_NON_JOB`, `CLARIFY`.

**Trade-off accepted:** Can't handle ambiguous intent (user sends something that doesn't clearly match any pattern → falls to `CLARIFY`). Worth it for testability and zero cost.

**References:** `core/router.py`, `tests/test_router.py`, BUILD_LOG.md §Architectural Decisions #5

---

## ADR-03: OpenRouter Gateway (Not Direct OpenAI)

**Date:** 2026-02-16 | **Commit:** `e2569b3` | **Status:** Active

**Context:** Need LLM access for JD extraction, resume mutation, draft generation. Which API?

**Considered:**
- **Direct OpenAI API** — well-documented, fast. But: expensive for iteration ($0.01-0.03/call), no free tier, locked to OpenAI models.
- **OpenRouter** — OpenAI-compatible SDK, 200+ models, free-tier models available (Gemma, Llama), easy model swaps without code changes.
- **Self-hosted (Ollama)** — free, private. But: requires GPU, not Railway-compatible, slow on CPU.

**Decision:** OpenRouter via OpenAI SDK (`core/llm.py`). Default model: free-tier `google/gemma-2-9b-it:free`. Production: Claude Sonnet via OpenRouter.

**Consequences:**
- Extra hop adds ~50ms latency vs direct API
- Cost resolution requires async lookup via OpenRouter's `/api/v1/generation` endpoint (ADR-06)
- Vendor dependency on OpenRouter availability

**References:** `core/llm.py`, `core/config.py` (LLM settings), BUILD_LOG.md §Architectural Decisions #3

---

## ADR-04: Dataclasses Over Pydantic for Domain Models

**Date:** 2026-02-16 | **Status:** Active

**Context:** Need structured data containers for pipeline payloads (`ApplicationPack`, `LLMResponse`, `RouteResult`, `Settings`, `ToolPlan`, `ToolStep`).

**Considered:**
- **Pydantic** — automatic validation, JSON schema generation, serialization. But: heavier, more magic, validation overhead on hot paths.
- **dataclass** — stdlib, simple, `frozen=True` for immutability, explicit validation in `__post_init__`.
- **NamedTuple** — immutable by default, lighter than dataclass. But: no default values in older Python, less flexible.

**Decision:** `@dataclass` for all domain models. `frozen=True` for config (`Settings`). Pydantic is a dependency but used sparingly.

**References:** `core/config.py` (Settings), `core/llm.py` (LLMResponse), `agents/inbox/executor.py` (ExecutionContext, ApplicationPack)

---

## ADR-05: Unlimited Resume Mutations with Density Rules

**Date:** 2026-02-25 | **Commit:** `20da486` | **Status:** Active

**Context:** Original design capped resume edits at 3 per application. Users found this too restrictive — resumes weren't sufficiently tailored.

**Considered:**
- **Keep 3-cap** — safe, predictable, low risk of over-mutation. But: resumes look barely tailored.
- **Unlimited with no constraints** — maximum tailoring. But: risk of bloated resumes, fabricated content.
- **Unlimited with density rules** — max 5 bullets/role, min 1, density weighted by relevance.

**Decision:** Remove cap. Add density rules + per-bullet truthfulness guard (ADR-11).

**Evolution:** V2 mutation pipeline (2026-04-02, `43d56bf`) added structured operation types: REWRITE (modify existing), SWAP (replace with bank entry), GENERATE (create new from profile). This replaced the original unstructured "edit these bullets" prompt.

**References:** `agents/inbox/executor.py` (_handle_resume_mutate), `agents/inbox/bullet_relevance.py`, BUILD_LOG.md §V2 Mutation Pipeline

---

## ADR-06: Deferred Cost Resolution

**Date:** 2026-02-25 | **Commit:** `20da486` | **Status:** Active

**Context:** OpenRouter provides real USD costs per LLM call, but the lookup requires a separate API call using the `generation_id`. Doing this inline adds 1-2s latency per LLM call.

**Decision:** Capture `generation_id` from each LLM response. Batch-resolve all costs at pipeline end via `resolve_generation_cost()`. Free models always report $0.00.

**Trade-off:** Cost data arrives after pipeline completion, not during. Acceptable because cost is a reporting metric, not a control signal.

**Known gap:** Draft calls (email, LinkedIn, referral) don't capture `generation_id` — their costs are always $0.00. See AGENT_HANDOFF.md §Known Risks.

**References:** `core/llm.py` (LLMResponse.generation_id), BUILD_LOG.md §Architectural Decisions #3

---

## ADR-07: Sprint Phases 1-3 in 2 Days

**Date:** 2026-03-04 to 2026-03-05 | **Commits:** `2110aca` through `b13bbc2` | **Status:** Completed

**Context:** Roadmap defined 5 phases. Codebase was small (~2000 LOC). Spreading phases across weeks would mean repeated context-loading overhead.

**Decision:** Sprint all three initial phases in one 2-day push:
- Phase 1: Intake reliability (webhook persistence, replay CLI, deterministic routing)
- Phase 2: Resume tailoring (selection, mutation, truthfulness, compile fallback)
- Phase 3: Collateral delivery (email/LinkedIn/referral drafts, Drive upload, Calendar events)

**Consequence:** Rapid progress but accumulated some technical debt (integration tests were thin, error handling was optimistic). Hardening work followed in subsequent weeks.

**References:** `.planning/ROADMAP.md`, BUILD_LOG.md §Timeline

---

## ADR-08: Planner/Executor Separation

**Date:** 2026-03-16 | **Commit:** `f95fa43` (KAR-61) | **Status:** Active

**Context:** The inbox pipeline was a single monolithic function with 12 interleaved LLM calls, DB writes, and file operations. Testing required mocking everything.

**Considered:**
- **Keep monolith** — simpler code structure. But: untestable without heavy mocking, hard to add/remove steps.
- **Planner + executor split** — planner produces a deterministic `ToolPlan` (list of `ToolStep` objects) with zero LLM calls. Executor runs each step with retry and graceful degradation.

**Decision:** Split. Planner is pure logic (input type detection → step list). Executor handles all LLM/IO/DB interactions.

**Key insight:** All intelligence lives in the executor's 12 step handlers. The planner is just a switch statement. This means the plan is 100% testable without mocks, and new steps can be added by just writing a handler + adding it to the plan.

**References:** `agents/inbox/planner.py`, `agents/inbox/executor.py`, `tests/test_planner.py`, `tests/test_executor.py`, BUILD_LOG.md §Planner/Executor

---

## ADR-09: Fixture-Based CI Gate (Not Live DB)

**Date:** 2026-03-16 | **Commit:** `1ffb5ae` (KAR-60) | **Status:** Active

**Context:** CI gate was querying live DB for eval metrics. Historical dev/test runs polluted the data — a bad test run would make the gate flaky.

**Decision:** 12 curated eval fixtures. 5 hard thresholds:
- Compile success ≥ 95%
- Forbidden claims = 0
- Edit scope violations = 0
- Average cost ≤ $0.15/run
- Average latency ≤ 60s

**Current metrics (on fixtures):** Compile 100%, forbidden 0, violations 0, $0.07/run, 33s avg.

**Trade-off:** Only 12 test cases. Doesn't catch issues specific to unusual JDs. But deterministic and reproducible across all environments.

**References:** `evals/ci_gate.py`, `evals/hard.py`, `evals/soft.py`, BUILD_LOG.md §Architectural Decisions #6

---

## ADR-10: SQLite → PostgreSQL

**Date:** 2026-03-31 | **Commit:** `e18a794` | **Status:** Active

**Context:** SQLite uses file-level locking. When multiple Telegram webhooks arrive simultaneously, they compete for the DB lock → timeouts and lost writes.

**Decision:** Migrate to PostgreSQL via `psycopg2`. Railway provides managed Postgres.

**Migration approach:** Kept the same schema DDL, replaced `sqlite3` calls with `psycopg2`. Added `_apply_migrations()` for column additions. Used `psycopg2.extras.RealDictCursor` for dict-style row access.

**Consequence:** Tests that need DB now require `DATABASE_URL` env var (35 tests skip without it). Local dev needs a running Postgres instance or Railway's connection string.

**References:** `core/db.py`, `Dockerfile`, `tests/conftest.py`, BUILD_LOG.md §Architectural Decisions #7

---

## ADR-11: Per-Bullet Truthfulness Guard

**Date:** 2026-04-02 | **Commit:** `6177cee` | **Status:** Active

**Context:** Original truthfulness check was all-or-nothing: if any mutation bullet contained a potentially ungrounded claim, the entire resume reverted to base. This caused too many false positives — JD-sourced terms like "data pipeline" or generic words like "Led" would trigger reversion.

**Decision:** Per-bullet granularity:
1. Check each mutated bullet individually against profile + bullet bank + JD corpus
2. Common-word skip set prevents false flags (`Product`, `Senior`, `Led`, `Built`, etc.)
3. Only flagged bullets are reverted; clean mutations are kept
4. Multi-word entity detection preserved (e.g., "Goldman Sachs" still caught)

**Result:** False positive rate dropped significantly. Resumes are more tailored while still blocking fabricated claims.

**References:** `agents/inbox/executor.py` (_handle_resume_mutate), BUILD_LOG.md §Per-Bullet Truthfulness

---

## ADR-12: Remove Single-Page Enforcement

**Date:** 2026-04-02 | **Commit:** `22eb3bf` | **Status:** Active

**Context:** Pipeline had a condense loop: compile → check page count → if >1 page, LLM condenses → retry (up to 2x) → margin adjustment fallback. This added complexity and sometimes hurt readability.

**Considered:**
- **Keep enforcement** — guarantees one-page output. But: condensing can remove important content, margin hacks look unprofessional.
- **Remove enforcement, track as metadata** — most resumes fit one page naturally with the density rules. Page count is logged but not a gate.

**Decision:** Remove. Page count stored as metadata in run telemetry.

**References:** `agents/inbox/executor.py`, BUILD_LOG.md §Architectural Decisions #8

---

## ADR-13: Single OAuth Token for Drive + Calendar

**Date:** 2026-04-06 | **Commit:** `8814640`, `03886ee` | **Status:** Active

**Context:** Original design used two separate OAuth flows — one for Drive, one for Calendar. This meant two token files (`drive_token.pickle`, `calendar_token.pickle`), two env vars for Railway (`GOOGLE_DRIVE_TOKEN_B64`, `GOOGLE_CALENDAR_TOKEN_B64`), and two authentication prompts.

**Trigger:** User feedback: "if I am using OAuth — it will have access to both APIs — why do I need two separate variables?"

**Decision:** Single token file (`google_token.pickle`) with both Drive + Calendar scopes. One env var (`GOOGLE_TOKEN_B64`). Shared OAuth module (`integrations/google_auth.py`).

**Three modes:**
1. **Headless** — load token, refresh if expired, raise if missing (never opens browser)
2. **Interactive** — `python main.py auth-google` opens browser for OAuth consent
3. **Env-var bootstrap** — decode `GOOGLE_TOKEN_B64` to disk on startup (Railway deployment)

**References:** `integrations/google_auth.py`, `integrations/drive.py`, `integrations/calendar.py`, `docs/google-oauth-setup.md`

---

## ADR-14: Pre-Commit Hooks Over CI-Only Checks

**Date:** 2026-04-07 | **Commit:** `61de9ea` | **Status:** Active

**Context:** Zero automated code quality gates existed. All 62 ruff issues accumulated unnoticed. Codex reviews PRs on open but only catches issues after push.

**Considered:**
- **CI-only (GitHub Actions)** — catches issues on push. But: slower feedback loop (push → wait for CI → fix → push again).
- **Pre-commit hooks** — catches issues before commit. Faster feedback. But: can be skipped with `--no-verify`.
- **Both** — layered approach. Pre-commit for fast local feedback, Codex for deeper design review on PR.

**Decision:** Both layers:
- **Layer 1 (local):** `scripts/pre-commit` runs ruff lint, ruff format check, and pytest on staged `.py` files
- **Layer 2 (remote):** Codex auto-reviews PRs. `.claude/commands/review-fix.md` and `review-check.md` for feedback loop.

**Immediate payoff:** The pre-commit hook caught a broken integration test (`test_integration_pipeline_adapter`) on the very first commit — would have made it to the PR without hooks.

**References:** `scripts/pre-commit`, `scripts/install-hooks.sh`, `.claude/commands/review-fix.md`, `pyproject.toml` (ruff config)

---

## ADR-15: Agent Run Logging — Match Inbox Agent Observability

**Date:** 2026-04-07 | **Commit:** `1580c49` | **Status:** Active

**Context:** Inbox Agent logged everything (runs, run_steps, evals, cost). Profile Agent and Article Agent logged nothing — no tokens, no latency, no errors. Impossible to debug quality issues or track usage.

**Decision:** Add `run_profile_agent()` and `run_article_agent()` wrappers that:
1. Generate unique `run_id`
2. Call `insert_run()` before execution
3. Call `complete_run()` after with tokens, latency, and eval results
4. For Article Agent: persist extracted signals to new `article_signals` table

**Design choice:** Wrapper pattern, not modification. Original `answer()` and `summarize()` functions unchanged for backward compatibility. New `*_with_telemetry()` variants return the `LLMResponse` alongside results.

**References:** `agents/profile/agent.py`, `agents/article/agent.py`, `core/db.py` (article_signals DDL), `tests/test_profile.py`, `tests/test_article_agent.py`

---

## ADR-16: LLM Outputs as Untrusted Data

**Date:** 2026-04-07 | **Commits:** `8abced8`, `1b9d822` | **Status:** Active (ongoing pattern)

**Context:** Three production bugs in one session all stemmed from trusting LLM output:
1. `None` in JD skills list → crash in `bullet_relevance.py`
2. Company name with `'` → Drive API query injection
3. Malformed JSON from LLM → article agent crash

**Decision:** Treat all LLM-extracted values as untrusted data at the boundary:
- `json.loads()` always wrapped in try/except
- Lists filtered for None before iteration
- String values guarded with `or ""`
- Extracted strings escaped before query interpolation
- Fallback paths log warnings (never silent)

**Codified as:** `~/.claude/skills/llm-output-hardening/SKILL.md` — a reusable Claude Code skill with 18 rules and a production checklist. Python-specific (not for TypeScript/Next.js).

**Key insight:** `json_mode=True` is a hint, not a contract. Free-tier models, rate-limited responses, and edge cases regularly produce non-JSON or structurally invalid output.

**References:** `agents/inbox/bullet_relevance.py`, `agents/article/agent.py`, `integrations/drive.py`, `agents/inbox/executor.py`, `agents/inbox/adapter.py`

---

## ADR-17: Graceful Degradation with Visibility

**Date:** 2026-02-17 (pattern) → 2026-04-07 (refined) | **Status:** Active

**Context:** Early design decision: non-fatal errors append to `pack.errors` and pipeline continues. Users get partial results instead of total failure. Good for reliability — but bad for debugging when degradation is silent.

**Original problem (2026-04-07):** `_load_profile()` had `except Exception: return {}` — if profile.json was missing, mutations proceeded with no profile context. No error, no warning, no telemetry. Quality silently eroded.

**Refined decision:** Graceful degradation is correct, but every fallback path must log a warning:
```python
except Exception as exc:
    logger.warning("Failed to load profile: %s", exc)
    return {}
```

**Principle:** Silent failures are worse than crashes. A crash gets fixed immediately. A silent fallback degrades quality for weeks before anyone notices.

**References:** `agents/inbox/executor.py` (_load_profile, _run_step_with_retry), BUILD_LOG.md §Bugfixes

---

## Decision Index

| # | Decision | Date | Trigger | Key Commit |
|---|----------|------|---------|------------|
| 01 | Webhook-first architecture | 2026-02-16 | Initial design | `e2569b3` |
| 02 | Deterministic router | 2026-02-16 | Initial design | `e2569b3` |
| 03 | OpenRouter LLM gateway | 2026-02-16 | Cost constraints | `e2569b3` |
| 04 | Dataclasses over Pydantic | 2026-02-16 | Simplicity preference | — |
| 05 | Unlimited mutations + density | 2026-02-25 | 3-cap too restrictive | `20da486` |
| 06 | Deferred cost resolution | 2026-02-25 | 1-2s inline latency | `20da486` |
| 07 | Sprint 3 phases in 2 days | 2026-03-04 | Small codebase | `2110aca` |
| 08 | Planner/executor separation | 2026-03-16 | Testability | `f95fa43` |
| 09 | Fixture-based CI gate | 2026-03-16 | Flaky live-DB metrics | `1ffb5ae` |
| 10 | SQLite → PostgreSQL | 2026-03-31 | Concurrent webhook locks | `e18a794` |
| 11 | Per-bullet truthfulness | 2026-04-02 | False positive rate | `6177cee` |
| 12 | Remove single-page enforcement | 2026-04-02 | Complexity vs value | `22eb3bf` |
| 13 | Single OAuth token | 2026-04-06 | User feedback | `8814640` |
| 14 | Pre-commit hooks | 2026-04-07 | Zero quality gates | `61de9ea` |
| 15 | Agent run logging | 2026-04-07 | Zero observability | `1580c49` |
| 16 | LLM outputs as untrusted data | 2026-04-07 | 3 production bugs | `8abced8` |
| 17 | Graceful degradation + visibility | 2026-04-07 | Silent quality loss | `1b9d822` |
