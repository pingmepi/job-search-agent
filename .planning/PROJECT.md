# Job Search Agent

## What This Is

Job Search Agent is a webhook-first Telegram assistant that turns job inputs (URL, screenshot/image, or text) into a tailored application package for Karan. It extracts and structures the job description, selects and mutates the best-fit base resume from the local repository, compiles artifacts, and generates outreach collateral. The system also tracks eval quality and follow-up workflow state so application quality can be measured and improved over time.

## Core Value

Given a job posting from Telegram, produce a truthful, ATS-safe, submission-ready application package with minimal manual effort.

## Requirements

### Validated

- ✓ Ingest Telegram job inputs via webhook service with text/photo handling and deterministic routing for job-processing flow — existing
- ✓ URL ingestion includes fetch path and screenshot fallback messaging when extraction fails — existing
- ✓ OCR pipeline with confidence checks and low-confidence fallback handling is implemented — existing
- ✓ Resume mutation is constrained to editable LaTeX regions only — existing
- ✓ Compile flow persists artifacts and supports rollback to base resume when mutated compile fails — existing
- ✓ Resume-fit signal (keyword overlap / fit score) is persisted in job records — existing
- ✓ Outreach collateral generation is implemented (email, LinkedIn DM, referral draft) — existing
- ✓ Follow-up draft generation with escalation tiers and scheduled follow-up detection runner are implemented — existing
- ✓ Eval logging includes hard metrics and token/cost accounting; soft evals for resume relevance and JD extraction are integrated — existing

### Active

- [ ] Enforce CI success-criteria gates reliably (10+ eval cases and threshold compliance for compile success, forbidden claims, and edit-scope signals) (`KAR-60`)
- [ ] Persist raw Telegram webhook events for replay/debugging (`KAR-72`)
- [ ] Add structured fallback memory-agent behavior for ambiguous/non-job messages (`KAR-74`)
- [ ] Add ArticleAgent routing/handler branch (`KAR-73`)
- [ ] Define and persist formal JSON artifacts for job/resume/eval outputs (`KAR-75`)
- [ ] Auto-create/update Linear application issue from each pipeline result (`KAR-76`)
- [ ] Introduce planner/executor separation (Phase 2) (`KAR-61`)
- [ ] Scope/prepare SaaS readiness and multi-user architecture (Phase 3) (`KAR-62`)

### Out of Scope

- Multi-user tenant support in v1 brownfield hardening — deferred to SaaS readiness phase
- Full autonomous auto-send of outreach without human review — current operating mode is draft-first review
- Replacing deterministic router with fully LLM-based routing — deferred until planner mode matures

## Context

The project is a brownfield Python codebase with webhook-first Telegram ingestion and an eval-driven workflow. Current documentation and Linear indicate significant Phase 0 and Phase 1 progress, including webhook migration, artifact persistence, mutation-guard safety, follow-up automation foundations, and soft eval integration. As of March 4, 2026, Linear milestones indicate active work remains in Phase 0/1 hardening with Phase 2 and Phase 3 not started. The repo contains multiple base resumes and existing pipeline logic for selection/mutation, plus run artifacts and tests.

## Constraints

- **Truthfulness/Grounding**: Resume and outreach outputs must avoid invented claims — enforced by evals and profile grounding checks
- **Document Quality**: Resume outputs should remain one page and ATS-compliant for submission quality
- **Determinism**: Routing and critical pipeline steps should remain predictable and testable
- **Operational Reliability**: Webhook ingestion must not block primary processing and should degrade gracefully on extraction/OCR failures
- **Cost/Latency Visibility**: LLM token and cost telemetry must stay complete for each run

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Webhook-first Telegram runtime (no polling) | Better production-operational model and cleaner integration boundary | ✓ Good |
| Brownfield-first initialization from existing implementation + Linear state | Avoid re-planning completed work and capture true current baseline | ✓ Good |
| Keep draft-first collateral generation as default | Preserves quality control for high-stakes job applications | — Pending |
| Maintain deterministic routing in current milestone | Reduces ambiguity and simplifies validation while hardening pipeline | ✓ Good |

---
*Last updated: 2026-03-04 after project initialization*
