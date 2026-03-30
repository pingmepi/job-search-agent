# Architecture Research

**Domain:** Brownfield multi-agent job application automation (Telegram-first)
**Researched:** 2026-03-05
**Confidence:** HIGH

## Standard Architecture

### System Overview

```
┌──────────────────────────────────────────────────────────────────────┐
│                        Interface and Control                        │
├──────────────────────────────────────────────────────────────────────┤
│  Telegram Webhook (FastAPI)   CLI Entrypoints   Scheduler Runner    │
│           │                        │                │                │
│           └──────────────┬─────────┴───────┬────────┘                │
├──────────────────────────┴──────────────────┴───────────────────────┤
│                       Routing and Orchestration                      │
├──────────────────────────────────────────────────────────────────────┤
│ Deterministic Router  Inbox Adapter  Pipeline Orchestrator          │
│ Profile Agent         Follow-up Agent  Follow-up Runner             │
├──────────────────────────────────────────────────────────────────────┤
│                        Shared Platform Services                      │
├──────────────────────────────────────────────────────────────────────┤
│ Config   Prompt Registry   LLM Gateway   Eval Gate   DB Access       │
│ Resume Compiler/OCR/JD Extraction Utilities                          │
├──────────────────────────────────────────────────────────────────────┤
│                    Persistence and External Integrations             │
├──────────────────────────────────────────────────────────────────────┤
│ SQLite (jobs, runs)   Runs Artifacts   Drive   Calendar   OpenRouter │
└──────────────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | Responsibility | Current Boundary Rule |
|-----------|----------------|-----------------------|
| Webhook/API (`app.py`) | Receive and validate Telegram updates, lifecycle management | No domain logic beyond transport validation and dispatch |
| Router (`core/router.py`) | Deterministic intent classification | Pure decision function; no side effects |
| Inbox Adapter (`agents/inbox/adapter.py`) | Translate Telegram events into domain calls | Owns message-level flow control, not business transformation |
| Inbox Pipeline (`agents/inbox/agent.py`) | End-to-end job application generation workflow | Orchestrates stages; delegates infra to `core/` and integrations |
| Profile Agent (`agents/profile/agent.py`) | Grounded profile Q&A | Reads profile sources; avoids changing pipeline state |
| Follow-up Agent/Runner (`agents/followup/*`) | Due detection and follow-up draft generation | Separate lifecycle from intake path |
| Shared Core (`core/*`) | Config, DB, LLM, prompts, cross-cutting utilities | Upstream dependency for all agents; no Telegram coupling |
| Integrations (`integrations/*`) | Drive/Calendar APIs and auth/session handling | Adapter-only; no routing/orchestration logic |
| Evaluations (`evals/*`) | Hard/soft quality checks and CI gate | Must be callable from pipeline and CI independently |

## Boundary Model for Brownfield Evolution

### Boundary 1: Transport vs Domain
- Keep `app.py` and Telegram handler code as a thin transport shell.
- Domain operations must be initiated through explicit pipeline/agent entrypoints.
- Implication: future channels (Slack/web UI/API) can reuse same domain interface.

### Boundary 2: Orchestration vs Stage Execution
- Inbox pipeline should remain orchestration-centric, while stage work lives in dedicated modules (`ocr`, `jd`, `resume`, `url_ingest`, `evals`).
- Implication: planner/executor split (Phase 2) can wrap existing stages without rewriting all logic.

### Boundary 3: Core Services vs External Integrations
- `core/` owns invariants (schemas, config, prompt versioning, LLM normalization).
- `integrations/` own external protocol details (Drive/Calendar APIs, OAuth token handling).
- Implication: SaaS/multi-tenant phase can swap integration credentials and storage strategy with minimal domain rewrites.

### Boundary 4: Runtime State vs Durable State
- In-memory webhook dedupe is operational state; SQLite and artifact paths are durable state.
- Implication: horizontal scale requires persistent/shared idempotency store before multi-instance deployment.

## Data Flow

### Primary Intake Flow (Telegram Job Submission)

```
Telegram Update
  -> FastAPI Webhook (secret validation)
  -> Inbox Adapter (update dedupe + retry envelope)
  -> Deterministic Router
  -> Inbox Pipeline Orchestrator
  -> Stage Chain: URL/OCR -> JD Extraction -> Resume Selection/Mutation -> Compile
  -> Optional Integrations (Drive/Calendar)
  -> Eval Gates + Telemetry
  -> Persist jobs/runs + artifacts
  -> Telegram Reply with package summary and links
```

### Follow-up Flow

```
Scheduler/Command Trigger
  -> Follow-up Runner
  -> Follow-up Agent (due detection + tier logic)
  -> LLM Draft Generation
  -> Persist follow-up metadata + run telemetry
  -> Return drafts for human review/send
```

### Profile Q&A Flow

```
User Question
  -> Router -> Profile Agent
  -> Grounded retrieval from profile/bullet bank
  -> LLM response constrained to known profile facts
  -> Telegram response
```

### Data Contracts to Formalize Next (KAR-75 aligned)
1. `JobArtifact`: canonical JSON for extracted JD + fit + selected resume.
2. `ApplicationPack`: canonical JSON for generated outputs, links, compile status, and fallbacks.
3. `EvalReport`: canonical JSON for hard/soft outcomes, thresholds, and token/cost metrics.
4. `RunEvent`: canonical JSON for step-level timing and error surfaces.

## Integration Points

### External Services

| Service | Pattern | Contract/Constraint |
|---------|---------|---------------------|
| Telegram Bot API | Webhook ingress + outbound message send | Header-secret validation and retry-safe idempotency required |
| OpenRouter | Synchronous request/response LLM calls + deferred cost lookup | Must keep model fallback chain and cost telemetry complete |
| Google Drive | Optional side-effect adapter | Failure must not fail core package generation |
| Google Calendar | Optional side-effect adapter | Event creation should be idempotent per job/run |
| Linear (planned KAR-76) | Async or post-run issue upsert | Should consume canonical artifacts, not raw intermediate state |

### Internal Boundaries and Communication

| Boundary | Communication | Build Implication |
|----------|---------------|-------------------|
| `app.py` <-> `agents/inbox/adapter.py` | Direct call with Telegram update objects | Keep stable adapter interface for test harness reuse |
| Adapter <-> Router | Pure function call | Enables deterministic regression tests |
| Adapter/Router <-> Agents | Typed payloads/dataclasses | Required for planner/executor split and replay tooling |
| Agents <-> `core/db.py` | CRUD helper functions | Introduce repository contracts before DB swap/scale work |
| Agents <-> `evals/*` | Function invocation with run context | Keep evals side-effect free except logging |
| Agents <-> `integrations/*` | Explicit optional calls | Preserve failure isolation around non-critical integrations |

## Suggested Build Order Implications

1. Stabilize data contracts before deeper orchestration changes.
- Implement formal artifact schemas (`KAR-75`) first.
- Reason: planner/executor separation and Linear sync both depend on stable payloads.

2. Add durable replay and observability before increasing autonomy.
- Persist raw Telegram events (`KAR-72`) and ensure run-step traceability.
- Reason: debugging and regression control become hard once routing/agents expand.

3. Introduce planner/executor split as a control-plane change, not a full rewrite.
- Wrap existing inbox stage modules under a planning interface (`KAR-61`).
- Reason: reuses proven brownfield logic and reduces migration risk.

4. Add new agent routes only after contract and replay foundations are in place.
- Implement `ArticleAgent`/memory fallback (`KAR-73`, `KAR-74`) after schema + replay.
- Reason: new route classes increase ambiguity and need robust introspection.

5. Integrate Linear issue upsert once canonical artifacts exist.
- Implement `KAR-76` against `ApplicationPack`/`EvalReport` outputs.
- Reason: avoids brittle mapping from ad hoc intermediate fields.

6. Defer multi-user/SaaS isolation until single-user hardening boundaries are explicit.
- Start with idempotency store extraction, credential boundary abstraction, and tenant-aware storage seams (`KAR-62`).
- Reason: avoids premature distributed complexity while preserving a clean migration path.

## Architecture Risks and Guardrails

### High-Risk Areas
- Inbox pipeline orchestration remains dense and can become a change hotspot.
- In-memory webhook dedupe does not protect across process restarts or multiple instances.
- SQLite + local artifact storage constrains horizontal scaling and operational recovery.

### Guardrails
- Keep router deterministic and test-first.
- Enforce schema versioning for artifacts and eval records.
- Treat integrations as optional, isolated side effects.
- Preserve “truthfulness and compile-safe” gates as non-bypassable checks.

## Sources

- `.planning/PROJECT.md` (project goals, active work, constraints)
- `.planning/codebase/ARCHITECTURE.md` (current implemented architecture)
- `.planning/codebase/STRUCTURE.md` (module boundaries and ownership)
- `.planning/codebase/INTEGRATIONS.md` (external service contracts)

---
*Architecture research for: Job Search Agent (brownfield multi-agent job application system)*
*Researched: 2026-03-05*
