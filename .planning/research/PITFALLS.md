# Pitfalls Research

**Domain:** AI-assisted job application automation (Telegram webhook pipeline)
**Researched:** 2026-03-05
**Confidence:** HIGH

## Critical Pitfalls

### Pitfall 1: Hallucinated Resume Claims in Mutated Outputs

**What goes wrong:**
The generated resume or outreach text introduces achievements, metrics, tools, or responsibilities not grounded in the candidate profile.

**Why it happens:**
Mutation prompts optimize for fit score and keyword overlap without strict grounding constraints and post-generation claim validation.

**How to avoid:**
Require profile-grounded extraction as an intermediate artifact, add explicit forbidden-claim eval gates in CI, and fail closed to base resume when confidence drops.

**Warning signs:**
Large fit-score increases with low source overlap, new proper nouns absent from base resumes, and repeated soft-eval failures on relevance/truthfulness.

**Phase to address:**
Phase 1 hardening (`KAR-60`, `KAR-75`)

---

### Pitfall 2: Silent OCR/URL Extraction Degradation

**What goes wrong:**
Job descriptions are partially extracted, causing malformed downstream artifacts while pipeline still reports success.

**Why it happens:**
Fallback paths exist, but extraction confidence, field completeness, and parser quality thresholds are not enforced as hard stop conditions.

**How to avoid:**
Define minimum extraction completeness contracts, persist raw input plus parsed JSON, and route low-confidence runs to explicit manual-review state.

**Warning signs:**
Frequent empty or generic responsibilities sections, inconsistent keyword sets across retries, and growing mismatch between user input and extracted JD.

**Phase to address:**
Phase 0/1 reliability + artifact formalization (`KAR-72`, `KAR-75`)

---

### Pitfall 3: Compile Success Masking ATS Quality Regressions

**What goes wrong:**
LaTeX compilation passes, but resume format becomes ATS-hostile (overfull layout, broken section hierarchy, unreadable text extraction).

**Why it happens:**
Build pipeline treats PDF generation as the completion criterion without machine-readable ATS checks and page/structure guardrails.

**How to avoid:**
Add post-compile ATS validation (one-page constraint, text extraction sanity, section order checks) and block artifacts that fail.

**Warning signs:**
Compile-pass rate remains high while application response quality drops, sudden page overflow, and malformed extracted text from generated PDFs.

**Phase to address:**
Phase 1 CI gate hardening (`KAR-60`)

---

### Pitfall 4: Non-Idempotent Webhook Processing

**What goes wrong:**
Duplicate Telegram deliveries create duplicate jobs, duplicate outreach drafts, and inconsistent Linear issue history.

**Why it happens:**
Webhook handlers process events without durable dedupe keys and without replay-safe persistence of raw inbound events.

**How to avoid:**
Persist raw webhook payloads with deterministic event IDs, enforce idempotency keys at job creation boundary, and make side effects retry-safe.

**Warning signs:**
Multiple records with same source message ID, duplicate outreach timestamps, and sporadic "already processed" logic in downstream logs.

**Phase to address:**
Phase 0 ingestion reliability (`KAR-72`) + Linear integration (`KAR-76`)

---

### Pitfall 5: Router Drift as New Agent Types Are Added

**What goes wrong:**
New message types (article/non-job/ambiguous prompts) are routed incorrectly into job pipeline, causing poor UX and wasted model spend.

**Why it happens:**
Routing rules are deterministic but brittle; adding branches (ArticleAgent, memory fallback) without contract tests causes regressions.

**How to avoid:**
Define explicit router decision table, add regression tests for each message class, and enforce confidence-based fallback behavior.

**Warning signs:**
Increase in "wrong agent" handling, user clarifications after bot responses, and cost spikes from unnecessary full pipeline runs.

**Phase to address:**
Phase 1 routing expansion (`KAR-73`, `KAR-74`)

---

### Pitfall 6: Eval Telemetry Exists but Does Not Gate Releases

