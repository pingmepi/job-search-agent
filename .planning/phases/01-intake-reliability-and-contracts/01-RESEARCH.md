# Phase 1 Research: Intake Reliability and Contracts

## Scope
Phase 1 must satisfy: `ING-01`, `ING-02`, `ING-03`, `OPS-03`, `OPS-04`.

## Current Baseline (Repo-Tailored)
- Webhook ingress exists in `app.py` with secret validation, at-most-once in-memory dedupe, and retry loop.
- Telegram intake paths exist in `agents/inbox/adapter.py` for text/photo URL handling.
- Deterministic router exists in `core/router.py` (`INBOX`, `PROFILE`, `FOLLOWUP`, `CLARIFY`).
- URL extraction helper exists in `agents/inbox/url_ingest.py` with explicit failure result.
- Runs/jobs are persisted in SQLite (`core/db.py`) and run JSON (`evals/logger.py`), but raw webhook payload replay and canonical versioned artifact contracts are not formalized.

## Practical Implementation Approach

### 1) Stabilize intake envelope and deterministic routing (`ING-01`, `OPS-03`)
Keep deterministic routing as the control plane and add explicit non-job branches instead of CLARIFY-only fallback.

Implementation:
- Extend `core/router.py`:
  - Add targets: `ARTICLE`, `AMBIGUOUS_NON_JOB`.
  - Add deterministic article heuristics (long-form/news/blog markers, low JD signal).
  - Return machine-stable reason codes (not just prose) for telemetry and tests.
- Update `agents/inbox/adapter.py`:
  - Branch handling for new targets.
  - `ARTICLE`: send deterministic response (e.g., "article detected; send a JD screenshot/text/URL").
  - `AMBIGUOUS_NON_JOB`: preserve current clarify UX, but with fixed branch id.
- Add route decision logging fields in adapter/webhook flow:
  - `route_target`, `route_reason_code`, `input_mode`, `update_id`.

Why this fits repo:
- Reuses existing `route()` architecture and tests (`tests/test_router.py`).
- Avoids LLM routing regression risk in a reliability phase.

### 2) Make URL failure fallback contract explicit (`ING-02`)
Current behavior already prompts for screenshot fallback when URL fetch fails; promote this to a tested contract.

Implementation:
- In `agents/inbox/adapter.py`, centralize fallback message text as a constant (single source of truth).
- In `agents/inbox/url_ingest.py`, classify error type (`network`, `http`, `insufficient_text`, `unsupported_scheme`) for better operator debugging.
- Add adapter tests asserting:
  - URL failure triggers fallback prompt.
  - Pipeline does not continue with low-confidence URL content.

Why this fits repo:
- Existing URL ingest API already returns `ok/error/extracted_text` and is easy to extend without changing pipeline internals.

### 3) Persist raw webhook events for replay (`ING-03`)
Move from in-memory-only dedupe to durable replay records.

Implementation:
- Extend DB schema in `core/db.py` with table:
  - `webhook_events(event_id TEXT PRIMARY KEY, update_id INTEGER, received_at TEXT, headers_json TEXT, payload_json TEXT, secret_valid INTEGER, processing_status TEXT, run_id TEXT, route_target TEXT, error_text TEXT)`
- Add DB helpers in `core/db.py`:
  - `insert_webhook_event(...)`
  - `mark_webhook_event_processed(...)`
  - `get_webhook_event(event_id | update_id)`
  - `list_webhook_events(...)`
- Update `app.py` webhook handler:
  - Generate stable `event_id` (hash of `update_id + payload canonical json + received timestamp` or UUID with indexed `update_id`).
  - Persist raw payload + selected headers immediately after auth check.
  - Update record status through retry lifecycle.
- Add replay CLI command in `main.py`:
  - `python main.py replay-webhook --event-id <id>` (or `--update-id <id>`) to re-submit persisted payload into `process_update`.

Why this fits repo:
- Reuses existing SQLite pattern/migrations in `core/db.py` and operational CLI model in `main.py`.
- Keeps replay local and deterministic.

### 4) Define canonical versioned JSON artifact contracts (`OPS-04`)
The pipeline currently writes mixed outputs (run JSON + artifact files). Add explicit schema-versioned contracts.

Implementation:
- Add new module `core/contracts.py` (Pydantic/dataclass contracts):
  - `JobExtractionArtifact` (from JD extraction)
  - `ResumeOutputArtifact` (resume base, mutation summary, compile outcome, pdf path)
  - `EvalOutputArtifact` (hard/soft eval metrics, token/cost/latency)
  - shared `schema_version` + `run_id` + `created_at` + trace fields (`jd_hash`, `input_mode`).
- Add artifact writer module `core/artifacts.py`:
  - `write_artifact(run_id, artifact_type, payload)` with deterministic paths under `runs/artifacts/<run_id>/`.
