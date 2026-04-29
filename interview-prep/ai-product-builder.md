# Interview Prep FAQ: job-search-agent (`inbox-agent`)

**Role:** AI Product Builder
**Lens applied:** AI Product Builder / Indie AI Developer (with 1–2 patterns borrowed from AI Engineer (LLM))
**Generated from:** A webhook-first, multi-agent system that turns a Telegram-submitted JD (image / URL / text) into a tailored resume PDF + outreach drafts + a Drive folder, gated by hard/soft evals.
**Repo HEAD:** `03ebb4a`
**Generated on:** 2026-04-29

---

## Alignment Caveats

⚠️ **Alignment check skipped this run** (no `.alignment-cache.json` present and a fresh `codebase-docs-alignment` scan was deferred to keep this responsive). Answers below trust the README/PRD claims as-is — flag any quoted doc claim with "let me verify against the code" before parroting it in an interview.

Two known soft-drift hotspots worth reading critically before the interview:
- The README still says SQLite has been migrated to Postgres in [PRD.md:148](PRD.md#L148) ("PostgreSQL DB (migrated from SQLite)") — but the CI gate's docstring still talks about "actual SQLite run history" in [evals/ci_gate.py:22](evals/ci_gate.py#L22). The runtime code uses Postgres; the comment is stale.
- The README's Quick Start says `pip install -e ".[dev]"` but the repo also has `uv.lock` and a `package-lock.json` (Node) — there is no Node code path documented; if asked, say it's vestigial / for tooling only and you'd verify before claiming otherwise.

---

## Repo Map (one paragraph)

`inbox-agent` is a Python 3.9+ FastAPI service ([pyproject.toml:6](pyproject.toml#L6)) that receives Telegram webhooks, deterministically routes the message ([core/router.py](core/router.py)) to one of three agents — **Inbox** (executor: OCR → JD extraction → resume select → bounded resume mutation → LaTeX compile → Drive upload → Calendar → outreach drafts → eval log), **Profile** (read-only "represent Karan" agent grounded in `profile/profile.json` + `profile/bullet_bank.json`), and **Follow-Up** (cron-style nudge generator) — plus an Article agent. The Inbox agent is split planner→executor: [agents/inbox/planner.py](agents/inbox/planner.py) builds a typed `ToolPlan` with no LLM involvement, then [agents/inbox/executor.py](agents/inbox/executor.py) runs each step with retry. All LLM calls go through one gateway ([core/llm.py](core/llm.py)) pointed at OpenRouter, with model fallback chains and deferred cost resolution. Quality is gated by a fixture-based CI (`evals/ci_gate.py`) on five thresholds: compile ≥95%, forbidden_claims=0, edit_violations=0, cost ≤$0.15, latency ≤60s. Deploy target is Railway (Docker + managed Postgres). **If you only memorize one fact:** this is a *deterministic-router + planner/executor + eval-gated* AI product — the LLM is a sub-component, not the architecture.

---

## 1. Walk Me Through It

**Q: Walk me through what happens when a user pastes a JD URL into Telegram.**
A: The Telegram webhook hits `POST /telegram/webhook` (FastAPI in `app.py`); the message is normalized and passed to the deterministic router at [core/router.py:99](core/router.py#L99), which sees a URL and returns `AgentTarget.INBOX` with reason `url_input`. The Inbox agent's [run_pipeline()](agents/inbox/agent.py#L54) builds a `ToolPlan` via [build_tool_plan()](agents/inbox/planner.py#L1) — an ordered list of `ToolStep`s (`ocr → jd_extract → resume_select → resume_mutate → compile → calendar → drafts → drive_upload → db_log → eval_log`) — and the executor runs them with retry. Output: a tailored PDF, an A–F markdown report, optional outreach drafts, and a Drive folder link returned to Telegram.
📁 *See: [core/router.py:99-169](core/router.py#L99-L169), [agents/inbox/agent.py:54-77](agents/inbox/agent.py#L54-L77), [agents/inbox/planner.py:44-57](agents/inbox/planner.py#L44-L57)*

**Q: How is "the AI" actually wired in — what's a model boundary vs deterministic logic?**
A: Routing is 100% rules-based — regex + keyword scores, no LLM ([core/router.py:33-91](core/router.py#L33-L91)). The plan itself is also non-LLM ([agents/inbox/planner.py](agents/inbox/planner.py)). LLMs are used for: JD extraction (`core/prompts/jd_extract_v1.txt`), resume mutation (`resume_mutate_v3.txt`), three outreach drafts (`draft_email_v1.txt`, `draft_linkedin_v1.txt`, `draft_referral_v1.txt`), and two soft-eval judges. Every call goes through [core/llm.chat()](core/llm.py#L161) which centralizes model, fallback, JSON-mode, and token tracking.
📁 *See: [core/prompts/](core/prompts/), [core/llm.py:161-244](core/llm.py#L161-L244)*

**Q: Where does the user actually experience the AI — and what's the surface?**
A: Telegram is the entire UX. Input modalities: image (screenshot of JD), URL, or pasted text. Output: a chat reply with the Drive link + report path, plus three optional drafts (email, LinkedIn DM <300 chars, referral). There's no web UI — that's an intentional product choice: ship-via-chat keeps friction near zero and makes the "user vetted" signal trustworthy ([README.md:11-14](README.md#L11-L14), `jobs.user_vetted = 1` is the persisted provenance bit).
📁 *See: [README.md:11-14](README.md#L11-L14), [PRD.md:153-156](PRD.md#L153-L156)*

**Q: What is the multi-agent architecture and why three agents instead of one?**
A: Three agents with different read/write power: **Inbox** is the only one with tool permissions (OCR, curl, LaTeX, Drive, Calendar) — [PRD.md:57-64](PRD.md#L57-L64). **Profile** is read-only: it grounds answers about Karan in `profile.json`, `bullet_bank.json`, and base resumes; never executes a tool ([PRD.md:81-91](PRD.md#L81-L91), [agents/profile/agent.py:31-40](agents/profile/agent.py#L31-L40)). **Follow-Up** runs on a schedule, detects stale applications (+7d, no update), and generates nudges. The split exists because mixing "represent the user" with "take actions" is the failure mode that produces fabricated bullets — separating them makes the forbidden-claim guardrail trivially enforceable.
📁 *See: [PRD.md:38-103](PRD.md#L38-L103), [agents/](agents/)*

---

## 2. Common Technical Questions

**Q: How are prompts managed and versioned in this codebase?**
A: Prompts are flat `.txt` files under [core/prompts/](core/prompts/), suffixed `_v1`, `_v2`, `_v3`. Active resume mutation prompt is [resume_mutate_v3.txt](core/prompts/resume_mutate_v3.txt) — the v1/v2 files are kept for diff/regression. Eval judge prompts are `eval_resume_relevance_v1.txt` and `eval_jd_accuracy_v1.txt` and are loaded by version number from [evals/soft.py:53](evals/soft.py#L53). Versioning prompts as files (not strings) means a prompt change shows up cleanly in `git diff` and can be A/B'd by changing the version int.
📁 *See: [core/prompts/](core/prompts/), [evals/soft.py:53](evals/soft.py#L53)*

**Q: How does the system handle non-deterministic / wrong LLM outputs?**
A: Three layers. **(1) Schema validation** — JD output goes through `check_jd_schema()` ([evals/hard.py:13-28](evals/hard.py#L13-L28)) and fails the run if any required field is missing or wrong type. **(2) Bounded mutation** — resume edits are constrained to lines between `%%BEGIN_EDITABLE` / `%%END_EDITABLE` markers; anything outside is detected by `check_edit_scope()` ([evals/hard.py:40-54](evals/hard.py#L40-L54)) and the run fails. **(3) Forbidden-claim detector** — a heuristic in [evals/hard.py:135-200](evals/hard.py#L135-L200) flags mutated bullets that introduce numbers or capitalized entities not present in the original bullets, the bullet bank, the JD text, or the profile. Compile failure also triggers a revert to the unmutated resume.
📁 *See: [evals/hard.py:13-200](evals/hard.py#L13-L200), [agents/inbox/resume.py:34-60](agents/inbox/resume.py#L34-L60)*

**Q: Why OpenRouter instead of going direct to OpenAI/Anthropic?**
A: [core/llm.py:42-48](core/llm.py#L42-L48) constructs the client with `base_url=settings.openrouter_base_url`. The bet is provider portability: switching models is a config change, not a code change, and free-tier models are usable for non-critical paths. The price you pay is the cost-resolution dance — OpenRouter doesn't return cost in the completion response, so [resolve_generation_cost()](core/llm.py#L79) has to make a *separate* GET to `/generation?id=...` after a 1s delay, batched at the end of the pipeline ([core/llm.py:129-158](core/llm.py#L129-L158)) so it doesn't add latency per call.
📁 *See: [core/llm.py:79-158](core/llm.py#L79-L158)*

**Q: How is model fallback handled when a model is unavailable or rate-limited?**
A: [core/llm.py:209-219](core/llm.py#L209-L219) iterates a list `[primary, *fallbacks]`, catches errors matching the heuristics in `_is_model_endpoint_error()` ([core/llm.py:65-76](core/llm.py#L65-L76)) — "no endpoints found", "rate limit", 429, etc. — and tries the next model. Non-matching errors raise immediately. Fallback list is configured via `LLM_FALLBACK_MODELS` env var (comma-separated). Note: only the *first* attempt's model is the requested one; the cost/latency telemetry records `used_model`.
📁 *See: [core/llm.py:65-76](core/llm.py#L65-L76), [core/llm.py:209-244](core/llm.py#L209-L244)*

**Q: How are AI feature costs tracked per run and gated?**
A: Each `chat()` call returns an `LLMResponse` with `prompt_tokens`, `completion_tokens`, and a `generation_id` ([core/llm.py:236-244](core/llm.py#L236-L244)). After the pipeline completes, `resolve_costs_batch()` makes parallel HTTP calls to OpenRouter's `/generation` endpoint and sums the real (post-discount) USD cost. The total is checked against `COST_THRESHOLD = 0.15` in [evals/ci_gate.py:39](evals/ci_gate.py#L39); CI fails if average cost across the fixture set exceeds $0.15 per run.
📁 *See: [core/llm.py:129-158](core/llm.py#L129-L158), [evals/ci_gate.py:36-40](evals/ci_gate.py#L36-L40)*

**Q: How do you evaluate output quality at scale?**
A: Two tracks. **Hard evals** (deterministic, CI-gating) in [evals/hard.py](evals/hard.py): schema, compile, edit scope, forbidden claims, draft length, cost. **Soft evals** (LLM-judge) in [evals/soft.py](evals/soft.py): `score_resume_relevance` and `score_jd_accuracy` use versioned judge prompts and run **3 times each** with `statistics.median()` to dampen judge variance ([evals/soft.py:21-59](evals/soft.py#L21-L59)). Soft scores are reported but don't gate CI. The gate runs on a curated fixture dataset in `evals/dataset.py` — explicitly *not* live DB history, because exploratory dev runs would pollute it ([evals/ci_gate.py:8-12](evals/ci_gate.py#L8-L12)).
📁 *See: [evals/hard.py](evals/hard.py), [evals/soft.py:21-59](evals/soft.py#L21-L59), [evals/ci_gate.py:8-12](evals/ci_gate.py#L8-L12)*

---

## 3. Deep-Dive Questions

**Q: The forbidden-claims detector is heuristic, not an LLM. Walk me through how it actually works and where it fails.**
A: [check_forbidden_claims_per_bullet()](evals/hard.py#L135) builds an "allowed text" corpus from `original_bullets + bullet_bank + jd_text + profile_text` (LaTeX-normalized so `\%` → `%`). For each mutated bullet it: (1) regexes out every numeric token (`\b\d+(?:\.\d+)?%?\b`) and flags any not in the corpus — catches "increased revenue 47%" when the source said "increased revenue meaningfully"; (2) finds multi-word capitalized sequences like "Goldman Sachs" — flags any not in the corpus; (3) finds single capitalized words but suppresses anything in `_COMMON_SKIP_WORDS` (a hand-curated frozenset of 50+ verbs and generic nouns at [evals/hard.py:60-119](evals/hard.py#L60-L119)) so "Built" or "Product" don't false-positive at sentence starts. **Failure modes:** lowercase fabricated metrics ("doubled the team" — no number); paraphrased company names ("the bank" instead of "Goldman Sachs"); fabricated numbers that happen to appear elsewhere in the JD.
📁 *See: [evals/hard.py:60-200](evals/hard.py#L60-L200)*

**Q: What happens under a load spike on the webhook? Where's the bottleneck?**
A: The webhook is FastAPI/Uvicorn on Railway, single Docker container. The hard bottleneck is the inline pipeline: `OCR (Tesseract, ~1–3s) → JD extract LLM call → resume mutation LLM call → pdflatex compile (1–5s) → Drive upload → Calendar → 3x draft LLM calls`. There's no queue — the request waits. The LLM gateway is synchronous ([core/llm.py:212](core/llm.py#L212) is `client.chat.completions.create`). At ~30–60s per run end-to-end (latency threshold at [evals/ci_gate.py:40](evals/ci_gate.py#L40)), one container saturates fast. First scaling lever: make the executor enqueue to a worker process and ack the Telegram webhook within the 200ms Telegram expects. Second: parallelize the three independent draft calls.
📁 *See: [agents/inbox/executor.py](agents/inbox/executor.py), [evals/ci_gate.py:40](evals/ci_gate.py#L40)*

**Q: The planner is deterministic and produces a `ToolPlan`. What's the product win from that vs. just calling the steps inline?**
A: Three things. (1) **Testability** — you can assert on plan shape without running tools (`TOOL_ORDER` at [agents/inbox/planner.py:44-57](agents/inbox/planner.py#L44-L57) is the contract). (2) **Selective skipping** — `skip_upload`, `skip_calendar`, and `selected_collateral` flags become "drop steps from the plan" rather than scattered if-statements ([agents/inbox/agent.py:54-77](agents/inbox/agent.py#L54-L77)). (3) **Future planner-mode** — PRD §13.3 marks Phase 2 (Planner Mode) as Done with KAR-61; the architecture cleanly admits an LLM planner later because the executor only consumes a typed `ToolPlan`. Today the planner is rules; tomorrow it can be an LLM that emits the same JSON.
📁 *See: [agents/inbox/planner.py:44-90](agents/inbox/planner.py#L44-L90), [PRD.md:546-554](PRD.md#L546-L554)*

**Q: The eval gate runs on fixtures, not live runs. Why, and what does that miss?**
A: [evals/ci_gate.py:8-12](evals/ci_gate.py#L8-L12) is explicit: live DB history is "polluted by dev / exploratory runs," so blocking on it makes CI flaky. Fixtures in `evals/dataset.py` are curated and stable. **What it misses:** real-world JD distribution drift (a fixture from 2026-01 can't catch that companies started writing JDs differently in 2026-04), and silent regressions in production model behavior between fixture refreshes. The live DB stats are still printed for "situational awareness" but don't gate. The honest answer in an interview: this is the right tradeoff for an indie/solo product, but at scale you'd want a shadow eval that re-runs the last 100 production JDs nightly against a held-out judge.
📁 *See: [evals/ci_gate.py:8-22](evals/ci_gate.py#L8-L22)*

**Q: How is fabrication actually prevented end-to-end — what's the layered defense?**
A: Four layers, ordered by trust: (1) **Prompt-level** — `resume_mutate_v3.txt` instructs the model to only rewrite within editable bounds and only use facts from supplied bullets/profile. (2) **Edit scope** — physically constrains *where* edits can land via `%%BEGIN_EDITABLE` markers ([agents/inbox/resume.py:34-60](agents/inbox/resume.py#L34-L60)). (3) **Forbidden claims** — heuristic post-check across numeric and entity drift ([evals/hard.py:135-200](evals/hard.py#L135-L200)). (4) **Soft eval LLM judge** — `score_resume_relevance` flags incoherence even when nothing fabricated ([evals/soft.py:40-59](evals/soft.py#L40-L59)). Importantly: the Profile agent is *read-only* and never edits the resume — separation of concerns is itself a guardrail ([PRD.md:81-91](PRD.md#L81-L91)).
📁 *See: [agents/inbox/resume.py:34-60](agents/inbox/resume.py#L34-L60), [evals/hard.py:135-200](evals/hard.py#L135-L200), [evals/soft.py:40-59](evals/soft.py#L40-L59)*

---

## 4. Tradeoffs & Design Decisions

**Q: Why a deterministic regex router instead of an LLM router?**
A: [PRD.md:111-123](PRD.md#L111-L123) is explicit: "No routing LLM initially." The router is ~170 lines of regex + keyword scoring ([core/router.py](core/router.py)). The trade is calibration vs. cost/latency/predictability. An LLM router would handle "yo can you check on that Stripe role from last week" as `FOLLOWUP`; the rules-based router catches it via the `_FOLLOWUP_KEYWORDS` list ([core/router.py:73-80](core/router.py#L73-L80)) but fails on phrasings outside the dictionary — and falls back to `AMBIGUOUS_NON_JOB`. For a single-user product where the user adapts to the bot's vocabulary, this is the right tradeoff. For a public product, you'd want an LLM tie-breaker on `AMBIGUOUS_NON_JOB`.
📁 *See: [core/router.py](core/router.py), [PRD.md:111-123](PRD.md#L111-L123)*

**Q: Why LaTeX resumes instead of Markdown / HTML / Word?**
A: PDF fidelity at one-page constraint. LaTeX gives sub-millimeter typography control, version-control-friendly diffs, and `pdflatex` is a single binary in the Docker image ([README.md:21](README.md#L21) mentions Tesseract + minimal TexLive). The product cost is real: every mutation can break compilation, so the pipeline has a `check_compile()` gate ([evals/hard.py:31-37](evals/hard.py#L31-L37)) and a revert-to-original on failure. For an AI product builder interview: this is a *quality-bar* decision — recruiters reject resumes with formatting bugs, and a Markdown-to-PDF pipeline (Pandoc, etc.) loses the formatting safety net.
📁 *See: [agents/inbox/resume.py](agents/inbox/resume.py), [Dockerfile](Dockerfile)*

**Q: Why is the Profile agent read-only when "AI assistants" usually act?**
A: This is the architectural answer to "how do you prevent fabrication" — you remove the means. The Profile agent has no tool permissions ([PRD.md:81-91](PRD.md#L81-L91), [agents/profile/agent.py:1-25](agents/profile/agent.py#L1-L25)). It can answer "tell me about Karan" using `profile.json` + `bullet_bank.json`, but it cannot write a file, push a resume, or send a message. Combined with the forbidden-claims gate, a fabricated answer from Profile can't reach a hiring manager — it'd have to be copy-pasted by Karan, who'd notice. **Tradeoff:** every workflow that "needs Profile to take action" has to go through the Inbox agent, which feels like indirection. For a product where credibility is everything (job applications), the indirection is the point.
📁 *See: [PRD.md:81-91](PRD.md#L81-L91), [agents/profile/agent.py](agents/profile/agent.py)*

**Q: 3-run median for soft evals — why not 1 or 5?**
A: [evals/soft.py:21](evals/soft.py#L21) sets `DEFAULT_REPEAT = 3` and uses median, not mean, at [evals/soft.py:59](evals/soft.py#L59). Median over 3 dampens single-outlier judge noise without paying 5x the token cost. Mean would let one rogue 0.0 score drag the average ~33%. With cost capped at $0.15/run total ([evals/ci_gate.py:39](evals/ci_gate.py#L39)) and two soft evals running 3x each, the soft-eval budget is bounded. If accuracy mattered more than cost (e.g. promoting a model change), you'd bump to 5–7 with mean+stddev — but for CI gating, 3-run median is the cheapest variance reduction that works.
📁 *See: [evals/soft.py:21-59](evals/soft.py#L21-L59)*

**Q: What is this codebase optimizing for, and what does it sacrifice?**
A: **Optimizing for:** speed of solo iteration (one user — Karan — can change behavior end-to-end in a single PR), eval-driven safety (no fabricated bullets ever ships), and operational simplicity (one container on Railway, no queue, no separate workers). **Sacrificed:** multi-tenant readiness (everything is hard-coded to "Karan" — see `_PROFILE_KEYWORDS` at [core/router.py:35-47](core/router.py#L35-L47)), real-time UX (a 30–60s pipeline blocks the webhook), and observability beyond per-run telemetry. This is what an interviewer wants to hear: you understand it's a *product for one user* and you'd describe the v2 changes (queue, multi-profile, web UI) without claiming v1 already had them.
📁 *See: [core/router.py:35-47](core/router.py#L35-L47), [pyproject.toml](pyproject.toml)*

---

## 5. Curveballs & Gotchas

**Q: The README says the deploy target is Railway with managed Postgres, but the CI gate's docstring still mentions "actual SQLite run history." Which is right?**
A: Both — Postgres is the runtime (`psycopg2-binary` in `pyproject.toml:19`, `DATABASE_URL` injected by Railway, [README.md:22](README.md#L22)). The "SQLite" line in [evals/ci_gate.py:22](evals/ci_gate.py#L22) is stale documentation from before the Postgres migration ([PRD.md:148](PRD.md#L148): "PostgreSQL DB (migrated from SQLite)"). In an interview: name it as a doc-rot example, say you'd fix the comment in the same PR you noticed it. Demonstrates you read code, not just docs.
📁 *See: [evals/ci_gate.py:22](evals/ci_gate.py#L22), [PRD.md:148](PRD.md#L148), [pyproject.toml:19](pyproject.toml#L19)*

**Q: The forbidden-claims detector has a hand-curated `_COMMON_SKIP_WORDS` set with ~50 entries. What's the trap there?**
A: The skip set is a **whitelist of common-but-capitalized words** so "Built", "Drove", "Product" don't false-positive. The trap: it conflates "this word is a common verb" with "this word is safe to be in a fabricated bullet." If a model wrote "Built Stripe integration" and "Stripe" wasn't in the source, the multi-word entity rule catches it via "Built Stripe" — but if it wrote just "Built integration with Stripe", the lone "Stripe" gets flagged correctly only because it's not in skip and not in corpus. Add "Stripe" to the company list and now "Built Stripe-style payments" passes even if Karan never worked on it. The skip set is product policy embedded in code — worth name-dropping as "single point of trust I'd extract to config."
📁 *See: [evals/hard.py:60-119](evals/hard.py#L60-L119), [evals/hard.py:175-189](evals/hard.py#L175-L189)*

**Q: There's a `user_vetted` column on the `jobs` table that defaults to 0. What does setting it to 1 actually unlock?**
A: It's a *provenance* bit, not a permissions bit. Set to 1 only when the job entered via Telegram inbox (Karan submitted it manually) — see [README.md:11-14](README.md#L11-L14), [PRD.md:153-156](PRD.md#L153-L156). Downstream "scanner / dashboard / integrity logic" uses it to distinguish reviewed input from auto-discovered jobs. It does *not* skip evals or relax constraints. The trap in an interview: don't pitch it as a "trust override that bypasses the forbidden-claims gate" — it isn't. It's the answer to "how do we know this JD wasn't scraped from a sketchy source," nothing more.
📁 *See: [README.md:11-14](README.md#L11-L14), [PRD.md:153-156](PRD.md#L153-L156)*

**Q: Soft evals call an LLM 3x via the same `chat_text` gateway that the pipeline uses. What's the failure mode?**
A: Same OpenRouter account, same model, same minute — if rate-limited, the *whole* pipeline's soft eval scores collapse to 0.0 (the `except` branches at [evals/soft.py:36-37](evals/soft.py#L36-L37) silently return 0.0 on JSON decode / value errors, and a 429 from the gateway propagates through). That means a transient OpenRouter hiccup looks identical to "the model wrote a bad resume." The fallback model chain in `core/llm.py` mitigates this for production calls, but the soft eval median can still be dragged down by 1–2 transient failures. Worth proposing: judge calls should use a different model than mutation calls so a single model outage doesn't cascade.
📁 *See: [evals/soft.py:24-38](evals/soft.py#L24-L38), [core/llm.py:209-219](core/llm.py#L209-L219)*

---

## Quick-Reference Cheat Sheet

Memorize cold before walking in:

- **Stack:** Python 3.9+, FastAPI/Uvicorn, Telegram webhook, Postgres on Railway, OpenRouter (any OpenAI-compatible model), Tesseract OCR, pdflatex.
- **Architecture:** Deterministic router → planner builds typed `ToolPlan` → executor runs steps with retry. Three agents: Inbox (executor), Profile (read-only), Follow-Up (scheduler).
- **Eval gate (hard, CI-blocking):** compile ≥95%, forbidden_claims=0, edit_violations=0, avg cost ≤$0.15/run, latency ≤60s — fixture-based, not live DB.
- **Eval gate (soft, reporting):** LLM judges for resume_relevance + jd_accuracy, 3-run median to reduce variance.
- **Fabrication defense:** layered — prompt + `%%BEGIN_EDITABLE` markers + heuristic forbidden-claims detector + read-only Profile agent.
- **Cost handling:** OpenRouter doesn't return cost in completion; resolved post-hoc via `/generation?id=...` batched at pipeline end.
- **Deploy:** single Docker container on Railway. No queue, no workers — webhook handles inline. Bottleneck is the synchronous pipeline.
- **Quirk worth name-dropping:** `_COMMON_SKIP_WORDS` is product policy (which capitalized words don't trigger fabrication detection) embedded in [evals/hard.py:60-119](evals/hard.py#L60-L119) — should arguably be config.

---

## If asked about something not above

Default fallback: "I'd start by reading [agents/inbox/agent.py](agents/inbox/agent.py) and [agents/inbox/planner.py](agents/inbox/planner.py) to confirm — but my read of the repo is that the Inbox pipeline is a planner→executor with deterministic step ordering, and most non-obvious behavior lives in the eval gates rather than the prompts." Honesty about repo familiarity beats fabrication.
