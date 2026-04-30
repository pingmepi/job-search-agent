# Interview Prep: AI Product Builder × job-search-agent

**Role:** AI Product Builder (`ai-product-builder`)
**Repo:** job-search-agent
**Generated:** 2026-04-30
**Question bank version:** 1

---

## Alignment Caveats

None — docs appear current. Alignment cache is fresh at HEAD `8c4619f`. All prior HIGH-severity findings resolved in PR #30 (commit `8ec48cb`). Two LOW findings are non-critical: `docs/webhook-service.md` is a stale build brief (use `docs/webhook-service-instructions.md` instead), and `interview-prep/` #L-anchor links are scanner false positives (base files exist).

---

## Coverage Summary

| Bucket | Total questions | With repo evidence | First-principles only |
|--------|----------------|-------------------|----------------------|
| Base Concepts | 12 | 12 | 0 |
| New Developments | 11 | 9 | 2 |
| Applied / Scenario | 9 | 7 | 2 |
| Failure Modes | 10 | 10 | 0 |
| **Total** | **42** | **38** | **4** |

---

## Section A — Canonical Questions + Repo Evidence

### Base Concepts

---

#### Q: Walk me through how you decide what to build with AI vs. what to build without it — what's your decision framework?

**Repo evidence:** `core/router.py:99–169` — deterministic keyword/regex routing that deliberately avoids LLM for intent classification; `docs/decisions.md` ADR-02

**Your answer:** The repo draws an explicit AI/no-AI boundary at the router. Incoming Telegram messages are classified using pure regex pattern matching (zero LLM, sub-millisecond, 100% reproducible) because intent classification doesn't require semantic reasoning — it just needs to distinguish "JD screenshot" from "profile question" from "follow-up." LLM is reserved for tasks where pattern matching provably can't substitute: JD extraction from unstructured text, resume bullet mutation, and outreach draft generation. The ADR documents the explicit cost-benefit comparison (LLM-based routing: $0.001–0.01/msg + 200–500ms; pattern matching: $0 + <1ms), making the decision traceable rather than intuitive.

---

#### Q: How do you evaluate whether an LLM feature is "good enough" to ship? What's your bar when ground truth is hard to define?

**Repo evidence:** `evals/ci_gate.py:36–40` — 5 hard thresholds; `evals/soft.py:40–81` — LLM-judge soft scores with median aggregation

**Your answer:** The repo uses a two-tier system. Hard gates are binary, deterministic, and block CI: compile success ≥95%, forbidden claims = 0, edit scope violations = 0, cost ≤$0.15/run, latency ≤60s — run against a curated fixture dataset of 12 diverse JDs. Soft evals are LLM-as-judge scores (resume relevance to JD, JD extraction accuracy) that run 3 times and take the median to reduce judge variance. They don't block CI but produce trend data. The bar for shipping is: all hard gates pass on fixtures, and soft scores don't regress vs. the previous version. Ground truth being hard to define is exactly why the soft evals use a judge model rather than manual labeling.

---

#### Q: You're building an AI feature with non-deterministic outputs. How do you design the UX to set appropriate user expectations?

**Repo evidence:** `agents/inbox/resume.py:24–29` — `EditableRegion` dataclass; `core/prompts/resume_mutate_v3.txt:8–14` — NON-NEGOTIABLE constraints block

**Your answer:** The resume mutation engine constrains what the LLM can touch via `%%BEGIN_EDITABLE`/`%%END_EDITABLE` markers in LaTeX templates. Company names, job titles, dates, and the structural skeleton are hardcoded outside these regions — the LLM only gets to modify specific bullet content within bounded zones. The UX implication: users know exactly what will and won't change before the pipeline runs. The prompt also enforces constraint 2 ("You must NOT change dates, company names, or job titles") — so non-determinism is scoped to wording variation within pre-approved zones, not structural surprise.

---

#### Q: Walk me through your approach to prompt design for a production feature — how does it differ from how a researcher would approach it?

**Repo evidence:** `core/prompts/` — versioned prompt files (resume_mutate_v1/v2/v3.txt, jd_extract_v1.txt, eval_resume_relevance_v1.txt) loaded via `core/prompts/__init__.py`

**Your answer:** Prompts are version-controlled `.txt` files (v1, v2, v3) tracked in git — diffable, reviewable in PRs, and independently deployable by bumping a version constant. The v3 mutation prompt defines 3 typed operations (REWRITE, SWAP, GENERATE) with exhaustive non-negotiable constraints — including LaTeX safety rules that prevent compilation failures from bare `^`, `~`, or unescaped math-mode delimiters. A researcher would iterate in a notebook and optimize for output quality alone; production prompt design also requires compilation safety, escape handling, version pinning, and a defined structured output contract (the JSON mutations schema). The evolution from v1 to v3 is observable in the commit history and directly reflects production failures encountered.

---

#### Q: How do you think about user trust in AI features? What design patterns build it and what patterns destroy it?

**Repo evidence:** `evals/hard.py:135–224` — per-bullet fabrication detector with numeric drift checking and multi-word entity detection; `docs/decisions.md` ADR-11

**Your answer:** The forbidden claims checker (`evals/hard.py`) inspects every mutated resume bullet against a corpus of original bullets, the bullet bank, the JD text, and the candidate profile — flagging any new numeric values (%, $, counts) or multi-word proper nouns not grounded in the source material. Only flagged bullets are reverted; clean mutations are kept. This is trust-by-constraint: the user can rely on the output being grounded because the system verifies it mechanically, not via prompt instruction alone. The pattern that destroys trust — which the repo guards against — is silent quality degradation: ADR-17 documents that `except Exception: return {}` without logging erodes output quality for weeks before anyone notices.