**What goes wrong:**
Metrics are collected but low-quality changes still ship because thresholds are advisory rather than blocking.

**Why it happens:**
Teams optimize for delivery speed; eval jobs run inconsistently, and failure criteria are not codified in CI policy.

**How to avoid:**
Convert quality thresholds into required checks, maintain minimum eval case count, and track trend deltas rather than single-run pass/fail.

**Warning signs:**
Frequent manual overrides, flaky eval suite tolerated in mainline, and regressions discovered only after user-facing runs.

**Phase to address:**
Phase 1 CI/eval governance (`KAR-60`)

---

### Pitfall 7: Schema Drift Across Pipeline Artifacts

**What goes wrong:**
Different stages produce incompatible JSON shapes, breaking analytics, replay, and integration workflows.

**Why it happens:**
Artifacts evolve organically across agents without versioned schema contracts and migration paths.

**How to avoid:**
Define versioned canonical schemas for job/resume/eval artifacts, validate on write, and include migration tooling for historical records.

**Warning signs:**
Conditional parsing scattered across code, frequent null checks for required fields, and backward-compat breakages in downstream tools.

**Phase to address:**
Phase 1 artifact formalization (`KAR-75`), Phase 2 planner/executor contracts (`KAR-61`)

---

### Pitfall 8: Single-User Assumptions Leaking into SaaS Transition

**What goes wrong:**
Identity, data ownership, and rate-limit boundaries are hard-coded for one operator, making multi-user rollout risky and expensive.

**Why it happens:**
Brownfield code optimizes for one workflow; tenancy and isolation are deferred until late architecture phases.

**How to avoid:**
Identify tenant boundaries early, separate user profile data from global config, and add per-tenant observability/cost attribution.

**Warning signs:**
Global mutable state, shared artifact directories without owner IDs, and integration keys reused across environments/users.

**Phase to address:**
Phase 3 SaaS readiness (`KAR-62`) with preparatory checks in Phase 2

---

## Technical Debt Patterns

Shortcuts that seem reasonable but create long-term problems.

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Hard-code routing conditions directly in handler branches | Fast feature shipping | Router brittleness and regression risk | Only for short-lived experiments behind explicit kill switch |
| Skip schema versioning for internal JSON artifacts | Less upfront design work | Expensive migrations and replay failures | Never beyond prototype spike |
| Treat compile success as quality success | Simple KPI and low implementation effort | Hidden ATS and content-quality regressions | Never for production gates |
| Keep all run artifacts in one shared namespace | Minimal storage design | Debug ambiguity, poor traceability, tenant migration blockers | Only in single-user local development |

## Integration Gotchas

Common mistakes when connecting to external services.

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| Telegram webhook delivery | Assume exactly-once delivery semantics | Design for at-least-once, dedupe by message/update ID, persist raw payloads |
| URL content fetchers / screenshot fallback | Trust fetched text without provenance or completeness checks | Store source type, extraction confidence, and structured fallback reason codes |
| Linear issue sync | Create issue per run without idempotent upsert key | Use deterministic external key per job and update existing issue lifecycle |

## Performance Traps

Patterns that work at small scale but fail as usage grows.

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Re-running full extraction + mutation on every retry | Rising latency and token cost per duplicate event | Cache immutable extraction artifacts keyed by source hash | Noticeable at moderate duplicate rates and batch replays |
| Serial pipeline orchestration across independent tasks | Slow end-to-end completion and timeout pressure | Split planner/executor responsibilities and parallelize safe stages | Breaks under bursty webhook traffic |
| Unbounded artifact retention in hot storage | Disk growth, slower lookups, operational cleanup burden | Apply retention policy + cold archive strategy by run state | Becomes painful as historical runs accumulate |

## Security Mistakes

Domain-specific security issues beyond general web security.

