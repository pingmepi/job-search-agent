# TESTING

## Framework and Tooling
- Primary framework: `pytest`.
- Async test support: `pytest-asyncio` (`asyncio_mode = "auto"` in `pyproject.toml`).
- HTTP/API tests use FastAPI `TestClient`.
- Test location is centralized under `tests/` via pytest `testpaths` config.
- No dedicated coverage tool configuration (`pytest-cov`, coverage thresholds, or `.coveragerc`) is currently committed.

## Suite Structure
- Current suite shape (from repository scan):
- `17` test files in `tests/`.
- About `107` `test_*` functions/methods.
- Coverage spans unit tests, integration-style tests, and API-level E2E webhook flows.
- File naming maps directly to module/domain under test (`test_db.py`, `test_router.py`, `test_soft_evals.py`, `test_webhook_api_e2e.py`).

## Test Organization Patterns
- Class-based grouping is common for related behaviors (`class TestJDAccuracy`, `class TestRunsCRUD`).
- Standalone function tests are used for focused behavior checks and endpoint responses.
- Behavior-driven naming is used in test names (e.g., `test_webhook_e2e_rejects_invalid_update_payload`).

## Mocking and Isolation Patterns
- `monkeypatch` is the primary mocking mechanism (heavily used across pipeline and adapter tests).
- Tests patch at module import boundaries to isolate dependencies (LLM calls, settings, compile/upload side effects).
- Local fake classes/doubles are used for Telegram app/bot and transport objects.
- External network/provider calls are mocked; LLM tests and soft-eval tests avoid real API calls.
- Temporary filesystem isolation relies on `tmp_path` for DB files, run artifacts, profile fixtures, and LaTeX stubs.

## Integration and E2E Testing Patterns
- Webhook API behavior is validated through `TestClient` with realistic Telegram payloads.
- Retry and idempotency behavior is covered (`tests/test_webhook_retries.py`, `tests/test_webhook_api_e2e.py`).
- Pipeline integration tests validate DB persistence and artifact generation while mocking unstable external dependencies.
- SQLite persistence is asserted directly using `sqlite3.connect(...)` queries in several tests.

## Async Testing Patterns
- Async handler flows use `@pytest.mark.asyncio` and async fakes for adapter/runtime interactions.
- Async offloading (`asyncio.to_thread`) is patched in tests to make behavior deterministic.

## Assertion Style
- `pytest.raises(...)` is used for expected failures and validation errors.
- `pytest.approx(...)` is used for float/tolerance assertions.
- Assertions commonly verify both return values and side effects (DB rows, files, response payloads, retry counters).

## Coverage Characteristics
- Strong coverage on:
- Routing logic.
- JD schema validation and eval scoring.
- OCR quality gates.
- Follow-up progression logic.
- Webhook security/retry/idempotency behavior.
- Pipeline persistence and rollback paths.
- Potentially weaker/implicit areas:
- Full external integration behavior (real provider contracts are mocked in tests).
- No enforced minimum coverage percentage found in repo config.

## Practical Testing Conventions to Preserve
- Keep tests deterministic by mocking LLM/network/IO boundaries.
- Use `tmp_path` per test for any persistent artifacts.
- Validate both happy path and degradation/fallback behavior.
- Include negative-path tests whenever adding new validation or webhook parsing logic.
- When adding pipeline steps, add at least one integration test proving persisted eval/context output.