---

#### Q: What's your mental model for when to fine-tune a model vs. use RAG vs. use prompt engineering for a new AI feature?

**Repo evidence:** `profile/bullet_bank.json` + `agents/inbox/bullet_relevance.py` — structured bullet bank as explicit retrieval corpus; `profile/skill_index.json` — pre-indexed resume skills with synonym expansion

**Your answer:** The repo uses structured retrieval + prompt engineering rather than fine-tuning or vector RAG. The bullet bank is a curated JSON file of pre-approved phrasings with IDs and tags — the mutation prompt can SWAP in a bank entry by ID. This was a deliberate choice over pgvector/Pinecone: the candidate's corpus is small (~50 bullets), deterministic ID-based lookup is auditable, and the bank doubles as a ground truth for the truthfulness guard. Fine-tuning was never considered — the domain is too narrow and the training set too small. The model is swappable via env var (OpenRouter gateway), making the prompt engineering layer the real IP rather than any model-specific training.

---

#### Q: How do you approach the "last mile" problem — LLM output is mostly good but wrong in specific ways that users notice. What do you do?

**Repo evidence:** `docs/decisions.md` ADR-11 — evolution from all-or-nothing reversion to per-bullet granularity; `evals/hard.py:60–119` — `_COMMON_SKIP_WORDS` skip set (50+ entries)

**Your answer:** The repo's truthfulness guard went through exactly this problem. The original all-or-nothing check (if any bullet was flagged, revert the entire resume) produced too many false positives — JD-sourced terms like "data pipeline" and sentence-start words like "Led" would trigger full reversion. The fix was per-bullet granularity (ADR-11): check each bullet individually, build a skip set of common-but-non-entity words, and only revert flagged bullets. The "wrong in specific ways" pattern here was fabrication of numbers and named entities — addressed by separate detection (numeric drift vs. multi-word entity sequences). The lesson: scope your validation to the actual failure mode, not the broadest possible constraint.

---

#### Q: Walk me through how you'd instrument an AI feature for monitoring — what signals tell you it's degrading?

**Repo evidence:** `evals/logger.py` + `core/db.py` runs table + `docs/decisions.md` ADR-15 — per-run telemetry with eval_results JSON, latency_ms, cost_estimate, token counts

**Your answer:** Every pipeline run persists: token counts (prompt + completion), latency_ms, cost_estimate, and an `eval_results` JSON blob containing compile_success, forbidden_claims_count, edit_scope_violations, and soft eval scores (resume_relevance, jd_accuracy). ADR-15 added the same telemetry to Profile and Article agents after they had zero observability. The CI gate also prints a live-DB informational report (non-blocking) showing trend data across all historical runs. The leading degradation signals are: rising forbidden_claims_count (model producing hallucinations), falling compile_success rate (prompt changes breaking LaTeX output), and rising latency (model provider routing issues).

---

#### Q: How do you handle the case where an AI feature works in demos but breaks under the diversity of real user inputs?

**Repo evidence:** `evals/dataset.py` + `docs/decisions.md` ADR-09 — fixture-based CI gate replacing live-DB evaluation after dev-run pollution

**Your answer:** ADR-09 directly addresses this. The original CI gate queried the live PostgreSQL database for eval metrics — but developer and exploratory runs polluted the data, making the gate unreliable. The fix was a curated fixture dataset (`evals/dataset.py`) with 12 JD inputs representing diverse real patterns. Each fixture has known expected behavior. When a new failure mode is discovered from production use, a fixture encoding that input is added. The discipline of "new production bug → new fixture" is what closes the demo-vs-production gap over time.

---

#### Q: What's your approach to building AI features that are robust to adversarial users?

**Repo evidence:** `app.py` webhook secret check; `docs/decisions.md` ADR-19–20 — SSRF protection on URL fetch, Telegram chat ID allowlist (`TELEGRAM_ALLOWED_CHAT_IDS`)

**Your answer:** Three defensive layers in the repo. First, Telegram webhook secret verification (`X-Telegram-Bot-Api-Secret-Token`) ensures requests come from Telegram, not arbitrary callers. Second, a chat ID allowlist (`TELEGRAM_ALLOWED_CHAT_IDS` env var, ADR-20) prevents unauthorized users from driving LLM costs. Third, SSRF protection on URL ingestion (ADR-19) blocks cloud metadata endpoint access when users submit URLs. Additionally, ADR-16 treats all LLM-extracted values as untrusted data at the boundary: `json.loads()` always wrapped in try/except, strings guarded with `or ""`, extracted values escaped before query interpolation.

---

#### Q: Walk me through how you think about latency UX for AI features — what's acceptable, and how do you use streaming?

**Repo evidence:** `core/llm.py:129–158` — `resolve_costs_batch()` using `ThreadPoolExecutor` for parallel deferred cost resolution; `evals/ci_gate.py:39` — `LATENCY_THRESHOLD_MS = 60_000`

**Your answer:** The repo uses deferred-and-batched non-critical work to minimize perceived latency. OpenRouter cost resolution takes 500–1500ms per LLM call — if done inline, a 5-call pipeline adds 7+ seconds. Instead, all `generation_id`s are collected during the pipeline, then resolved in parallel via `ThreadPoolExecutor(max_workers=5)` at pipeline end. The user gets their resume PDF and drafts without waiting for cost accounting. The CI latency gate is ≤60s total pipeline end-to-end. Streaming isn't implemented (Telegram bot returns a completed message), but the design principle is the same: return the value-bearing artifact first, settle accounting after.

