# Architecture

## Summary
This repository is a webhook-first, multi-agent Python system for job application automation. The runtime is message-driven from Telegram updates, with deterministic routing and specialized agents for inbox processing, profile Q&A, and follow-up generation.

## Architectural Pattern
- Pattern: Layered modular monolith (single deployable service + internal modules)
- Orchestration style: Agent-oriented workflow with explicit function boundaries
- Runtime mode: FastAPI webhook service hosting a python-telegram-bot `Application`
- Persistence: PostgreSQL via `psycopg2-binary` and hand-written data access helpers in `core/db.py`
- External integration model: Adapter modules under `integrations/` and message ingress adapter in `agents/inbox/adapter.py`

## Core Layers

### 1) Interface and Entry Layer
- HTTP entrypoint: `app.py`
- CLI entrypoint: `main.py`
- Telegram message adapter/handlers: `agents/inbox/adapter.py`
- Health and webhook endpoints:
  - `GET /health`
  - `POST /telegram/webhook` (or configured path)

Responsibilities:
- Validate webhook secret
- Parse Telegram update payloads
- Deduplicate update processing (`processed_update_ids`, `processing_update_ids`)
- Route user intents and invoke domain agents

### 2) Routing and Control Layer
- Deterministic router: `core/router.py`

Responsibilities:
- Classify input by content signals (image, URL, keywords, JD indicators)
- Select target agent: `INBOX`, `PROFILE`, `FOLLOWUP`, or `CLARIFY`
- Keep routing behavior non-LLM and reproducible

### 3) Domain Agent Layer
- Inbox pipeline orchestrator: `agents/inbox/agent.py`
- Follow-up logic: `agents/followup/agent.py`, scheduler `agents/followup/runner.py`
- Profile responder: `agents/profile/agent.py`

Responsibilities:
- Inbox: end-to-end pipeline (OCR/JD extraction/resume mutation/compile/integrations/evals/telemetry)
- Follow-up: detect due jobs, generate tiered follow-up drafts, optionally persist follow-up progress
- Profile: grounded narrative response generation from profile data

### 4) Shared Core Services Layer
- Config singleton: `core/config.py`
- Database access: `core/db.py`
- LLM gateway: `core/llm.py`
- Prompt loader/versioning: `core/prompts/__init__.py`
- PDF utilities: `core/extract_pdfs.py`

Responsibilities:
- Centralize settings and paths
- Encapsulate storage schema and migrations
- Standardize LLM calls and deferred cost lookup
- Decouple prompt text from Python code

### 5) Integration Layer
- Google Drive adapter: `integrations/drive.py`
- Google Calendar adapter: `integrations/calendar.py`
- URL ingestion helper: `agents/inbox/url_ingest.py`

Responsibilities:
- Boundary to third-party APIs
- OAuth token management and API client creation
- File upload/event creation and URL text fetch

### 6) Quality and Evaluation Layer
- Hard gates: `evals/hard.py`
- Soft checks: `evals/soft.py`
- Run logging helper: `evals/logger.py`
- CI gate: `evals/ci_gate.py`

Responsibilities:
- Validate schema/claims/cost/draft constraints
- Persist quality and telemetry outcomes in runs table

## Data Flow

### Telegram Webhook Flow
1. Telegram sends update to FastAPI webhook (`app.py`).
2. Webhook verifies secret token and parses update.
3. Adapter handlers process command/photo/text (`agents/inbox/adapter.py`).
4. Text route determined by `core/router.py`.
5. Target agent executes:
   - Inbox: `run_pipeline(...)`
   - Profile: `answer(...)`
   - Follow-up: status or follow-up generation path
6. Reply messages are sent back through Telegram bot API.

### Inbox Pipeline Flow
1. Input normalization: text, URL extraction/fetch, or image OCR.
2. JD extraction: LLM prompt -> structured JD schema.
3. Resume selection: choose base resume by skills fit.
4. Resume mutation: LLM-guided editable-region mutation.
5. Compile: LaTeX to PDF with single-page enforcement/condense retries.
6. Optional integrations: upload PDF to Drive, create Calendar events.
7. Draft generation: email/linkedin/referral text.
8. Evaluation gates + telemetry logging.
9. Persistence: job/run records in PostgreSQL.

## Main Abstractions
- `Settings` dataclass (`core/config.py`): immutable runtime configuration contract
- `LLMResponse` dataclass (`core/llm.py`): normalized LLM response envelope
- `RouteResult` dataclass (`core/router.py`): deterministic routing output
- `ApplicationPack` dataclass (`agents/inbox/agent.py`): end-to-end pipeline result container

These abstractions provide explicit typed handoffs across modules and reduce implicit dict-based coupling in critical paths.

## Entry Points
- Service runtime:
  - `python main.py webhook`
  - module-level ASGI app object: `app:app`
- Initialization:
  - `python main.py init-db`
- Evaluation and diagnostics:
  - `python main.py ci-gate`
  - `python main.py db-stats`
- Scheduled flow:
  - `python main.py followup-runner [--once|--dry-run|--interval-minutes ...]`

## Dependency Direction
- Outer layers (`app.py`, handlers) depend inward on core/domain modules.
- Domain agents depend on shared core services and integrations.
- `core/*` is foundational and does not depend on `agents/*`.
- `integrations/*` are invoked by domain logic but isolated from transport entrypoints.

This mostly preserves one-way dependencies and supports incremental modularization if split into separate services later.

## Architectural Strengths
- Clear boundary between ingress/routing and domain execution
- Deterministic routing removes LLM uncertainty for intent classification
- Centralized config + prompt versioning improves operational control
- Pipeline state encapsulated in `ApplicationPack`
- Webhook dedupe/retry logic reduces duplicate processing risk

## Architectural Constraints and Tradeoffs
- Single-process in-memory webhook dedupe state is not durable across restarts
- PostgreSQL handles concurrent writes; `runs/` artifacts remain ephemeral (single-node) — PDFs sent to Telegram before the process exits, so this is acceptable until object storage is added
- Domain pipeline in `agents/inbox/agent.py` is feature-rich and comparatively heavy, increasing coupling
- No explicit interface/protocol classes for integrations, so adapters are concrete-function based

## Suggested Evolution Path
- Extract inbox pipeline stages into smaller service modules/classes for testability
- Move webhook idempotency state to persistent/shared storage if scaling out
- Introduce explicit integration interfaces (ports) and adapter implementations
- Add domain event objects for clearer boundaries between pipeline stages
