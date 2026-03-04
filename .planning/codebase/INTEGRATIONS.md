# INTEGRATIONS

## Overview
This repository integrates with messaging, LLM, Google Workspace, and arbitrary job-posting web pages. Integration wiring is primarily in `app.py`, `agents/inbox/adapter.py`, `core/llm.py`, and `integrations/*.py`.

## External APIs

### Telegram Bot API
- Purpose: inbound user messages via webhook and bot responses.
- Inbound webhook endpoint: `POST /telegram/webhook` implemented in `app.py`.
- SDK usage: `python-telegram-bot` application processes updates and sends chat responses (`agents/inbox/adapter.py`, `app.py`).
- Webhook registration call: `setWebhook` + `getWebhookInfo` via `curl` in `set_webhook.sh`.
- Required secrets/config: `TELEGRAM_TOKEN`, `TELEGRAM_WEBHOOK_SECRET`, `PUBLIC_BASE_URL` (`.env.example`, `core/config.py`, `set_webhook.sh`).

### OpenRouter (through OpenAI-compatible client)
- Purpose: JD extraction, OCR cleanup, resume mutation/condensing, draft generation, soft eval scoring.
- API client: OpenAI SDK configured with OpenRouter base URL (`core/llm.py`).
- Endpoints used:
  - Chat completions via `client.chat.completions.create(...)` (`core/llm.py`).
  - Cost resolution via OpenRouter generation lookup `GET /generation?id=...` (`core/llm.py`).
- Required secrets/config: `OPENROUTER_API_KEY`, `LLM_MODEL`, `LLM_FALLBACK_MODELS` (`.env.example`, `core/config.py`).

### Google Drive API (Optional)
- Purpose: upload generated resume PDFs to Drive folder hierarchy.
- Integration module: `integrations/drive.py`.
- Scope: `https://www.googleapis.com/auth/drive.file`.
- Token persistence: `drive_token.pickle` beside credentials file (`integrations/drive.py`).
- Feature flag: `TELEGRAM_ENABLE_DRIVE_UPLOAD` (`core/config.py`, `.env.example`).

### Google Calendar API (Optional)
- Purpose: create applied/follow-up calendar events.
- Integration module: `integrations/calendar.py`.
- Scope: `https://www.googleapis.com/auth/calendar.events`.
- Token persistence: `calendar_token.pickle` beside credentials file (`integrations/calendar.py`).
- Feature flag: `TELEGRAM_ENABLE_CALENDAR_EVENTS` (`core/config.py`, `.env.example`).

### Arbitrary Job URL Fetching
- Purpose: ingest job-posting content from user-provided links.
- Implementation: HTTP(S) fetch using stdlib `urllib.request` in `agents/inbox/url_ingest.py`.
- Network behavior: direct outbound GET with browser-like User-Agent; no site-specific API adapters.

## Databases and Storage

### SQLite (Primary Data Store)
- Engine: local SQLite via stdlib `sqlite3` (`core/db.py`).
- File location: `data/inbox_agent.db` by default, configurable via `DB_PATH` (`core/config.py`, `.env.example`).
- Tables: `jobs`, `runs` with additive migration logic (`core/db.py`).

### File-Based State/Artifacts
- Runtime outputs: artifacts and logs in `runs/` (`agents/inbox/agent.py`, `scripts/check_runtime.sh`).
- Profile inputs: local JSON profile/bullet bank (`profile/profile.json`, `profile/bullet_bank.json`, `core/config.py`).
- Credentials/tokens: local OAuth client JSON and pickle token files (`credentials/`, `integrations/drive.py`, `integrations/calendar.py`).

## Authentication and Authorization

### Telegram Webhook Verification
- Mechanism: shared-secret header `X-Telegram-Bot-Api-Secret-Token` checked per request (`app.py`).
- Failure behavior:
  - Invalid header value -> `401`.
  - Missing/misconfigured expected secret -> `500`.

### OpenRouter API Key
- Mechanism: bearer key in OpenAI client config (`core/llm.py`, `core/config.py`).
- No user-level OAuth; single application credential model.

### Google OAuth (Installed App Flow)
- Mechanism: interactive OAuth flow via `InstalledAppFlow.run_local_server(...)` (`integrations/drive.py`, `integrations/calendar.py`).
- Refresh behavior: refresh token reuse when available (`integrations/drive.py`, `integrations/calendar.py`).

## Webhooks and Event Flows

### Inbound Webhooks
- Telegram -> app webhook:
  - Endpoint: configurable path defaulting to `/telegram/webhook` (`app.py`, `core/config.py`, `.env.example`).
  - Processing: update de-duplication + retry/timeout handling in webhook runtime (`app.py`).

### Outbound Webhook Configuration
- App operator -> Telegram API:
  - Scripted registration via `set_webhook.sh`.
  - Passes `secret_token` and `drop_pending_updates=true`.

## Integration Control Flags and Safety
- Optional integrations are explicitly toggled at runtime (`TELEGRAM_ENABLE_DRIVE_UPLOAD`, `TELEGRAM_ENABLE_CALENDAR_EVENTS`) (`core/config.py`, `.env.example`, `agents/inbox/adapter.py`).
- Pipeline degrades gracefully: Drive/Calendar failures are captured in `ApplicationPack.errors` without hard-failing the full processing flow (`agents/inbox/agent.py`).

## Current Gaps/Constraints (Integration View)
- No external queue/event bus integration; webhook handler processes updates inline (`app.py`).
- No first-party user authentication layer for API endpoints beyond Telegram webhook secret (`app.py`).
- OAuth token storage is file-based pickle in local filesystem, which is simple but not centralized secret management (`integrations/drive.py`, `integrations/calendar.py`).