---

#### Q: How do you structure an A/B test for an AI feature where the improvement is qualitative, not just quantitative?

**Repo evidence:** `evals/soft.py:40–59` — LLM-judge with `DEFAULT_REPEAT=3` and median aggregation; `docs/decisions.md` ADR-05 — mutation cap removal evaluated against density-rule variant

**Your answer:** The soft eval system is the repo's answer to qualitative measurement. An LLM judge evaluates resume relevance to the JD and JD extraction accuracy, running 3 times per sample and returning the median to reduce variance. ADR-05 documents the qualitative A/B that led to removing the 3-mutation cap: the density-rule variant (max 5 bullets/role, weighted by relevance) was compared against the fixed-cap variant on the same 12 fixture inputs, comparing soft eval scores and manual spot-checks. The evaluation principle: multi-run median LLM judge + fixed input set + a documented decision in the ADR before committing the change.

---

### New Developments

---

#### Q: How has the speed of model capability improvement changed how you plan product roadmaps around AI features?

**Repo evidence:** `.env.example:3–4` — `LLM_FALLBACK_MODELS` lists 7 distinct free models; `docs/decisions.md` ADR-03 — OpenRouter gateway for model agnosticism

**Your answer:** The repo deliberately avoids roadmap bets on specific models. The OpenRouter gateway abstracts model selection behind an env var — swapping from Gemma to Llama to DeepSeek-R1 requires no code change. The fallback chain (stepfun, qwen, llama-3.3-70b, deepseek-r1, and others) means new capable free models are usable the day they appear on OpenRouter without a deploy. This shifts roadmap investment toward pipeline logic, eval infrastructure, and prompt versioning — the parts that don't become obsolete when a better model ships.

---

#### Q: What's your take on building on top of proprietary APIs vs. open-source models for a startup product?

**Repo evidence:** `docs/decisions.md` ADR-03 — explicit three-way comparison (OpenAI direct, OpenRouter, self-hosted); `.env.example:2–4` — free-tier open-source models as default

**Your answer:** ADR-03 documents this decision explicitly: direct OpenAI ($0.01–0.03/call, model lock-in) was rejected in favor of OpenRouter with free-tier open-source models as the default. The free model cascade covers development and light production use at $0.00/run. Switching to a proprietary model (Claude Sonnet, GPT-4) requires only an env var change — no code diff. The tradeoff accepted: free-tier models have higher output variance, so the truthfulness guard and structured eval infrastructure compensate for weaker model consistency. The defensible position is the pipeline and evals, not the model.

---

#### Q: How has the emergence of multi-modal models changed what's possible to build as an individual or small team?

**Repo evidence:** `agents/inbox/ocr.py` + `agents/inbox/adapter.py` photo handler — pytesseract OCR for JD screenshot ingestion before LLM extraction

**Your answer:** The repo handles multi-modal input (JD screenshots via Telegram) via pytesseract OCR rather than a vision model. This is a practical small-team pattern: OCR is free, deterministic, and doesn't require a multi-modal model API. The LLM step (JD extraction) receives text output from OCR, not the raw image — decoupling image parsing from text understanding. Emergence of capable vision models means this could be simplified (image → structured JD in one call), but the current architecture keeps the two concerns independently testable.

---

#### Q: What's your opinion on "wrapper companies" — products that are essentially prompts around a frontier model? What's defensible?

**Repo evidence:** `core/router.py` (deterministic classifier), `evals/` (full eval pipeline), `agents/inbox/resume.py` (custom mutation engine + skill matching), `core/prompts/` (versioned prompts)

**Your answer:** The repo shows what's defensible: the pipeline logic surrounding the LLM, not the model. The deterministic router, per-bullet truthfulness guard, editable-region constraints, LaTeX compilation engine, and curated eval fixture dataset are all model-agnostic. If a major provider launched a "tailored resume" feature tomorrow, they'd have the model but not the domain-specific logic — the 5 master resume variants, the bullet bank, the fabrication detection tuned for resume claims, and the 17+ ADR-documented design decisions. The prompt is the least defensible part; the pipeline and eval infrastructure are the moat.

---

#### Q: How do you think about model provider risk and dependency as part of your architecture decisions?

**Repo evidence:** `core/llm.py:61–76` — `_is_model_endpoint_error()` detecting 6 failure patterns; `core/llm.py:207–219` — automatic fallback chain iteration across providers

**Your answer:** The LLM gateway implements automatic provider failover: when a model endpoint returns "no endpoints found," "not available," "rate limit," or 429, it catches the error and retries with the next model in the fallback chain — transparently to callers. 7 free-tier models span 4 different providers (Qwen/Alibaba, Meta, Mistral, DeepSeek, OpenAI, Arcee), so a single provider outage doesn't cascade. Provider risk is further mitigated by the OpenRouter intermediary — a single API contract routes to multiple providers. The cost: an extra network hop (~50ms) and dependency on OpenRouter availability, documented explicitly in ADR-03.

---

#### Q: What new product categories have become viable because of recent LLM capability improvements that weren't viable 2 years ago?

**Repo evidence:** None found — prep this from first principles.

**Your answer:** Personalized document generation at scale (resume tailoring, cover letters, legal document drafts) required expensive human labor or produced generic low-quality output before LLMs could reliably follow structured multi-constraint instructions. Job application automation like this repo — where the LLM must simultaneously follow LaTeX syntax rules, preserve numeric metrics, respect editable-region scope, and match JD vocabulary — wasn't viable before models could reliably produce structured, constraint-following output.

