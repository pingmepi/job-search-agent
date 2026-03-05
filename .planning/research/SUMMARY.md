# Project Research Summary

**Project:** job-search-agent
**Domain:** Brownfield Telegram-first AI job application automation
**Researched:** 2026-03-05
**Confidence:** HIGH

## Executive Summary

This project is a brownfield, single-user, Telegram-driven automation system that ingests job postings (URL/image/text), extracts job requirements, tailors resume artifacts, drafts outreach, and supports follow-up workflows. The research indicates the existing foundation is suitable for a v1 hardening cycle: keep the current Python/FastAPI/Telegram/OpenAI/SQLite stack, formalize data contracts, and tighten quality controls before adding autonomy or multi-tenant complexity.

The recommended approach is reliability-first sequencing: enforce schema and eval gates, persist replayable webhook events, and maintain deterministic routing while introducing scoped new routes. This preserves debuggability and protects user trust in high-stakes outputs.

The biggest risks are hallucinated resume claims, silent extraction degradation, and non-idempotent webhook behavior. Mitigation should be release-blocking CI gates (truthfulness + compile/ATS checks), canonical artifact schemas with versioning, and durable idempotency/replay boundaries.

## Key Findings

### Recommended Stack

Keep the current stack for the hardening window and avoid major platform shifts. Python + FastAPI + python-telegram-bot + OpenAI SDK + Pydantic + SQLite are aligned with current architecture and roadmap needs. Add test and reliability tooling (`pytest-cov`, `respx`, schema validation, standardized retries, structured logging) to improve confidence and operability without high migration cost.

**Core technologies:**
- Python + FastAPI + Uvicorn: webhook runtime and service lifecycle — already integrated and testable.
- python-telegram-bot: Telegram ingress/egress handling — mature async model and existing adapter integration.
- OpenAI SDK + Pydantic: LLM workflows with typed contracts — supports deterministic validation and fallback control.
- SQLite: durable local state for current phase — lowest migration risk until SaaS readiness.

### Expected Features

v1 should focus on table-stakes reliability of ingestion, extraction, compile-safe tailoring, outreach drafts, and artifact traceability. Competitive features should be added only where they strengthen trust and operational control.

**Must have (table stakes):**
- Multi-input ingestion (URL/image/text) with robust fallback handling.
- Reliable JD extraction with explicit low-confidence/manual-review outcomes.
- Tailored resume generation with compile rollback and safety checks.
- Outreach draft generation tied to grounded profile/JD facts.
- Run artifact persistence and follow-up workflow support.

**Should have (competitive):**
- Truthfulness guardrails enforced by eval-based release gates.
- Deterministic routing with measurable fallback paths.
- Constrained resume mutation and fit/eval telemetry.
- Linear issue sync using canonical run artifacts.

**Defer (v2+):**
- Planner/executor architecture split beyond incremental wrapping.
- Multi-user SaaS tenancy/isolation rollout.

### Architecture Approach

Use a strict boundary model: transport (FastAPI/webhook) remains thin, orchestration remains deterministic, stage execution remains modular, integrations remain optional side effects, and durable state contracts become explicit/versioned. Prioritize formal artifact schemas and replayable events first, then extend routing and integrations, then evolve control-plane architecture.

**Major components:**
1. Webhook/API and adapter layer — validate ingress, dedupe envelope, dispatch.
2. Router + pipeline agents — deterministic intent routing and staged workflow orchestration.
3. Core services + integrations + evals — shared invariants, external adapters, and release quality gates.

### Critical Pitfalls

1. **Hallucinated resume claims** — enforce profile grounding and forbidden-claim CI gates; fail closed to safe fallback.
2. **Silent OCR/URL extraction degradation** — require completeness thresholds and confidence-aware manual review routing.
3. **Compile success masking ATS regressions** — add post-compile ATS validation as a blocking gate.
4. **Non-idempotent webhook processing** — persist raw events, use deterministic dedupe keys, and ensure retry-safe side effects.
5. **Schema drift across artifacts** — define versioned canonical schemas and validate on write/read.

## Implications for Roadmap

Based on research, suggested phase structure:

### Phase 1: Reliability and Contract Foundation
**Rationale:** All downstream work depends on trustworthy outputs and stable contracts.
**Delivers:** Canonical `JobArtifact`/`ApplicationPack`/`EvalReport`/`RunEvent` schemas; replayable webhook persistence; CI-enforced truthfulness + compile/ATS gates.
**Addresses:** Core v1 table stakes and P1 feature priorities.
**Avoids:** Hallucination, extraction drift, schema drift, and telemetry-without-enforcement.

### Phase 2: Routing and Integration Expansion
**Rationale:** Expand capability only after observability and contracts are stable.
**Delivers:** Article/memory fallback route hardening, router decision-table regression suite, idempotent Linear issue upsert.
**Uses:** Deterministic router, typed artifacts, isolated integration adapters.
**Implements:** Controlled orchestration growth with measurable fallback behavior.

### Phase 3: Control-Plane Evolution and SaaS Readiness
**Rationale:** Architectural scale changes should follow proven single-user reliability.
**Delivers:** Incremental planner/executor separation, tenant boundary seams, storage/idempotency abstractions for multi-user path.

### Phase Ordering Rationale

- Contracts and replay must precede new agent branches to preserve debuggability.
- Deterministic hardening should precede autonomy increases to limit regression surface.
- Integration sync should consume canonical artifacts, not unstable intermediates.
- SaaS concerns should follow explicit tenant/data boundary preparation.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 2:** Linear API idempotent upsert semantics and failure recovery strategy.
- **Phase 3:** Tenant isolation model, credential partitioning, and migration from single-user assumptions.

Phases with standard patterns (skip research-phase):
- **Phase 1:** Schema validation, webhook idempotency, CI gating, and structured logging patterns are well-established.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Directly aligned with current codebase and dependency profile. |
| Features | HIGH | Strong fit with domain expectations and existing roadmap backlog. |
| Architecture | HIGH | Clear boundary model with direct brownfield applicability. |
| Pitfalls | HIGH | Risks are concrete and mapped to active backlog items. |

**Overall confidence:** HIGH

### Gaps to Address

- Eval corpus breadth: expand benchmark cases for OCR failures, hallucination attempts, and ATS regressions before strict thresholds are finalized.
- Linear integration contract details: confirm external-key strategy, update semantics, and retry behavior during implementation planning.
- SaaS migration assumptions: validate tenant model and data ownership boundaries before Phase 3 execution.

## Sources

- [.planning/research/STACK.md](/Users/karan/Desktop/job-search-agent/.planning/research/STACK.md)
- [.planning/research/FEATURES.md](/Users/karan/Desktop/job-search-agent/.planning/research/FEATURES.md)
- [.planning/research/ARCHITECTURE.md](/Users/karan/Desktop/job-search-agent/.planning/research/ARCHITECTURE.md)
- [.planning/research/PITFALLS.md](/Users/karan/Desktop/job-search-agent/.planning/research/PITFALLS.md)
- [Template SUMMARY.md](/Users/karan/.codex/get-shit-done/templates/research-project/SUMMARY.md)

---
*Research completed: 2026-03-05*
*Ready for roadmap: yes*