- Update `agents/inbox/agent.py`:
  - Write all three canonical artifacts per run.
  - Include artifact paths in `run_context` passed to `log_run`.
- Optionally update `evals/logger.py`:
  - Add top-level references to canonical artifact paths.

Why this fits repo:
- Aligns with current `runs/` storage and avoids replacing current logs immediately.
- Backward compatible: keep existing `run-*.json` while introducing strict contracts.

## Sequencing
1. Contract-first scaffolding (`core/contracts.py`, `core/artifacts.py`) and tests.
2. DB migration + webhook event persistence + replay command.
3. Router branch expansion (`ARTICLE`, `AMBIGUOUS_NON_JOB`) and adapter branch handling.
4. URL fallback contract hardening + tests.
5. Pipe artifacts through `agents/inbox/agent.py` and attach to run context.
6. Final regression suite and docs updates.

Reasoning:
- Replay and contracts are foundation dependencies for reliable debugging of routing/intake changes.
- Routing changes before contract/persistence increase regression triage cost.

## Risks and Tradeoffs
- In-memory dedupe vs DB dedupe:
  - Tradeoff: DB dedupe is slower but survives restart and supports replay.
  - Decision: keep in-memory fast-path and add DB durability for audit/replay.
- Strict artifact schemas vs rapid iteration:
  - Tradeoff: schema validation can fail fast and block runs during rollout.
  - Decision: implement `schema_version="1.0"` and fail-write with explicit error capture in run errors.
- Article routing false positives:
  - Tradeoff: over-classification can block valid JD text.
  - Decision: conservative heuristics plus escape hatch message (user can resend with "job:" prefix or screenshot).
- Replay side effects:
  - Tradeoff: replay could duplicate downstream side effects (Drive/calendar).
  - Decision: replay default with `skip_upload=true`, `skip_calendar=true`, and explicit override flag.

## Concrete File-Level Targets
Modify:
- `app.py` (persist webhook events, status transitions, durable event IDs)
- `main.py` (add `replay-webhook` command)
- `core/db.py` (new `webhook_events` schema + CRUD helpers)
- `core/router.py` (new deterministic branches + reason codes)
- `agents/inbox/adapter.py` (new branch handling + fallback constant + richer logs)
- `agents/inbox/agent.py` (write canonical artifacts + context linkage)
- `evals/logger.py` (optional artifact path linkage in run log)

Add:
- `core/contracts.py` (versioned canonical artifact models)
- `core/artifacts.py` (artifact writer/path policy)
- `tests/test_webhook_events.py` (event persistence + replay lifecycle)
- `tests/test_replay_webhook_cli.py` (CLI replay behavior)
- `tests/test_artifact_contracts.py` (schema validation and artifact writing)
- `tests/test_router_article_handling.py` (new deterministic branches)

## Validation Architecture

Test strategy:
- Unit layer:
  - Router decision table tests for JD/article/ambiguous cases.
  - URL ingest error typing and fallback message contract.
  - Artifact schema validation tests with required/optional fields and `schema_version` checks.
- Integration layer:
  - Webhook endpoint persists payload before processing and updates status across retries.
  - Replay command can re-run a persisted event deterministically.
  - Pipeline writes `job_extraction.json`, `resume_output.json`, `eval_output.json` under `runs/artifacts/<run_id>/`.
- Regression layer:
  - Existing webhook retry/dedupe and DB/run logging suites remain green.

Primary commands:
```bash
./.venv/bin/python main.py init-db
./.venv/bin/pytest -q tests/test_router.py tests/test_url_ingest.py tests/test_webhook_api_e2e.py tests/test_webhook_retries.py tests/test_db.py
./.venv/bin/pytest -q tests/test_webhook_events.py tests/test_replay_webhook_cli.py tests/test_artifact_contracts.py tests/test_router_article_handling.py
./.venv/bin/pytest -q
```

Manual verification commands:
```bash
./.venv/bin/python main.py webhook
curl -i -X POST http://127.0.0.1:8000/telegram/webhook \
  -H "Content-Type: application/json" \
  -H "X-Telegram-Bot-Api-Secret-Token: $TELEGRAM_WEBHOOK_SECRET" \
  -d '{"update_id":123456,"message":{"message_id":1,"date":1700000000,"chat":{"id":777,"type":"private"},"text":"https://example.com/job"}}'
./.venv/bin/python main.py replay-webhook --update-id 123456
```

Exit criteria for Phase 1:
- Intake works for text/url/image with deterministic route telemetry.
- URL extraction failure always returns screenshot fallback prompt.
- Raw webhook events are queryable/replayable via stable IDs and timestamps.
- Non-job/article content follows explicit deterministic branches.
- Versioned canonical JSON artifacts are produced for extraction/resume/eval on every successful run.
