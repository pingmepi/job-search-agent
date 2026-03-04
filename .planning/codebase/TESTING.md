# TESTING

## Frameworks and Configuration
- Test runner is `pytest` with async support through `pytest-asyncio` (`pyproject.toml` optional deps).
- Pytest config is minimal and centralized in `pyproject.toml`:
  - `testpaths = ["tests"]`
  - `asyncio_mode = "auto"`
- Project docs use `.venv/bin/pytest -q` as the standard command (`README.md`, `docs/setup-and-test.md`).

## Test Layout and Scope
- Tests are flat under `tests/` with domain-focused files (`tests/test_db.py`, `tests/test_llm.py`, `tests/test_webhook_retries.py`, `tests/test_integration_pipeline_adapter.py`).
- Naming convention is `test_<area>.py` plus descriptive test function names (`test_webhook_e2e_rejects_invalid_update_payload`).
- Mix of function-style tests and grouped class-based suites (for example `TestSchema`/`TestRunsCRUD` in `tests/test_db.py`, class suites in `tests/test_soft_evals.py`).
- E2E-ish API verification uses FastAPI `TestClient` with realistic Telegram payloads (`tests/test_webhook_api_e2e.py`).

## Mocking and Isolation Patterns
- Primary mechanism is `monkeypatch` to replace runtime dependencies and side effects:
  - Settings injection (`agents.inbox.agent.get_settings`, `core.db.get_settings` in `tests/test_integration_pipeline_adapter.py`).
  - LLM/network adapters (`evals.soft.chat_text` in `tests/test_soft_evals.py`, `_get_client` in `tests/test_llm.py`).
  - Async/thread boundaries (`adapter.asyncio.to_thread` in `tests/test_integration_pipeline_adapter.py`).
- Lightweight fake objects (`_Dummy*`, `_Fake*`) are preferred over heavy mocking frameworks (`tests/test_llm.py`, `tests/test_webhook_api_e2e.py`).
- Filesystem and DB isolation rely on `tmp_path` fixtures and temporary SQLite files (`tests/test_db.py`, `tests/test_integration_pipeline_adapter.py`).

## Coverage Approach (Observed)
- No explicit coverage tool/config (`pytest-cov`, coverage thresholds, or CI gate) is defined in `pyproject.toml`.
- Coverage strategy is behavior-driven via representative scenario tests:
  - Success + retry/fallback paths (`tests/test_llm.py`, `tests/test_webhook_retries.py`, `tests/test_integration_pipeline_adapter.py`).
  - Edge/error parsing behavior (`tests/test_soft_evals.py`, `tests/test_jd.py`, `tests/test_ocr.py`).
  - Persistence/schema invariants (`tests/test_db.py`).
- Some lines are intentionally excluded from strict coverage via `# pragma: no cover` comments (`tests/test_health.py`, `agents/inbox/url_ingest.py`).

## Practical Test Writing Conventions
- Keep tests deterministic: stub all external services (OpenRouter, Telegram, URL fetch, OCR side effects) and assert contract outputs, not implementation details.
- Prefer single-responsibility assertions per scenario with explicit fixture setup in test body when stateful flows are under test (`tests/test_integration_pipeline_adapter.py`).
- Preserve production-like payload shapes in boundary tests (Telegram update JSON in `tests/test_webhook_api_e2e.py`) to catch schema drift early.
