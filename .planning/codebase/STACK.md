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
- PostgreSQL via `psycopg2-binary` as persistence layer (replaces SQLite).
- OCR/image stack: `pytesseract`, `Pillow`.
- PDF stack: `pypdf`.

## Google Platform Dependencies
- `google-api-python-client`
- `google-auth-httplib2`
- `google-auth-oauthlib`

## Deployment
- **Platform**: Railway (Docker container + managed PostgreSQL plugin).
- **Container**: `Dockerfile` using `python:3.11-slim` + Tesseract + minimal TexLive (`texlive-latex-base`, `texlive-latex-extra`, `texlive-fonts-recommended` — ~400MB vs ~3GB full install).
- **Orchestration**: `railway.json` with `/health` healthcheck and ON_FAILURE restart policy.

### Why Railway over alternatives
| Considered | Decision | Reason rejected/chosen |
|---|---|---|
| Vercel | Rejected | No Tesseract system binary, no pdflatex, ephemeral FS (no SQLite), cold-start kills webhook latency |
| Mac + launchd | Rejected | Requires machine to stay on; not cloud-hosted |
| Railway | **Chosen** | Supports arbitrary system deps via Docker, managed Postgres, always-on, handles future multi-user SaaS |

### Why PostgreSQL over SQLite
- SQLite serialises all writes → deadlocks under concurrent users when productizing to multi-user SaaS.
- Railway's managed Postgres plugin auto-injects `DATABASE_URL`, making migration low-effort at single-user stage rather than painful later with real data.
- `psycopg2-binary` chosen (over `psycopg2`) — binary wheel requires no `libpq-dev`/`gcc` build tools in Docker.

## Testing and Dev Dependencies
- `pytest`
- `pytest-asyncio`
- `httpx` (test/client usage)
- `psycopg2-binary` (also used at test time — tests hit real PostgreSQL, not mocks)

## Project Configuration Surfaces
- `pyproject.toml`
  - Declares runtime, dependencies, package discovery, pytest settings.
- `.env` / `.env.example`
  - Central runtime config for API keys, webhook settings, feature flags, `DATABASE_URL`, model routing.
- `core/config.py`
  - Canonical settings object (`Settings`) and env-to-runtime mapping.
- `main.py`
  - CLI entrypoints (`webhook`, `init-db`, `ci-gate`, `db-stats`, `followup-runner`).

## Runtime Modes and Processes
- Webhook-first service mode (no polling): FastAPI app in `app.py` exposes `/health` and Telegram webhook endpoint.
- Scheduled/background mode: follow-up runner via `python main.py followup-runner`.
- Local operations scripts under `scripts/` plus root `set_webhook.sh`.

## Persistence and State Layout
- Primary database: PostgreSQL via `DATABASE_URL` env var (managed by Railway in production).
- Runtime artifacts stored under `runs/` (ephemeral in Railway — PDFs are already sent to Telegram, DB holds all durable telemetry).
- Credentials expected under `credentials/` (Google OAuth client file + cached tokens).

## Notable Architecture Characteristics
- Monorepo-style single Python project with feature-oriented folders (`agents/`, `core/`, `integrations/`, `evals/`, `tests/`).
- Config-driven feature toggles for optional integrations (`TELEGRAM_ENABLE_DRIVE_UPLOAD`, `TELEGRAM_ENABLE_CALENDAR_EVENTS`).
- External LLM model routing handled via primary + fallback model list (`LLM_MODEL`, `LLM_FALLBACK_MODELS`).