---

#### Q: How has the cost of running LLM-powered features changed the economics of building AI products?

**Repo evidence:** `evals/ci_gate.py:39` — `COST_THRESHOLD = 0.15` USD per run; `.env.example:3–4` — free-tier cascade; `docs/decisions.md` ADR-06 — deferred cost resolution

**Your answer:** The repo runs the entire pipeline (JD extraction + resume mutation + 3 outreach drafts) on free-tier models by default — $0.00/run during development. The CI gate enforces ≤$0.15/run as the production ceiling. Cost resolution is deferred (ADR-06) because inline lookups add 1–2s latency — cost is a reporting metric, not a control signal. This architecture was only possible because capable free-tier models exist on OpenRouter. Two years ago, the same pipeline at GPT-4 rates ($0.03/call × 5 calls) would have made the economics marginal for a solo project.

---

#### Q: What's your take on agentic products — what's genuinely ready to ship vs. what requires too much human supervision to be useful?

**Repo evidence:** `agents/inbox/planner.py:1–75` — deterministic `ToolPlan` with zero LLM; `agents/inbox/executor.py` — retry-bounded step execution with no open loop

**Your answer:** The repo's "agentic" design is deliberately constrained: the planner produces a deterministic ordered step list (no LLM, no dynamic branching) and the executor runs each step with bounded retry logic. There's no autonomous decision to add or remove pipeline steps at runtime. This is what's ready to ship — fixed-topology pipelines with LLM execution at specific constrained steps. Open-ended agent loops (where the model decides what tool to call next based on intermediate results) require too much supervision at current reliability levels. The planner/executor split (ADR-08) is specifically the architectural answer to "make it shippable" — all intelligence is in the bounded executor handlers, not a self-directing agent.

---

#### Q: How do you think about evals-driven development for AI products — what does a good eval pipeline look like at an early-stage company?

**Repo evidence:** `evals/` full directory — `ci_gate.py`, `hard.py`, `soft.py`, `dataset.py`, `logger.py`, `report.py`; `docs/decisions.md` ADR-09

**Your answer:** The repo has a complete early-stage eval pipeline: hard gates (schema validation, compile success, fabrication detection, cost, latency) via curated fixtures that block CI; soft LLM-judge metrics for qualitative signals that trend over time; per-run telemetry logged to PostgreSQL; and a `python main.py ci-gate` command for local and CI use. ADR-09 is the key lesson: don't use your live DB as your eval dataset — development runs pollute it. A curated fixture set of 12 diverse inputs with known expected behavior is more reliable than hundreds of uncontrolled historical runs. Start with hard gates (binary, deterministic), add soft evals once the hard gates are stable.

---

#### Q: How has the "build vs. buy" decision changed for AI infrastructure — what do you build, what do you use managed services for?

**Repo evidence:** `docs/decisions.md` ADR-03, ADR-10, ADR-13 — managed LLM via OpenRouter, managed Postgres via Railway, unified Google OAuth; `agents/inbox/executor.py` + `evals/` — custom pipeline and eval logic

**Your answer:** The repo's pattern: buy managed for commodity (LLM access via OpenRouter, PostgreSQL via Railway, OAuth via Google), build custom for domain logic. The planner/executor, truthfulness guard, bullet bank retrieval, editable region parsing, eval fixture dataset, and prompt versioning system are all custom — because that's where the product's correctness lives. SQLite was replaced with managed Postgres (ADR-10) when concurrent webhooks caused file-level lock contention. Self-hosted LLM (Ollama) was rejected (ADR-03) because GPU costs exceed managed API costs at this scale. Rule: anything a managed service does adequately, buy; anything the product's quality depends on, build and test.

---

#### Q: What do you think about the shift toward reasoning models for product use cases — when is "thinking" worth the latency?

**Repo evidence:** `.env.example:4` — `deepseek/deepseek-r1-0528:free` in fallback chain; `evals/ci_gate.py:39` — `LATENCY_THRESHOLD_MS = 60_000`

**Your answer:** The fallback chain includes DeepSeek-R1 as an option, but the use cases here (JD extraction → structured JSON, resume mutation → structured mutations JSON) are constrained structured extraction tasks, not multi-step reasoning chains. Thinking tokens add latency without proportional benefit when the output schema is fixed and the reasoning is shallow. The CI latency gate (≤60s total pipeline) creates a concrete budget: a reasoning model that adds 30–40s of thinking on a step that non-reasoning models handle in 5s is a regression. Reasoning models are worth the latency when the task requires multi-hop deduction — not structured JSON extraction from a provided context.

---

### Applied / Scenario

---

#### Q: You're building a writing assistant that helps users improve their emails. Walk me through your product decisions from prompt design to eval to UX to launch.

**Repo evidence:** `core/prompts/draft_email_v1.txt` + `evals/soft.py` + `core/prompts/resume_mutate_v3.txt` — the repo's draft generation and eval pattern

**Your answer:** Use the repo's pattern directly. Prompt: version-controlled `.txt` file with typed operations and non-negotiable constraints (what the LLM can and can't do), with a structured JSON output contract. Eval: hard gate on format compliance + soft LLM-judge score for quality (run 3×, take median). UX: set expectations by bounding what changes — the editable-region concept translates to "we'll improve phrasing but won't change names, dates, or factual claims." Launch gate: all hard evals pass on a fixture dataset of diverse input styles, soft score ≥ baseline, cost ≤ threshold. The key difference from research: the prompt has LaTeX safety rules (or format safety rules for email), the eval has a curated input fixture, and every version is a git-diffable file.

