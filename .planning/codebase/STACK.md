# STACK

## Overview
- Project type: Python backend automation service with Telegram webhook ingestion and agent-style processing pipeline (`README.md`, `main.py`, `app.py`).
- Packaging/distribution: setuptools-based Python package named `inbox-agent` (`pyproject.toml`).

## Languages and Runtimes
- Primary language: Python (`main.py`, `app.py`, `core/*.py`, `agents/**/*.py`).
- Python version floor: `>=3.9` (`pyproject.toml`).
- Runtime mode in active flow: webhook-first server process (`python main.py webhook`) (`README.md`, `main.py`).

## Application Frameworks and Core Libraries
- Web framework: FastAPI for webhook/health endpoints (`app.py`, dependency in `pyproject.toml`).
- ASGI server: Uvicorn (`app.py`, dependency in `pyproject.toml`).
- Telegram SDK: `python-telegram-bot` v21+ (`agents/inbox/adapter.py`, dependency in `pyproject.toml`).
- LLM client SDK: `openai` package configured for OpenRouter-compatible endpoint (`core/llm.py`, dependency in `pyproject.toml`).
- Config/env loading: `python-dotenv` and `dataclasses` settings object (`core/config.py`, dependency in `pyproject.toml`).
- Validation/schema tooling: Pydantic models used in extraction flows (`agents/inbox/jd.py`, dependency in `pyproject.toml`).

## Data and Persistence
- Database: SQLite via stdlib `sqlite3`; local file path defaults to `data/inbox_agent.db` (`core/db.py`, `core/config.py`, `.env.example`).
- Schema management: startup-time DDL + additive migrations in code (`core/db.py`).
- Persistent runtime artifacts: generated outputs under `runs/` (`agents/inbox/agent.py`, `core/config.py`).

## AI/Document Processing Toolchain
- JD and draft generation: OpenRouter-backed chat completions through OpenAI SDK wrapper (`core/llm.py`, `agents/inbox/agent.py`, `agents/inbox/drafts.py`).
- OCR: `pytesseract` + `Pillow` (`agents/inbox/ocr.py`, dependencies in `pyproject.toml`).
- PDF reading/parsing: `pypdf` for page count checks (`agents/inbox/resume.py`, dependency in `pyproject.toml`).
- Resume compile path: external `pdflatex` binary invoked via `subprocess` (`agents/inbox/resume.py`).
- OCR system binary dependency: local Tesseract installation required by runtime (`agents/inbox/ocr.py`).

## External-Service SDK Dependencies in Stack
- Google API client stack: `google-api-python-client`, `google-auth-httplib2`, `google-auth-oauthlib` (`integrations/drive.py`, `integrations/calendar.py`, `pyproject.toml`).

## Testing and Dev Tooling
- Test framework: pytest with asyncio auto mode (`pyproject.toml`, `tests/`).
- Async/API test helper: `pytest-asyncio`, `httpx` (`pyproject.toml`, e.g. `tests/test_health.py`, `tests/test_webhook_api_e2e.py`).
- Developer scripts: runtime diagnostics and webhook restart helpers (`scripts/check_runtime.sh`, `scripts/restart_webhook.sh`).

## Build, Packaging, and Execution Entry Points
- Build backend: setuptools (`pyproject.toml`).
- Package discovery includes `core*`, `agents*`, `integrations*`, `evals*` (`pyproject.toml`).
- Operational CLI entry by subcommand: `main.py` (`webhook`, `init-db`, `ci-gate`, `db-stats`, `followup-runner`).
- Deployment shape: long-running webhook API process plus optional scheduled follow-up runner (`main.py`, `agents/followup/runner.py`).

## Configuration Surface
- Source of truth: `.env` loaded from repo root into immutable `Settings` dataclass (`core/config.py`, `.env.example`).
- Key config domains:
  - LLM provider/model/fallbacks: `OPENROUTER_API_KEY`, `LLM_MODEL`, `LLM_FALLBACK_MODELS` (`core/config.py`, `.env.example`).
  - Webhook runtime: `TELEGRAM_WEBHOOK_SECRET`, `TELEGRAM_WEBHOOK_PATH`, `WEBHOOK_HOST`, `WEBHOOK_PORT`, `WEBHOOK_PROCESS_TIMEOUT_SECONDS` (`core/config.py`, `.env.example`).
  - Optional feature flags: `TELEGRAM_ENABLE_DRIVE_UPLOAD`, `TELEGRAM_ENABLE_CALENDAR_EVENTS` (`core/config.py`, `.env.example`).
  - Data paths and limits: `DB_PATH`, `GOOGLE_CREDENTIALS_PATH`, OCR thresholds, and cost cap (`core/config.py`, `.env.example`).

## Non-Obvious/Operational Notes
- Runtime is intentionally webhook-only; polling path is not part of active architecture (`README.md`, `docs/webhook-service-instructions.md`).
- Some tooling scripts/docs reference Python 3.11+, while package metadata allows 3.9+; effective compatibility should be validated in CI (`docs/webhook-service.md`, `pyproject.toml`, `docs/setup-and-test.md`).
