# CONVENTIONS

## Language and Style Baseline
- Codebase is Python 3.9+ (`pyproject.toml`) with pervasive type annotations across runtime and tests (for example `Path`, `Optional[...]`, `dict[str, Any]`).
- `from __future__ import annotations` is standard in modules and tests (`app.py`, `main.py`, `core/llm.py`, `tests/test_db.py`).
- Module/class/function docstrings are widely used and usually explain behavior and intent (`agents/inbox/agent.py`, `core/db.py`, `app.py`).
- Logging uses module-level `logger = logging.getLogger(__name__)`; structured message templates with `%s` args are preferred in newer paths (`app.py`), but f-strings still appear (`agents/inbox/adapter.py`).

## Naming Conventions
- Files and modules use `snake_case` (`agents/inbox/url_ingest.py`, `tests/test_followup_runner.py`).
- Functions and variables use `snake_case`; constants are `UPPER_SNAKE_CASE` (`JOBS_DDL`, `RUNS_MIGRATIONS` in `core/db.py`).
- Dataclasses are `PascalCase` and model structured domain payloads (`Settings` in `core/config.py`, `ApplicationPack` in `agents/inbox/agent.py`, `LLMResponse` in `core/llm.py`).
- Internal/private helpers are prefixed with `_` (`_parse_followup_runner_args` in `main.py`, `_keyword_coverage` in `agents/inbox/agent.py`).
- Test helper doubles use `_Dummy*` / `_Fake*` naming (`tests/test_llm.py`, `tests/test_webhook_api_e2e.py`, `tests/test_integration_pipeline_adapter.py`).

## Structural and Design Patterns
- Dependency access is centralized through `get_settings()` singleton from `core/config.py`, then patched in tests via monkeypatch.
- Pipeline orchestration is step-oriented with explicit progress comments and staged exception handling (`agents/inbox/agent.py`).
- Storage layer wraps SQLite with context-managed connections (`get_conn`) and small CRUD helpers (`core/db.py`).
- Adapter pattern separates transport/webhook concerns from core pipeline logic (`agents/inbox/adapter.py` delegates to `agents/inbox/agent.py`; `app.py` owns webhook API lifecycle).

## Error Handling Patterns
- Input/argument validation raises `ValueError` for CLI and parser invariants (`main.py`, `agents/followup/runner.py`, `agents/inbox/jd.py`).
- HTTP boundary errors raise `HTTPException` with explicit status codes and stable error messages (`app.py`).
- Pipeline/runtime failures are often captured with broad `except Exception as e`, accumulated into `pack.errors`, and allow degraded completion (`agents/inbox/agent.py`, `agents/inbox/adapter.py`).
- Defensive fallbacks favor continuity over hard failure (example: LLM fallback model retry in `core/llm.py`; compile rollback path in `tests/test_integration_pipeline_adapter.py` expectations).

## Practical Consistency Notes
- Keep new logging consistent with `%s` parameterized logging style used in webhook code (`app.py`) instead of interpolated f-strings.
- Preserve typed signatures and dataclass-centric boundaries for cross-module contracts (`core/config.py`, `core/llm.py`, `agents/inbox/agent.py`).
- For user-visible failures, prefer explicit typed exceptions at boundaries and convert them to stable response/error payloads (`app.py`) rather than leaking raw exceptions.