---

#### Q: Your AI feature is working well but users aren't adopting it. What are your hypotheses and how do you investigate?

**Repo evidence:** `agents/inbox/agent.py:38–42` — `ApplicationPack.collateral_generation_status` and `collateral_generation_reason` fields; `docs/decisions.md` ADR-14 — `user_vetted` flag distinguishing Telegram-submitted from other sources

**Your answer:** The `ApplicationPack` records `collateral_generation_status` and `collateral_generation_reason` on every run — this surfaces whether users are requesting collateral (email, LinkedIn, referral drafts) or not. The `user_vetted` flag in the runs table (ADR-14) distinguishes Telegram-submitted jobs (the primary surface) from other sources. First hypothesis: users don't know how to trigger the feature — check if jobs without collateral have `blocked_missing_selection` as the reason. Second: friction in intake — check `completed_runs_with_errors` in `core/pipeline_checks.py`. Third: output quality too low to use — check soft eval score trends. Each hypothesis maps to a DB query.

---

#### Q: You need to add AI-powered search to an existing product. Walk me through your build vs. integrate decisions.

**Repo evidence:** `agents/inbox/resume.py:178–327` — custom skill matching with synonym expansion; `profile/skill_index.json` — pre-indexed resume skills

**Your answer:** The repo chose custom keyword matching + synonym expansion (with a `skill_index.json` for pre-indexed resume skills) over vector search for resume selection. Rationale: corpus is small (5 master resumes), deterministic ranking is testable without embeddings, and the synonym map is auditable — you can see exactly why "AI/ML" matches "machine learning." At this scale, vector search infrastructure (pgvector, Pinecone) adds dependency and cost with marginal precision gain. Build custom matching when the corpus is small and auditability matters; integrate vector DB when the corpus is large (>1K documents) and semantic similarity is the right ranking signal.

---

#### Q: Design an AI document review tool for a legal team — what are the accuracy requirements and what happens when the model is wrong?

**Repo evidence:** `evals/ci_gate.py:37` — `FORBIDDEN_CLAIMS_MAX = 0` (zero tolerance); `docs/decisions.md` ADR-17 — graceful degradation with mandatory visibility

**Your answer:** The repo's answer to high-consequence LLM output is zero-tolerance hard gates + mandatory visibility on every fallback. Forbidden claims threshold is 0 — not 1, not 2. When a mutation would introduce an ungrounded claim, it's reverted rather than allowed through. ADR-17 documents the principle: silent failures are worse than crashes — a crash gets fixed immediately, a silent fallback (like `except Exception: return {}`) degrades quality for weeks unnoticed. For a legal team: every model decision needs a `reason` field (the mutation prompt already requires this), every review output needs a confidence signal, and results below a threshold surface to a human reviewer. The audit trail is in the runs table: `eval_results`, `context_json`, `user_vetted`.

---

#### Q: You have a working AI prototype and need to turn it into a production feature in 4 weeks. Walk me through how you prioritize.

**Repo evidence:** `docs/decisions.md` ADR-07–08 — sprint 3 phases in 2 days, then planner/executor refactor for testability; ADR-16 — LLM output hardening added after 3 production bugs

**Your answer:** The repo's own build timeline is the answer. Week 1: happy path working end-to-end + LLM output hardening immediately (ADR-16 — the 3 production bugs happened in the very first production use session; they should have been addressed before, not after). Week 2: testability refactor (ADR-08 planner/executor split) and basic eval fixture dataset. Week 3–4: cost monitoring, CI gate with hard thresholds, and observability (per-run telemetry, ADR-15). The key lesson from ADR-16: LLM output hardening is week 1 work, not week 4. The three bugs (None in skills list, string injection, malformed JSON crash) are all predictable LLM-trust failures that will appear immediately in real use.

---

#### Q: Your AI feature costs $0.20 per user interaction. You have 10K MAU. At what scale does this become a problem, and what do you do about it?

**Repo evidence:** `evals/ci_gate.py:39` — `COST_THRESHOLD = 0.15`; `.env.example:3–4` — free-tier cascade with 7 options; `docs/decisions.md` ADR-03 — model swappability via env var

**Your answer:** 10K MAU × $0.20 = $2K/month — meaningful burn at early stage. The repo's cost architecture: CI gate enforces ≤$0.15/run, free-tier models are the default (7 options via OpenRouter cascade), and model swapping requires zero code change. Cost levers in order: (1) switch to free-tier models — instant, no quality regression for most inputs; (2) cache JD extractions for duplicate JD hashes (the DB already stores `jd_hash` in the jobs table — reuse extracted JD for repeated submissions of the same listing); (3) batch LLM calls if multiple interactions share a session context. The deferred cost resolution (ADR-06) prevents cost monitoring from adding latency, so you measure accurately without slowing the experience.

---

#### Q: Walk me through how you'd approach building an AI feature in a regulated industry where you need audit trails and explainability.

**Repo evidence:** `core/db.py` runs table with `eval_results`, `context_json`, `latency_ms`, `cost_estimate`; `core/prompts/resume_mutate_v3.txt:49–52` — `reason` field per mutation in output JSON; `docs/decisions.md` ADR-14 — `user_vetted` provenance flag

