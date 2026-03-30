# External Integrations

## External APIs

### OpenRouter (LLM Inference and Cost Metadata)
- Purpose: chat completion inference for extraction/drafting pipeline steps.
- Client path: `core/llm.py` using OpenAI SDK with `base_url` set to OpenRouter.
- Base URL: `https://openrouter.ai/api/v1`.
- Auth: bearer API key from `OPENROUTER_API_KEY`.
- Extra endpoint usage: generation cost lookup via `GET /generation?id=<generation_id>`.
- Failover behavior: configurable fallback model list via `LLM_FALLBACK_MODELS`.

### Telegram Bot API
- Purpose: inbound job ingestion and bot messaging.
- Inbound webhook receiver: FastAPI route in `app.py` (`POST /telegram/webhook` by default).
- Outbound registration/inspection: `set_webhook.sh` calls:
  - `POST https://api.telegram.org/bot<TOKEN>/setWebhook`
  - `GET https://api.telegram.org/bot<TOKEN>/getWebhookInfo`
- Runtime bot operations are handled through `python-telegram-bot` adapter code.

### Google Drive API
- Purpose: optional upload of generated application artifacts.
- Implementation: `integrations/drive.py` via Google API client (`drive v3`).
- Scope: `https://www.googleapis.com/auth/drive.file`.
- Behavior: creates/uses folder hierarchy `Jobs/{Company}/{Role}/`, uploads PDF, returns share link.

### Google Calendar API
- Purpose: optional calendar event creation for apply/follow-up workflow.
- Implementation: `integrations/calendar.py` via Google API client (`calendar v3`).
- Scope: `https://www.googleapis.com/auth/calendar.events`.
- Behavior: inserts 2 events on primary calendar (applied date and follow-up date).

## Databases and Storage
- Primary datastore: SQLite database (`data/inbox_agent.db` by default).
- Access layer: `core/db.py` using stdlib `sqlite3` with lightweight migration logic.
- Main tables:
  - `jobs` (application records, fit score, Drive link, follow-up metadata)
  - `runs` (agent run telemetry, token/cost/latency/error context)
- File storage:
  - `runs/` for runtime outputs/logs.
  - `resumes/`, `profile/`, `core/prompts/` for local domain assets.

## Authentication and Authorization

### OpenRouter
- Auth mechanism: API key bearer token (`OPENROUTER_API_KEY`).

### Telegram Webhook Verification
- Auth/validation mechanism: secret header check.
- Header: `X-Telegram-Bot-Api-Secret-Token`.
- Config key: `TELEGRAM_WEBHOOK_SECRET`.
- Behavior: webhook requests are rejected with `401` if secret mismatch.

### Google OAuth
- Auth mechanism: OAuth client credentials + token refresh flow.
- Credentials file path: `GOOGLE_CREDENTIALS_PATH` (default `credentials/google_oauth.json`).
- Token cache files:
  - `credentials/drive_token.pickle`
  - `credentials/calendar_token.pickle`

## Webhooks and Event Interfaces
- Inbound webhook provider: Telegram.
- Endpoint path: configurable via `TELEGRAM_WEBHOOK_PATH` (default `/telegram/webhook`).
- Host/port binding: `WEBHOOK_HOST` and `WEBHOOK_PORT`.
- Processing timeout: `WEBHOOK_PROCESS_TIMEOUT_SECONDS`.
- Delivery semantics in app logic:
  - validates secret header before processing.
  - deduplicates `update_id` to avoid duplicate execution.
  - retries failed processing up to 3 attempts before user notification.

## Integration Feature Flags and Operational Controls
- `TELEGRAM_ENABLE_DRIVE_UPLOAD` toggles Drive upload integration.
- `TELEGRAM_ENABLE_CALENDAR_EVENTS` toggles Calendar event integration.
- `PUBLIC_BASE_URL` controls external webhook URL registration target.
