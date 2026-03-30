# Feature Research

**Domain:** Brownfield Telegram-based job-search assistant
**Researched:** 2026-03-05
**Confidence:** HIGH

## Feature Landscape

### Table Stakes (Users Expect These)

Features users assume exist. Missing these = product feels incomplete.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Multi-input ingestion (URL, image/screenshot, text) | Job seekers share openings in mixed formats and expect assistant to accept all common input forms | MEDIUM | Existing webhook + OCR pipeline is in place; hardening should focus on retry behavior, malformed payload handling, and observability. Dependency: Telegram webhook + fetch/OCR adapters. |
| Reliable JD extraction with graceful fallback | Users expect assistant to understand job details correctly even when page scraping fails | HIGH | Requires extraction path selection, OCR confidence thresholds, and fallback messaging. Dependency: fetcher, OCR, normalization schema, and failure-state UX. |
| Tailored resume generation with compile-safe output | Core expected outcome is a submission-ready resume customized to the role | HIGH | Existing mutation + compile + rollback exists; further scope should enforce edit-scope controls and forbidden-claim checks in CI gates. Dependency: base resume corpus, constrained editor, LaTeX compile pipeline. |
| Outreach draft generation (email/DM/referral) | Users expect outreach text alongside resume for end-to-end application prep | MEDIUM | Already implemented; needs quality consistency and per-channel templates with traceability to JD/profile facts. Dependency: structured job/profile artifacts and prompt contracts. |
| Run artifact persistence and traceability | Users expect ability to revisit generated outputs and debug failures | MEDIUM | Existing artifact persistence present; needs formalized JSON artifacts and replayable raw webhook events. Dependency: storage layer, schema versioning, event log retention. |
| Follow-up workflow support (drafts + reminders) | Application process is multi-step; users expect assistant to help after first message | MEDIUM | Existing follow-up drafts and scheduler runner exist; prioritize state model clarity and idempotent reminder jobs. Dependency: application status model, scheduling runner, Telegram notification channel. |

### Differentiators (Competitive Advantage)

Features that set the product apart. Not required, but valuable.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Truthfulness guardrails with eval-based enforcement | Builds trust by preventing invented claims in resume/outreach outputs | HIGH | Strong differentiator for high-stakes applications. Dependency: profile-grounding checks, forbidden-claim detectors, CI threshold gates (`KAR-60`). |
| Deterministic routing for job-processing flows | Predictable behavior improves debuggability and operational reliability | MEDIUM | Helps brownfield hardening before planner/executor expansion. Dependency: explicit router rules, telemetry, fallback branch for ambiguous inputs (`KAR-74`, `KAR-73`). |
| Resume mutation constrained to editable LaTeX regions | Preserves formatting quality and ATS safety while still personalizing content | HIGH | Reduces document breakage compared to free-form generation. Dependency: region annotations, mutation policy checks, compile rollback safety. |
| Fit scoring + eval telemetry (quality, token/cost) | Enables measurable improvement loop rather than subjective iteration | MEDIUM | Supports product decisions and regression detection. Dependency: eval dataset, metric store, dashboards/reporting query layer. |
| Automatic Linear issue sync per application run | Converts generated output into actionable pipeline state for job tracking | MEDIUM | Bridges assistant output to execution workflow; currently active gap (`KAR-76`). Dependency: canonical run schema, Linear API integration, idempotent upsert logic. |

### Anti-Features (Commonly Requested, Often Problematic)

Features that seem good but create problems.

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Fully autonomous outreach auto-send | Promises zero-click automation | High reputational risk from factual errors, tone mismatch, or timing mistakes; weak human control for high-stakes communication | Keep draft-first workflow with one-tap approval and optional policy checks before send |
| LLM-only routing replacing deterministic rules immediately | Seems flexible and "smarter" for all message types | Increases nondeterminism, complicates debugging, and raises regression risk during hardening | Keep deterministic router for core paths; add planner/executor branch incrementally with strict eval gates |
| Aggressive multi-user SaaS expansion now | Expands potential market quickly | Introduces tenant isolation, billing, compliance, and support complexity before v1 stability | Defer to Phase 3; retain single-user architecture with clean seams for future tenancy |
| Real-time "optimize everything" loop on every artifact | Sounds like maximum quality | Adds latency/cost and creates unstable outputs from over-iteration | Use bounded optimization passes with confidence thresholds and explicit stop criteria |
| Unbounded memory for all conversations | Appears to improve personalization | Privacy/cost burden and context drift from stale signals | Use scoped, explicit memory objects tied to application lifecycle and retention policies |

## Feature Dependencies