**Your answer:** The repo's runs table is the audit trail foundation: every execution has a `run_id`, `created_at`, `latency_ms`, `cost_estimate`, structured `eval_results` JSON, `context_json` with artifact paths, `user_vetted` flag for source provenance, and `error_count`. The mutation prompt requires a `reason` field for every change — so the LLM explains each mutation decision in the output JSON, not just the result. Explainability is baked into the output contract. For regulated environments, this extends to: immutable run log (append-only writes), per-mutation human approval flag, and a separate audit table that can't be overwritten — but the schema and prompt design already provide the raw material.

---

### Failure Modes

---

#### Q: Walk me through a common failure mode where an AI product works great in the founder's demos but fails for regular users. What causes it?

**Repo evidence:** `docs/decisions.md` ADR-09 — live DB pollution from dev runs making CI metrics look healthy; `evals/dataset.py` — curated fixture dataset as the fix

**Your answer:** ADR-09 is the repo's direct experience with this. The CI gate originally measured quality against the live PostgreSQL database — which was full of developer runs using well-formed, hand-crafted test JDs that the developer had personally optimized against. Every metric looked healthy. When real users submitted diverse, messy JD text (multi-column formatting, OCR noise, partial copy-pastes), the failure modes that had always existed were finally exercised. The fix was separating demo data from eval data: a curated fixture dataset with intentionally diverse and edge-case inputs. The cause is always the same — your test distribution is biased toward inputs you've seen and optimized for.

---

#### Q: What's wrong with using your own (biased) usage patterns as the primary test case for an AI feature?

**Repo evidence:** `docs/decisions.md` ADR-09 — the exact problem that motivated the fixture-based CI gate replacing live DB metrics

**Your answer:** ADR-09 is the canonical example. Developer runs (structured, well-formed JDs from familiar companies) trained the implicit expectation of what inputs look like. When the CI gate measured against those runs, everything looked fine. Real user inputs — screenshots with OCR noise, JDs pasted from PDFs with formatting artifacts, non-standard section headers — hit code paths never exercised by the developer's own usage. The fixture dataset was built specifically by adding inputs that represent the distribution of real user submissions, not the developer's sample. Your own usage biases toward the happy path you designed and have already seen work.

---

#### Q: What failure mode emerges when you ship an AI feature with no fallback for when the model returns garbage?

**Repo evidence:** `docs/decisions.md` ADR-16 — 3 production bugs from trusting LLM output: None in skills list, Drive query string injection, malformed JSON crash

**Your answer:** ADR-16 documents three real production bugs that all stemmed from the same root cause: trusting LLM output. Bug 1: `None` in the JD skills list (LLM returned a list containing a null element) caused a crash in `bullet_relevance.py`. Bug 2: a company name with an apostrophe from LLM extraction was interpolated directly into a Drive API query string — injection vulnerability. Bug 3: the article agent crashed when the LLM returned malformed JSON despite `json_mode=True`. The fix for all three: treat LLM output as untrusted data — `try/except` on all JSON parsing, `or ""` guards on all string values, type checks before iteration. `json_mode=True` is a hint, not a contract.

---

#### Q: Walk me through a scenario where over-promising AI capability to users created backlash — what did the product team miss?

**Repo evidence:** `core/prompts/resume_mutate_v3.txt:8–16` — NON-NEGOTIABLE constraints (preserve numeric values, don't invent metrics, don't change company names); `docs/decisions.md` ADR-05 — evolution from unconstrained mutations

**Your answer:** ADR-05 shows the evolution. Early versions of the mutation system allowed the LLM to change as many bullets as it wanted — and it would sometimes produce resumes with inflated or invented achievements. Users who expected light tailoring got radical rewrites with fabricated metrics. The constraints block in v3 (NON-NEGOTIABLE: preserve all numeric values, don't invent specific metrics, don't claim work at companies not in the resume) were added specifically because the unconstrained LLM would over-tailor. The product team missed that users trust the output to be truthful, not just relevant — and "more tailored" is not the same as "better."

---

#### Q: What's the most common mistake founders make when choosing which AI features to build first?

**Repo evidence:** `docs/decisions.md` ADR-02 — deliberate choice of deterministic routing over LLM; ADR-16 — LLM trust failures appearing in the first production session

**Your answer:** The repo's ADR history shows two related mistakes. First: using LLM where deterministic logic suffices. ADR-02 documents the explicit decision to NOT use LLM for intent routing — founders default to "LLM for everything" because it's easy to prototype. The cost ($0.001–0.01/message), latency (200–500ms), and non-determinism accumulate fast. Second: building the core feature without LLM output hardening. ADR-16 shows that 3 production bugs appeared within the first real usage session — all from trusting LLM output. Founders build the happy path demo, ship it, and discover that LLM outputs are untrusted data at the boundary only after they break.

---

#### Q: What goes wrong when you optimize your AI product purely for demo impressiveness rather than repeat usage?

**Repo evidence:** `evals/soft.py:40–59` — LLM judge measuring resume relevance (not visual polish); `docs/decisions.md` ADR-11 — per-bullet truthfulness as the repeat-usage metric

**Your answer:** The resume mutation feature could be optimized for demo impressiveness: add lots of keywords, rephrase everything to sound impressive, inflate numbers slightly. The demo would look great. The hard gates specifically prevent this — forbidden claims = 0 means the LLM can't add new metrics to make a bullet look better. The soft eval measures relevance to the actual JD, not surface impressiveness. ADR-11 (per-bullet truthfulness) was added specifically because the unconstrained LLM produced impressive-looking output that contained fabrications. Repeat-usage quality is measured by whether the resume is actually usable in an application — and that requires grounded truth, not keyword stuffing.

---

#### Q: Walk me through how "prompt brittleness" — where minor input changes cause major output changes — shows up as a product failure.

