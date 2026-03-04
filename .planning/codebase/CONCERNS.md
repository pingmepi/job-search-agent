# Codebase Concerns

## Scope
This document tracks current technical debt, known issues, and risk areas identified from the codebase and tracker state.

## Critical Concerns

### 1) In-memory webhook dedupe is process-local and unbounded
- Risk: Duplicate processing can happen after service restart, and memory can grow indefinitely under sustained traffic.
- Evidence: `app.py` keeps `processed_update_ids`, `processing_update_ids`, and `update_attempts` only in memory with no TTL or persistence.
- File references: `app.py`.
- Impact: Reliability regression (duplicate executions), and long-running process memory growth.
- Practical mitigation: Persist dedupe state in SQLite (`update_id`, status, timestamp) and prune old entries.

### 2) Timeout path marks updates as processed before work is guaranteed complete
- Risk: Lost work or inconsistent side effects if background/threaded work continues after timeout but update is treated as done.
- Evidence: `app.py` catches `asyncio.TimeoutError`, logs warning, then adds `update_id` to processed set and returns `{"ok": true}`.
- File references: `app.py`, `agents/inbox/adapter.py` (`asyncio.to_thread` usage).
- Impact: At-least-once delivery semantics are weakened; failures may be hidden from retries.
- Practical mitigation: Introduce explicit pipeline completion ack + idempotent run keys before marking processed.

### 3) Unsafe deserialization of OAuth token pickle files
- Risk: Local code execution if token pickle files are tampered with.
- Evidence: `pickle.load` is used directly for credential token files.
- File references: `integrations/drive.py`, `integrations/calendar.py`.
- Impact: Security exposure on shared/dev hosts and CI-like environments.
- Practical mitigation: Store tokens in safer serialized formats (JSON credentials supported by Google libs) and enforce restrictive file permissions.

## High Concerns

### 4) SQL updates use dynamic column interpolation
- Risk: Future callsites could accidentally pass unexpected keys, causing schema drift bugs or injection-like risk if field names become user-derived.
- Evidence: `update_job` builds `set_clause` with f-string column interpolation.
- File references: `core/db.py`.
- Impact: Fragility and maintainability risk; harder to reason about allowed writes.
- Practical mitigation: Whitelist allowed columns in `update_job`.

### 5) URL ingestion lacks SSRF hardening and content limits
- Risk: Internal network probing or large response download pressure if URLs are untrusted.
- Evidence: URL validation only checks scheme/netloc; no host allow/block policy, IP range checks, or max response bytes.
- File references: `agents/inbox/url_ingest.py`.
- Impact: Security and performance risk in production-facing webhook mode.
- Practical mitigation: Add DNS/IP private-range blocking, response size cap, and stricter content-type checks.

### 6) Error details are echoed back to users
- Risk: Internal implementation details can leak through chat responses.
- Evidence: Exception messages are sent directly in user-visible replies.
- File references: `agents/inbox/adapter.py`.
- Impact: Information disclosure and inconsistent UX.
- Practical mitigation: Return stable user-safe messages and log detailed exceptions server-side only.

## Medium Concerns

### 7) Retry policy is fixed and non-jittered
- Risk: Burst failures may synchronize retries and worsen provider pressure.
- Evidence: Webhook retries are exactly 3 attempts with fixed `0.2s` delay.
- File references: `app.py`.
- Impact: Lower resilience under transient outages.
- Practical mitigation: Exponential backoff with jitter and categorized retryability.

### 8) Cost resolution is synchronous and serial
- Risk: End-of-pipeline latency increases linearly with number of generation IDs.
- Evidence: `resolve_costs_batch` does one global sleep then sequential per-ID network calls.
- File references: `core/llm.py`.
- Impact: Performance drag and potential webhook timeout pressure in long runs.
- Practical mitigation: Resolve costs asynchronously/offline (post-run job) with bounded concurrency.

### 9) Operational scripts can kill unrelated listeners on configured port
- Risk: Service restart script may terminate non-agent processes sharing the port.
- Evidence: `scripts/restart_webhook.sh` kills all listening PIDs on target port.
- File references: `scripts/restart_webhook.sh`.
- Impact: Operational fragility on shared hosts.
- Practical mitigation: Track and kill only owned PID/process signatures.

## Known Issues From Tracker

### 10) CI gate is documented as failing on historical eval thresholds
- Risk: Quality gate noise can hide real regressions and reduce trust in CI signals.
- Evidence: Tracker notes failing compile success/forbidden-claims thresholds due to historical runs.
- File references: `TRACKER.md`, `evals/ci_gate.py`.
- Impact: Slower release confidence and triage fatigue.
- Practical mitigation: Separate historical analytics from release gates; gate on bounded recent window or branch-local runs.

### 11) Raw webhook event persistence is still pending
- Risk: Incident forensics and replay are limited.
- Evidence: Pending item `KAR-72` to persist raw webhook events.
- File references: `TRACKER.md`.
- Impact: Debuggability and auditability gap.
- Practical mitigation: Persist normalized raw events with retention and redaction policy.

## Fragile Areas To Monitor
- `agents/inbox/agent.py`: single large orchestrator with many side-effecting steps and broad exception handling; high change coupling.
- `app.py`: webhook correctness depends on runtime state machine + timeout behavior.
- `core/db.py`: lightweight migration approach is simple but brittle for future schema complexity.
