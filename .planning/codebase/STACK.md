# Technology Stack

## Languages
- Python (primary language across runtime, agents, integrations, and tests).
- Bash (operational scripts such as webhook registration).

## Runtime and Packaging
- Python runtime: `>=3.9` (declared in `pyproject.toml`).
- Build backend: `setuptools.build_meta`.
- Package name: `inbox-agent`.
- Typical local runtime uses a virtualenv (`.venv`) and editable install (`pip install -e ".[dev]"`).

## Application Frameworks and Core Libraries
- FastAPI (`fastapi`) for HTTP webhook service.
- Uvicorn (`uvicorn`) as ASGI server.
- python-telegram-bot (`python-telegram-bot`) for Telegram bot update handling.
- OpenAI Python SDK (`openai`) used as an OpenRouter-compatible client.
- Pydantic (`pydantic`) for typed data modeling/validation in pipeline layers.
- python-dotenv (`python-dotenv`) for `.env` loading.

## Data, Documents, and Media Tooling
- SQLite (`sqlite3` from stdlib) as embedded persistence layer.
- OCR/image stack: `pytesseract`, `Pillow`.
- PDF stack: `pypdf`.

## Google Platform Dependencies
- `google-api-python-client`
- `google-auth-httplib2`
- `google-auth-oauthlib`

## Testing and Dev Dependencies
- `pytest`
- `pytest-asyncio`
- `httpx` (test/client usage)

## Project Configuration Surfaces
- `pyproject.toml`
  - Declares runtime, dependencies, package discovery, pytest settings.
- `.env` / `.env.example`
  - Central runtime config for API keys, webhook settings, feature flags, DB path, model routing.
- `core/config.py`
  - Canonical settings object (`Settings`) and env-to-runtime mapping.
- `main.py`
  - CLI entrypoints (`webhook`, `init-db`, `ci-gate`, `db-stats`, `followup-runner`).

## Runtime Modes and Processes
- Webhook-first service mode (no polling): FastAPI app in `app.py` exposes `/health` and Telegram webhook endpoint.
- Scheduled/background mode: follow-up runner via `python main.py followup-runner`.
- Local operations scripts under `scripts/` plus root `set_webhook.sh`.

## Persistence and State Layout
- Primary DB file defaults to `data/inbox_agent.db` (SQLite).
- Runtime artifacts/log-like state stored under `runs/`.
- Credentials expected under `credentials/` (Google OAuth client file + cached tokens).

## Notable Architecture Characteristics
- Monorepo-style single Python project with feature-oriented folders (`agents/`, `core/`, `integrations/`, `evals/`, `tests/`).
- Config-driven feature toggles for optional integrations (`TELEGRAM_ENABLE_DRIVE_UPLOAD`, `TELEGRAM_ENABLE_CALENDAR_EVENTS`).
- External LLM model routing handled via primary + fallback model list (`LLM_MODEL`, `LLM_FALLBACK_MODELS`).
