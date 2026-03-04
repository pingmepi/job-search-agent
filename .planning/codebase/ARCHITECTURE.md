# Architecture

## System Style
- The repository is a modular monolith in Python: transport adapters, domain agents, shared core services, integrations, and evaluation logic are separated by package (`agents/`, `core/`, `integrations/`, `evals/`).
- Runtime is webhook-first: FastAPI receives Telegram updates in `app.py`, then delegates update handling to a `python-telegram-bot` `Application` created in `agents/inbox/adapter.py`.
- The primary business pipeline is orchestrated in one function, `run_pipeline()` in `agents/inbox/agent.py`, which executes OCR/JD extraction/resume mutation/compile/integrations/drafts/persistence/evaluation end-to-end.
- Persistence is SQLite-centered via `core/db.py`, with telemetry dual-written to DB plus JSON logs (`runs/*.json`) via `evals/logger.py`.

## Layers

### 1) Entry/Transport Layer
- CLI entrypoint: `main.py`.
- Web server entrypoint: `app.py` (`create_webhook_app()`, `run_webhook_server()`).
- Bot message adapter and handlers: `agents/inbox/adapter.py`.

Responsibilities:
- Accept external events (HTTP webhook, Telegram commands/messages, CLI commands).
- Perform request-level controls (webhook secret check, update dedupe/retry/timeout in `app.py`).
- Route user text to target agents via deterministic router (`core/router.py`).

### 2) Orchestration Layer
- Inbox pipeline orchestrator: `agents/inbox/agent.py`.
- Follow-up orchestration: `agents/followup/agent.py`, scheduled loop in `agents/followup/runner.py`.
- Profile response orchestration: `agents/profile/agent.py`.

Responsibilities:
- Compose multi-step workflows across extraction, generation, validation, persistence, and integrations.
- Manage step-local fallback behavior (compile fallback, condense retries, optional integrations).
- Assemble cross-step telemetry payloads for run logging.

### 3) Domain/Processing Components
- JD extraction and schema validation: `agents/inbox/jd.py`.
- OCR extraction/cleanup/quality gate: `agents/inbox/ocr.py`.
- Resume parsing/mutation/selection/compile: `agents/inbox/resume.py`.
- Outreach draft generation: `agents/inbox/drafts.py`.
- URL text extraction: `agents/inbox/url_ingest.py`.
- Deterministic routing heuristics: `core/router.py`.

Responsibilities:
- Perform bounded transformations with clear inputs/outputs.
- Encapsulate reusable business rules (editable LaTeX regions, skill overlap selection, follow-up escalation tiers).

### 4) Platform Services
- Configuration and env loading: `core/config.py`.
- LLM gateway and deferred cost resolution: `core/llm.py`.
- Prompt loading/versioning: `core/prompts/__init__.py` + prompt files in `core/prompts/*.txt`.
- Data access and schema/migrations: `core/db.py`.

Responsibilities:
- Centralize shared infra concerns (settings, API clients, DB access, prompt lookup).
- Keep agent code focused on workflow logic.

### 5) Integrations Layer
- Google Drive upload: `integrations/drive.py`.
- Google Calendar event creation: `integrations/calendar.py`.

Responsibilities:
- Isolate third-party API auth/state and API-specific logic from core agent flows.

### 6) Evaluation/Quality Layer
- Hard checks: `evals/hard.py`.
- Soft LLM-judged checks: `evals/soft.py`.
- Run logging: `evals/logger.py`.
- CI gate: `evals/ci_gate.py`.

Responsibilities:
- Provide quality gates/signals independent of business orchestration.
- Persist auditable telemetry per run.

## Primary Data Flow

### A) Webhook message to completed application pack
1. `app.py` receives `POST /telegram/webhook`, validates secret, deduplicates by `update_id`, retries processing up to 3 attempts.
2. `app.py` passes parsed Telegram `Update` to bot app from `agents/inbox/adapter.py`.
3. `agents/inbox/adapter.py` handler:
- Photo path: downloads image and calls `run_pipeline(..., image_path=...)`.
- Text path: calls `core/router.py::route()`.
- If URL present, pre-fetches plain text with `agents/inbox/url_ingest.py` before pipeline.
4. `agents/inbox/agent.py::run_pipeline()` executes stepwise:
- OCR (optional) via `agents/inbox/ocr.py`.
- JD extraction via `agents/inbox/jd.py`.
- Resume selection/mutation/compile via `agents/inbox/resume.py`.
- Optional Drive/Calendar via `integrations/drive.py` and `integrations/calendar.py`.
- Draft generation via `agents/inbox/drafts.py`.
- Job persistence via `core/db.py`.
- Eval computation via `evals/hard.py` and `evals/soft.py`.
- Run logging via `evals/logger.py`.
5. Handler sends summarized completion/errors back to Telegram chat.

### B) Follow-up cycle
1. `main.py followup-runner` invokes `agents/followup/runner.py`.
2. Runner detects jobs needing follow-up (`core/db.py::get_jobs_needing_followup`).
3. Drafts generated with LLM in `agents/followup/agent.py` and progress optionally persisted (`follow_up_count`, `last_follow_up_at`).
4. Runner logs cycle as run telemetry in `runs` table.

### C) Profile Q&A
1. Router sends profile-like queries to `agents/profile/agent.py`.
2. Agent loads `profile/profile.json` and `profile/bullet_bank.json`.
3. LLM answer generated through `core/llm.py`, then checked for grounding heuristics before response.

## Core Abstractions
- `Settings` (`core/config.py`): immutable runtime configuration singleton.
- `LLMResponse` (`core/llm.py`): normalized LLM output shape for usage/cost telemetry.
- `RouteResult` + `AgentTarget` (`core/router.py`): deterministic routing contract.
- `JDSchema` (`agents/inbox/jd.py`): normalized extracted job-description object with deterministic hash.
- `EditableRegion` (`agents/inbox/resume.py`): explicit editable-scope model for safe LaTeX mutation.
- `ApplicationPack` (`agents/inbox/agent.py`): aggregate result model spanning outputs, artifacts, evals, and errors.
- `DraftResult` (`agents/inbox/drafts.py`): typed outreach generation result.

## Entry Points and Execution Modes
- `main.py` command modes:
- `webhook`/`bot`: run FastAPI+Telegram webhook service (`app.py`).
- `init-db`: initialize/migrate SQLite schema (`core/db.py`).
- `ci-gate`: run evaluation gate (`evals/ci_gate.py`).
- `db-stats`: print DB quality/debug stats.
- `followup-runner`: run one-shot or scheduled follow-up processing.
- `app.py` can also be started directly (`run_webhook_server()`) and exposes `GET /health`.

## Architectural Patterns in Use
- Deterministic pre-routing before costly model calls (`core/router.py`).
- Ports/adapters split at boundaries: transport in `app.py`/`agents/inbox/adapter.py`, external APIs in `integrations/*.py`.
- Prompt-as-artifact pattern with versioned text files in `core/prompts/`.
- Cost-latency decoupling: generation cost resolved asynchronously after primary flow (`core/llm.py::resolve_costs_batch`).
- Progressive fallback strategy in critical path (`agents/inbox/agent.py` compile fallback + condense retries).
- Observability by design: structured run logs in both relational (`runs` table) and file (`runs/*.json`) sinks.
