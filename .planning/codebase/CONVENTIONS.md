# CONVENTIONS

## Scope
- Repository type: Python 3.9+ service-style application with FastAPI webhook runtime and multi-agent pipeline logic.
- Primary source roots: `agents/`, `core/`, `evals/`, `integrations/`, entrypoints `main.py` and `app.py`.

## Code Style
- Type-hint-first style is used broadly (function signatures, dataclass fields, local variables in critical paths).
- `from __future__ import annotations` is used in most modules for forward-reference-friendly typing.
- Module-level docstrings are common and usually explain purpose plus runtime context.
- Standard library imports are generally grouped before local imports.
- Formatting appears Black-compatible (4-space indent, double-quoted strings, trailing commas), but no explicit formatter config is committed.

## Naming Conventions
- Modules and files use `snake_case` (`url_ingest.py`, `followup_runner.py`, `test_soft_evals.py`).
- Functions and variables use `snake_case`; constants use `UPPER_SNAKE_CASE` (`JOBS_DDL`, `_URL_PATTERN`).
- Classes use `PascalCase` (`ApplicationPack`, `RouteResult`, `TelegramWebhookRuntime`).
- Internal helpers are prefixed with `_` (`_env_bool`, `_slugify_filename_part`, `_outside_editable_content_changed`).
- Test classes follow `Test*` and test functions follow `test_*`.

## Typing and Data Modeling Patterns
- `dataclass` is the primary data model primitive for internal structs (`Settings`, `ApplicationPack`, `LLMResponse`, `RouteResult`).
- `Optional[T]` and `T | None` are both used (mixed style but consistently meaningful).
- Return shapes are explicit for public functions (`dict[str, Any] | None`, `list[dict[str, Any]]`, etc.).
- Pydantic is a dependency, but core domain objects are mostly dataclasses and explicit validation functions.

## Architectural Patterns in Code
- Layered separation is visible:
- `core/` for infra primitives (config, DB, LLM client, router).
- `agents/` for domain workflows and adapters.
- `evals/` for scoring/guardrail logic.
- Orchestration-heavy functions (`run_pipeline`) aggregate step-by-step operations while keeping helper logic in module-private functions.
- Configuration is centralized through `core.config.get_settings()` singleton access.
- Deterministic routing intentionally avoids LLM use in `core/router.py`.

## Error Handling Conventions
- Operational pipeline code favors resilient, step-local `try/except` blocks that collect recoverable errors instead of crashing whole runs.
- Recoverable failures are appended to `pack.errors` in `agents/inbox/agent.py` and processing continues when possible.
- API boundary errors are translated into `HTTPException` with explicit status codes in `app.py`.
- Parsing/validation functions raise typed errors (`ValueError`, `TypeError`, `FileNotFoundError`) when data is invalid.
- Fallback behavior is explicit in key paths (LLM model fallback, PDF compile rollback, webhook retry loop).
- Some broad `except Exception` blocks are intentionally defensive in runtime-facing code.

## Logging and Observability Patterns
- Module-level `logger = logging.getLogger(__name__)` is standard.
- Logs use structured message templates and include runtime identifiers where possible (`update_id`, `attempt`, `latency_ms`).
- Logging levels align with severity (`info` for state transitions, `warning` for degraded behavior, `error/exception` for failures).

## Consistency Notes and Gaps
- No committed linter config (`ruff`, `flake8`, `pylint`) or formatter config (`black`, `isort`) was found in `pyproject.toml`.
- No pre-commit config was found; conventions are mostly enforced socially and by tests.
- Type checking is style-oriented (good annotations) but no mypy/pyright config was found.
- String interpolation style is mixed (`f"..."` and logger `%s` formatting), with `%s` used in many logging callsites.

## Practical Convention Summary
- Keep new modules in `snake_case` and expose typed public functions.
- Prefer dataclasses for internal domain payloads.
- Route user/input-facing errors into explicit, non-crashing outcomes.
- Preserve stepwise pipeline structure with local fallback handling.
- Add tests for regressions whenever fallback or retry behavior changes.