**Repo evidence:** `core/prompts/resume_mutate_v1.txt` → `v3.txt` evolution; `core/prompts/resume_mutate_v3.txt:17–21` — explicit LaTeX safety constraints added to prevent compilation failures

**Your answer:** The mutation prompt evolved through 3 versions specifically because of brittleness. v3 added explicit LaTeX safety rules (lines 17–21) after discovering that the LLM would sometimes output bare `^` or `~` characters — invisible in plain text, but causing pdflatex compilation failures (hard gate: compile success < 95%). A minor change in JD content or bullet phrasing would cause the LLM to introduce a superscript or approximation symbol in a slightly different way, breaking compilation intermittently. The fix: name the specific failure modes explicitly in the prompt ("Never use a bare caret"), provide the correct form ("spell the concept out"), and preserve math-mode pairs verbatim. Brittleness shows up as intermittent failures that are hard to reproduce and hard to debug.

---

#### Q: What are the signs that an AI product has been shipped too early without sufficient eval infrastructure?

**Repo evidence:** `docs/decisions.md` ADR-07 (rapid sprint with thin tests), ADR-09 (eval gate added retroactively), ADR-16 (output hardening added after production bugs)

**Your answer:** ADR-07 documents the 2-day sprint that shipped phases 1–3 with "thin integration tests and optimistic error handling." ADR-16 appeared immediately after: 3 production bugs in one session, all from LLM-trust failures that would have been caught by an output hardening standard. ADR-09 followed: the CI gate was querying polluted live-DB data that made quality look better than it was. The signs: (1) you discover bugs only when real users submit unexpected inputs; (2) your CI gate passes on developer runs but fails on diverse inputs; (3) LLM errors crash the pipeline rather than degrading gracefully; (4) you have no way to compare the current version against a previous one on a standard test set.

---

#### Q: What's wrong with using your development dataset (which you've iterated on) as your benchmark for production quality?

**Repo evidence:** `docs/decisions.md` ADR-09 — live DB gate replaced by curated fixture dataset after dev-run contamination

**Your answer:** ADR-09 is the direct answer. The live-DB gate queried historical run data — which consisted largely of developer runs using JDs the developer had personally selected and optimized against. When a new version broke on a specific JD, the developer fixed the code and that JD was now "handled." The benchmark tracked the developer's known-good inputs, not the production distribution. The fix: a separate curated fixture dataset where each entry was added because it represented a failure mode or edge case found in the wild — not because it was convenient to test with. Development data leaks your optimizations into your benchmark, making benchmarks look better than production reality.

---

#### Q: Walk me through how an AI product that doesn't handle uncertainty gracefully erodes user trust faster than a non-AI alternative.

**Repo evidence:** `docs/decisions.md` ADR-17 — "silent failures are worse than crashes"; `agents/inbox/agent.py:50` — `errors: list[str]` in ApplicationPack; `evals/hard.py:40–54` — explicit boolean return from `check_edit_scope`