```text
[Multi-input ingestion]
    └──requires──> [Telegram webhook reliability + event persistence]
                        └──requires──> [Replay/debug tooling]

[JD extraction reliability]
    └──requires──> [Fetcher + OCR + normalization schema]
                        └──requires──> [Structured artifact model]

[Tailored resume generation]
    └──requires──> [Constrained mutation engine]
                        └──requires──> [Compile + rollback safeguards]

[Truthfulness guardrails]
    └──requires──> [Profile grounding + forbidden-claim evals]
                        └──requires──> [CI success-criteria gates]

[Linear issue auto-sync] ──requires──> [Canonical run/job schema]
[Follow-up automation] ──requires──> [Application state machine + scheduler idempotency]

[LLM-only routing] ──conflicts──> [Deterministic hardening goals]
[Auto-send outreach] ──conflicts──> [Draft-first safety model]
```

### Dependency Notes

- **Structured artifact model is a core prerequisite:** It unlocks reliable downstream integrations (Linear sync, analytics, replay, and eval reproducibility) and should be scoped before new feature branches.
- **Eval gates depend on representative datasets:** CI thresholds are only meaningful if the eval corpus includes realistic failure modes (bad OCR, compile regressions, hallucination attempts).
- **Replayable webhook events reduce debugging complexity:** Raw event persistence is high leverage for brownfield hardening because it improves triage, reproducibility, and regression testing speed.
- **Scheduler idempotency is required for follow-up trust:** Without dedupe/idempotency, reminder automation can spam users and undermine product confidence.
- **Planner/executor separation should follow deterministic stabilization:** Introducing adaptive planning before core path stability increases moving parts and obscures regression attribution.

## MVP Definition

### Launch With (v1)

Minimum viable product for this brownfield hardening cycle.

- [x] Multi-input Telegram ingestion with deterministic routing
- [x] JD extraction with OCR fallback and user-visible failure messaging
- [x] Tailored resume mutation + compile rollback safeguards
- [x] Outreach draft generation (email/LinkedIn/referral)
- [x] Artifact persistence and basic fit/eval telemetry
- [ ] CI-enforced quality gates for compile success and truthfulness (`KAR-60`)
- [ ] Structured JSON artifacts for job/resume/eval objects (`KAR-75`)
- [ ] Raw webhook event persistence for replay/debug (`KAR-72`)

### Add After Validation (v1.x)

- [ ] Linear issue create/update sync per run (`KAR-76`) — add after schema stabilization
- [ ] Memory-agent fallback for ambiguous messages (`KAR-74`) — add after deterministic fallback baseline
- [ ] ArticleAgent routing branch (`KAR-73`) — add after core job-processing reliability targets are met

### Future Consideration (v2+)

- [ ] Planner/executor architecture split (`KAR-61`) — after v1 reliability and data contracts are stable
- [ ] Multi-user SaaS readiness and tenant model (`KAR-62`) — after single-user PMF and operational SLO compliance

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| CI-enforced quality/truthfulness gates | HIGH | MEDIUM | P1 |
| Structured JSON artifact schema | HIGH | MEDIUM | P1 |
| Raw webhook event replay persistence | HIGH | LOW | P1 |
| Linear issue auto-sync | MEDIUM | MEDIUM | P2 |
| Memory-agent fallback for ambiguity | MEDIUM | MEDIUM | P2 |
| ArticleAgent route branch | LOW | LOW | P3 |
| Planner/executor split | HIGH | HIGH | P3 |
| Multi-user SaaS readiness | MEDIUM | HIGH | P3 |

**Priority key:**
- P1: Must have for brownfield v1 hardening
- P2: Should have after core reliability gates are passing
- P3: Strategic future work after validation

## Competitor Feature Analysis

| Feature | Generic AI resume tools | Automation platforms (Zapier-style) | Our Approach |
|---------|-------------------------|-------------------------------------|--------------|
| Resume tailoring | Strong text generation, weaker source-grounding controls | Usually orchestration-only; external model quality varies | Grounded mutation with constrained LaTeX edit regions + compile safety |
| Job input handling | Often manual paste/upload UX | Strong integration surface, weak domain-specific parsing | Telegram-native URL/image/text ingestion with OCR fallback |
| Safety/truthfulness | Often policy-light for domain facts | Depends on custom workflow quality | Eval-driven forbidden-claim and grounding gates as release criteria |
| End-to-end application workflow | Commonly stops at resume text | Can chain tasks but requires heavy setup | Resume + outreach + follow-up + tracking integration in one pipeline |

## Sources

- `.planning/PROJECT.md` (project scope, active requirements, constraints, Linear-linked gaps)
- `~/.codex/get-shit-done/templates/research-project/FEATURES.md` (research structure and definitions)
- Current brownfield state references embedded in PROJECT requirements (`KAR-60`, `KAR-72`, `KAR-73`, `KAR-74`, `KAR-75`, `KAR-76`, `KAR-61`, `KAR-62`)

---
*Feature research for: brownfield Telegram-based job-search assistant*
*Researched: 2026-03-05*
