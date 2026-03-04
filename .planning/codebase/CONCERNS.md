# CONCERNS

## Summary
This repository is functional and has solid test scaffolding, but there are several high-impact concerns in runtime reliability and security boundaries. The highest risks are webhook timeout semantics, URL-fetch SSRF exposure, and follow-up cadence logic.

## Critical Concerns

### 1) SSRF risk in user-supplied URL ingestion
- Type: Security
- Evidence:
  - `agents/inbox/adapter.py:177-180` passes user-provided URLs into `fetch_url_text`.
  - `agents/inbox/url_ingest.py:42-63` fetches arbitrary `http/https` URLs with `urlopen` and no private-address filtering, hostname allowlist, redirect policy, or content-type checks.
- Risk:
  - A malicious Telegram message can make the server fetch internal endpoints (metadata services, private network hosts, local admin interfaces).
- Recommended mitigation:
  - Enforce URL allowlist/denylist rules (block RFC1918, loopback, link-local, metadata IPs/domains).
  - Resolve and validate DNS target IP before request and after redirects.
  - Restrict to known job-board domains if possible.
  - Add response size/content-type limits.

### 2) Follow-up cadence bug can spam contacts within hours
- Type: Bug / Product risk
- Evidence:
  - `core/db.py:148-156` selects jobs older than 7 days based only on `created_at`.
  - `agents/followup/agent.py:112-121` updates `last_follow_up_at`, but this field is not used in selection.
- Risk:
  - Once a job crosses 7 days old, each scheduler cycle can send another follow-up until `MAX_FOLLOW_UPS` is reached (potentially in 3 consecutive hourly runs).
- Recommended mitigation:
  - Base eligibility on `last_follow_up_at` (or `created_at` if never followed up) with per-tier cooldown windows.
  - Add tests for tier progression over time windows.

### 3) Webhook timeout path marks updates as processed even if work may still fail
- Type: Reliability / Data-loss risk
- Evidence:
  - `app.py:147-171` wraps processing in `asyncio.wait_for(...)`.
  - On timeout, it sets `last_error = None` and adds update ID to `processed_update_ids` (`app.py:166-170`).
  - Comment explicitly states work may continue after timeout (`app.py:158-159`).
- Risk:
  - Telegram redelivery is suppressed while underlying work may not complete successfully; failed jobs can be silently dropped.
- Recommended mitigation:
  - Use explicit async job queue + durable state for idempotency.
  - Only mark processed after terminal success/failure persisted to DB.
  - Return 5xx on uncertain completion to allow safe retry with dedupe key.

## High Concerns

### 4) In-memory dedupe state is unbounded and non-durable
- Type: Performance / Reliability
- Evidence:
  - `app.py:26-28` uses in-memory sets/dict for processed and in-flight update IDs.
  - No TTL or compaction is implemented.
- Risk:
  - Memory growth over long uptime; restart loses dedupe state and can replay updates.
- Recommended mitigation:
  - Move dedupe state to SQLite/Redis with TTL and bounded retention.

### 5) Unsafe `pickle.load` for OAuth token files
- Type: Security
- Evidence:
  - `integrations/drive.py:43-46` and `integrations/calendar.py:47-50` deserialize token files via `pickle.load`.
- Risk:
  - If token file is tampered with, arbitrary code execution is possible during load.
- Recommended mitigation:
  - Store tokens as JSON using Google credential serialization methods, not pickle.
  - Enforce strict file permissions and ownership checks.

### 6) Dynamic SQL column construction in `update_job`
- Type: Fragility / Future security debt
- Evidence:
  - `core/db.py:160-168` builds `SET` clause directly from `**fields` keys.
- Risk:
  - Internal callers are currently trusted, but any future externalized field path can become SQL-injection-prone or break on invalid columns.
- Recommended mitigation:
  - Enforce a whitelist of allowed columns before query construction.

### 7) Synchronous heavy pipeline behind webhook request path
- Type: Performance / Availability
- Evidence:
  - `agents/inbox/adapter.py:102-108` and `192-197` execute full pipeline in request-triggered flow.
  - `agents/inbox/agent.py` performs OCR, multiple LLM calls, LaTeX compile, Drive/Calendar actions in one call path.
- Risk:
  - High latency and timeout sensitivity under load; threadpool contention; inconsistent UX.
- Recommended mitigation:
  - Move to async job queue; immediately acknowledge webhook; report completion via follow-up message.

## Medium Concerns

### 8) Monolithic orchestrator with broad exception swallowing
- Type: Technical debt / Fragility
- Evidence:
  - `agents/inbox/agent.py:105-602` is a large multi-responsibility function.
  - Repeated broad catches (`agents/inbox/agent.py:251-253`, `355-363`, `381-382`, `389-390`, `436-437`, `467-468`, `514-515`, `540-541`, `599-600`).
- Risk:
  - Hidden regressions, hard debugging, and partial success states that are difficult to reason about.
- Recommended mitigation:
  - Split into explicit stages with typed stage results.
  - Standardize recoverable vs fatal error policy per stage.

### 9) DB connection settings are minimal for concurrent webhook workloads
- Type: Performance / Reliability
- Evidence:
  - `core/db.py:108-114` creates default SQLite connections; no busy timeout, WAL, foreign key enforcement pragma.
- Risk:
  - More likely to hit lock contention and integrity drift as concurrency grows.
- Recommended mitigation:
  - Configure `PRAGMA journal_mode=WAL`, `PRAGMA foreign_keys=ON`, and reasonable busy timeout.

### 10) Cost-resolution adds synchronous tail latency
- Type: Performance
- Evidence:
  - `agents/inbox/agent.py:501-514` resolves costs before finishing.
  - `core/llm.py:128-149` resolves each generation ID sequentially with network I/O.
- Risk:
  - Adds variable end-of-request latency and increases timeout pressure.
- Recommended mitigation:
  - Defer cost-resolution to background telemetry task or batch asynchronously.

### 11) Limited test coverage on abuse/operational edge cases
- Type: Quality risk
- Evidence:
  - URL ingest tests (`tests/test_url_ingest.py`) cover basic success/scheme validation but not SSRF/private-network blocking.
  - Follow-up runner tests (`tests/test_followup_runner.py`) do not validate cooldown behavior against `last_follow_up_at`.
  - Webhook tests validate happy/error paths but not sustained dedupe memory behavior.
- Risk:
  - Regressions likely in production-only scenarios.
- Recommended mitigation:
  - Add tests for SSRF guards, follow-up cooldown semantics, dedupe TTL/eviction, and timeout/retry race behavior.

## Fragile Areas to Watch
- `app.py` webhook processing semantics (idempotency, timeout, retries).
- `agents/inbox/agent.py` pipeline orchestration and partial-failure policy.
- `core/db.py` follow-up selection/update semantics and concurrent access behavior.
- `integrations/*.py` credential/token handling and side-effect reliability.

## Suggested Priority Order
1. Fix follow-up eligibility logic and add cooldown tests.
2. Add SSRF protections around URL ingestion.
3. Redesign webhook processing to durable async jobs + persistent dedupe.
4. Replace pickle token storage and harden credential file handling.
5. Refactor `run_pipeline` into stage modules with explicit error contracts.