**Your answer:** ADR-17 documents the concrete case: `_load_profile()` had `except Exception: return {}` — if the profile file was missing or corrupt, resume mutations proceeded with no profile context, producing generic output. No error, no warning, no degradation signal. Users experienced steadily worsening resume quality with no explanation. The trust erosion: users who got good results early started getting worse results later, with no feedback that anything had changed. The principle ADR-17 encodes: a crash gets fixed immediately (it's visible); a silent fallback degrades quality for weeks. The `ApplicationPack.errors` list exists specifically to surface non-fatal degradations visibly rather than burying them. A non-AI tool fails predictably — an AI tool can fail silently by producing plausible-but-wrong output, which is far more damaging to trust.

---

## Section B — Repo-Specific Deep-Dives

*Questions that only THIS codebase can answer.*

---

#### Q: Why does the router use zero LLM calls for intent classification when you already have an LLM gateway wired up? Wouldn't LLM be more accurate?

**Where to look:** `core/router.py:1–8` (module docstring) + `docs/decisions.md` ADR-02

**Answer:** ADR-02 documents the explicit comparison. LLM-based classification would add $0.001–0.01 per message, 200–500ms latency, and non-determinism (the same message could route differently on two calls). The deterministic router uses regex keyword matching and returns a `RouteResult` with a `reason_code` — making routing 100% testable without mocks and free to run. The accepted tradeoff: ambiguous inputs that don't match any pattern return `CLARIFY` rather than being routed. For a personal job-search tool where the input domain is well-defined, this is the correct call.

---

#### Q: The mutation prompt has three operation types (REWRITE, SWAP, GENERATE) but they weren't always there. What forced this structure?

**Where to look:** `core/prompts/resume_mutate_v3.txt:3–6` + `docs/decisions.md` ADR-05

**Answer:** ADR-05 documents the V2 mutation pipeline introduced in commit `43d56bf`. The original prompt gave the LLM an unstructured "edit these bullets" instruction — the model would do whatever seemed best, which included inventing achievements, changing structure, and producing inconsistent output. The typed operation structure was introduced to constrain LLM behavior to three known-safe modes: REWRITE (modify wording only, preserve metrics), SWAP (replace with pre-approved bank entry by ID — grounded in the bullet bank), GENERATE (new bullet allowed only if explicitly grounded in profile context + allowed_tools). Each type has different truthfulness constraints, and the CI gate can check them differently.

---

#### Q: Why did the project switch from SQLite to PostgreSQL mid-build rather than starting with Postgres?

**Where to look:** `docs/decisions.md` ADR-10 + `core/db.py`

**Answer:** SQLite was fine for single-threaded local development. The production failure mode only appeared when Telegram started sending concurrent webhook updates — SQLite's file-level lock caused timeouts and lost writes under parallel processing. The switch was triggered by a real production incident, not pre-emptive architecture. The migration kept the same schema DDL and swapped the access layer from `sqlite3` to `psycopg2`. Lesson: the failure mode wasn't predictable from local testing because local development doesn't simulate concurrent webhook delivery.

---

#### Q: The CI gate uses a curated fixture dataset, but the code also prints live-DB stats. Why two sources, and why doesn't the live DB block CI?

**Where to look:** `evals/ci_gate.py:127–188` + `docs/decisions.md` ADR-09

**Answer:** ADR-09 documents the shift. The live DB was contaminated by developer runs using hand-picked JDs the developer had optimized against — metrics looked healthy because the code was tuned to them. The fixture dataset (12 curated JDs representing diverse real patterns) is immutable — test runs never add to it. The live DB report is printed as informational context (trend data, outlier detection) but doesn't gate CI, because a single bad manual test run would make it flaky. Current fixture metrics: compile 100%, forbidden 0, violations 0, $0.07/run avg, 33s avg latency. Live DB report is for situational awareness only.

---

#### Q: Why does cost resolution happen at pipeline end in a batch rather than inline after each LLM call?

**Where to look:** `core/llm.py:129–158` — `resolve_costs_batch()` + `docs/decisions.md` ADR-06

**Answer:** OpenRouter's `/api/v1/generation` endpoint takes 500–1500ms to populate after a completion response. If resolved inline, a 5-LLM-call pipeline adds 2.5–7.5s of pure cost-accounting latency to every user interaction. Instead, all `generation_id`s are collected during the pipeline, then resolved in parallel via `ThreadPoolExecutor(max_workers=5)` with a single 1-second upfront wait. The user gets their resume PDF without waiting for cost accounting. The known gap (documented in `AGENT_HANDOFF.md`): draft generation calls don't capture `generation_id`, so their costs are always $0.00 in the DB.

---

#### Q: You have an `EditableRegion` dataclass but resume selection scores the whole `.tex` file. Why aren't these the same thing?

**Where to look:** `agents/inbox/resume.py:24–29` (EditableRegion) vs `agents/inbox/resume.py:292–327` (compute_keyword_overlap)

**Answer:** Resume selection and resume mutation are different problems with different correctness requirements. Selection (pick the best base resume) needs to score the whole resume — all sections including education, skills header, and non-editable roles — against JD keywords. Mutation (change specific bullets) must be strictly scoped to `%%BEGIN_EDITABLE` regions to avoid touching dates, company names, or document structure. Conflating the two would mean either scoring only editable content for selection (losing most of the signal) or allowing mutation anywhere in the document (breaking the truthfulness contract). The separation keeps each concern correct independently.

---

#### Q: Why is the planner a zero-LLM pure function rather than an LLM-driven orchestrator that decides which steps to run?

**Where to look:** `agents/inbox/planner.py:1–20` + `docs/decisions.md` ADR-08

**Answer:** ADR-08 documents the split from a monolithic pipeline into planner + executor. The key insight: if the planner uses LLM to decide which steps to run, then testing the pipeline requires mocking the LLM, and a non-deterministic model can decide to skip resume mutation or add an extra step on a whim. By making the planner a pure function (input type detection → ordered ToolStep list), the execution topology is 100% testable without mocks and 100% deterministic from the same inputs. All intelligence — and all LLM calls — live in the executor's step handlers. New steps are added by writing a handler and adding it to the plan, without changing the planner logic.

---

#### Q: The LLM fallback chain has 7 models across 4 providers. Is this ordered by quality, by cost, or something else?

**Where to look:** `core/llm.py:61–76` — `_is_model_endpoint_error()`; `.env.example:3–4` — `LLM_MODEL` + `LLM_FALLBACK_MODELS`

**Answer:** The ordering is availability-based failover, not quality ranking. The primary model (`stepfun/step-3.5-flash:free`) is tried first. Fallbacks are tried only when the primary returns an endpoint error (not available, rate limit, 429) — not on output quality degradation. The list spans multiple providers (Qwen/Alibaba, Meta, Mistral, DeepSeek, OpenAI, Arcee) so a single provider outage doesn't cascade. Importantly, fallback only triggers on `_is_model_endpoint_error()` — other exceptions (network timeouts, unexpected API errors) propagate up and are caught by the executor's retry logic at a higher level.

---

---

## Cheat Sheet

*The 5 things you most need to know walking into this interview.*

1. **AI/no-AI boundary:** The deterministic router (zero LLM, pure regex, ADR-02) vs. LLM-only-where-necessary is the concrete answer to every "when do you use AI" question — `core/router.py` is your evidence.
2. **Eval infrastructure:** Two-tier system (hard gates on curated fixtures + LLM-judge soft scores) with fixture-based CI to avoid live-DB pollution — the ADR-09 story is your "evals-driven development" answer.
3. **LLM output is untrusted data:** ADR-16's 3 production bugs (None in list, string injection, malformed JSON) are the concrete example for every failure mode and last-mile question — memorize the three bug types and fixes.
4. **Prompt versioning:** `resume_mutate_v1/v2/v3.txt` in git, each version documenting why constraints were added — use this to answer "how does production prompt design differ from research."
5. **Graceful degradation with visibility:** ADR-17's principle ("silent failures are worse than crashes") + `pack.errors` accumulation pattern — this is your answer to trust, uncertainty handling, and monitoring questions.