| Mistake | Risk | Prevention |
|---------|------|------------|
| Persisting PII-rich artifacts without classification or redaction | Exposure of personal/contact/employment data | Tag artifacts by sensitivity, redact where possible, enforce retention and access controls |
| Logging raw prompts/responses containing personal profile details | Leakage through logs/monitoring tooling | Structured logging with field-level filtering and explicit safe-log schemas |
| Reusing integration secrets across local/staging/prod | Cross-environment compromise blast radius | Per-environment credentials, scoped tokens, and regular rotation |

## UX Pitfalls

Common user experience mistakes in this domain.

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| Returning "success" without confidence or caveats | Users trust weak outputs and send poor applications | Include confidence summary + manual review guidance when extraction quality is low |
| Ambiguous fallback responses for non-job inputs | Users cannot predict assistant behavior | Provide explicit route explanation and next-step options |
| Overloading user with all artifacts at once | High cognitive load, missed critical checks | Present prioritized artifact checklist (resume first, then outreach) |

## "Looks Done But Isn't" Checklist

Things that appear complete but are missing critical pieces.

- [ ] **Webhook reliability:** Often missing replay-safe dedupe — verify repeated delivery produces one logical job outcome.
- [ ] **Resume mutation safety:** Often missing claim-grounding validation — verify no new facts beyond source profile.
- [ ] **Eval readiness:** Often missing enforced CI thresholds — verify failing quality gates block merge/release.
- [ ] **Artifact contracts:** Often missing schema version + migration path — verify old runs remain readable after schema changes.
- [ ] **Linear sync:** Often missing idempotent upsert semantics — verify retries update existing issue instead of duplicating.

## Recovery Strategies

When pitfalls occur despite prevention, how to recover.

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Hallucinated claims shipped in outputs | HIGH | Quarantine affected artifacts, notify operator, roll back to base resume for impacted runs, add regression case to eval suite |
| Duplicate webhook processing | MEDIUM | Deduplicate historical records by source event ID, merge downstream issue threads, patch idempotency boundary and replay test |
| Schema drift breaks downstream tools | MEDIUM | Freeze writes, ship schema adapter/migration, revalidate historical artifacts, then re-enable pipeline with version checks |
| ATS regressions despite compile success | MEDIUM | Backfill ATS validation on recent outputs, mark non-compliant artifacts, tighten compile + ATS gate policy in CI |

## Pitfall-to-Phase Mapping

How roadmap phases should address these pitfalls.

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Hallucinated resume claims | Phase 1 (`KAR-60`, `KAR-75`) | CI blocks forbidden-claim eval failures across 10+ benchmark cases |
| OCR/URL extraction degradation | Phase 0/1 (`KAR-72`, `KAR-75`) | Low-confidence runs route to manual-review state with explicit reason codes |
| Compile success masking ATS regressions | Phase 1 (`KAR-60`) | Post-compile ATS checks enforced and trend dashboard stable |
| Non-idempotent webhook processing | Phase 0 + Linear integration (`KAR-72`, `KAR-76`) | Replay tests confirm one logical outcome per source event |
| Router drift with new agents | Phase 1 (`KAR-73`, `KAR-74`) | Router decision-table tests pass for all supported input classes |
| Eval telemetry not gating releases | Phase 1 (`KAR-60`) | Required CI checks fail merge when thresholds are not met |
| Artifact schema drift | Phase 1/2 (`KAR-75`, `KAR-61`) | Versioned schema validation passes and legacy data remains parseable |
| Single-user assumptions block SaaS | Phase 3 with Phase 2 prep (`KAR-62`, `KAR-61`) | Tenant-boundary tests and per-tenant data partition checks pass |

## Sources

- Project context and requirements in `.planning/PROJECT.md`
- Existing roadmap items and active Linear references in `PROJECT.md` (`KAR-60`, `KAR-61`, `KAR-62`, `KAR-72`, `KAR-73`, `KAR-74`, `KAR-75`, `KAR-76`)
- Domain operational patterns from webhook-based automation systems and LLM pipeline reliability practices

---
*Pitfalls research for: Job Search Agent (AI-assisted job application automation)*
*Researched: 2026-03-05*
