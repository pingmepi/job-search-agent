# Job Search Agent - Runbook

This document explains how to run the full `job-search-agent` project in webhook mode (no Telegram polling).

## 1) What This Project Does

The system ingests job descriptions from Telegram (text, URL, screenshot) and runs a pipeline:

1. Parse JD content
2. Select best base resume
3. Mutate editable LaTeX regions
4. Compile PDF resume
5. Generate outreach drafts
6. Log eval and telemetry data
7. Optionally upload PDF to Google Drive
8. Optionally create Google Calendar events

Primary runtime: FastAPI webhook service (`app.py`) + Telegram handlers (`agents/inbox/adapter.py`).

## 2) Prerequisites

Install these first:

- Python `>=3.9`
- `pdflatex` (for resume PDF compilation)
- Tesseract OCR binary (for screenshot OCR)

macOS (Homebrew):

```bash
brew install tesseract
brew install --cask mactex-no-gui
```

After installing MacTeX, make sure `pdflatex` is on PATH (restart terminal if needed).

## 3) Project Setup

From project root:

```bash
cd /Users/karan/Desktop/job-search-agent
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e ".[dev]"
```

## 4) Environment Configuration

Create local env file:

```bash
cp .env.example .env
```

Set required values:

```env
OPENROUTER_API_KEY=...
LLM_MODEL=google/gemma-2-9b-it:free
LLM_FALLBACK_MODELS=openai/gpt-4o-mini,meta-llama/llama-3.1-8b-instruct

TELEGRAM_TOKEN=...
TELEGRAM_BOT_USERNAME=@job_notes_bot
TELEGRAM_WEBHOOK_SECRET=<random-secret>
PUBLIC_BASE_URL=https://your-domain.com
TELEGRAM_WEBHOOK_PATH=/telegram/webhook
WEBHOOK_HOST=0.0.0.0
WEBHOOK_PORT=8000
WEBHOOK_PROCESS_TIMEOUT_SECONDS=10

GOOGLE_CREDENTIALS_PATH=credentials/google_oauth.json
MAX_COST_PER_JOB=0.15
DB_PATH=data/inbox_agent.db
```

Notes:

- `.env` is gitignored.
- `PUBLIC_BASE_URL` must be HTTPS for Telegram webhooks.

## 5) Initialize Database

```bash
python main.py init-db
```

## 6) Start Webhook Service (No Polling)

```bash
python main.py webhook
```

Equivalent:

```bash
uvicorn app:app --host 0.0.0.0 --port 8000
```

Exposed endpoints:

- `GET /health` -> `{"status":"ok"}`
- `POST /telegram/webhook` -> validates `X-Telegram-Bot-Api-Secret-Token` and processes updates

## 7) Register Telegram Webhook

Use included script:

```bash
./set_webhook.sh
```

Script behavior:

- Reads `.env` (`TELEGRAM_TOKEN`, `TELEGRAM_WEBHOOK_SECRET`, `PUBLIC_BASE_URL`)
- Calls Telegram `setWebhook`
- Sends `drop_pending_updates=true`
- Sends `secret_token`
- Prints `getWebhookInfo`

## 8) Local Testing With ngrok

1. Start app:

```bash
python main.py webhook
```

2. In a second terminal:

```bash
ngrok http 8000
```

3. Set `PUBLIC_BASE_URL` to the ngrok HTTPS URL in `.env`.
4. Re-run `./set_webhook.sh`.
5. Send messages to your bot and inspect logs.

## 9) Reverse Proxy Deployment

### Caddy example

```caddy
your-domain.com {
    reverse_proxy 127.0.0.1:8000
}
```

### Nginx example

```nginx
server {
    listen 443 ssl;
    server_name your-domain.com;

    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

## 10) Optional: Drive + Calendar Integrations

Telegram adapter behavior is env-controlled:

- `TELEGRAM_ENABLE_DRIVE_UPLOAD=true|false`
- `TELEGRAM_ENABLE_CALENDAR_EVENTS=true|false`

Defaults are disabled for safety.

## 11) Scheduled Follow-Up Runner

Run one cycle:

```bash
python main.py followup-runner --once
```

Run continuously (every hour by default):

```bash
python main.py followup-runner
```

Useful options:

```bash
python main.py followup-runner --dry-run --once
python main.py followup-runner --interval-minutes 30 --max-cycles 4
python main.py followup-runner --once --no-persist-progress
```

The runner logs telemetry into the `runs` table with `agent='followup_runner'`.

## 12) Tests

```bash
.venv/bin/pytest -q
```

Includes webhook auth/health + webhook E2E tests (`tests/test_health.py`, `tests/test_webhook_api_e2e.py`) and follow-up runner tests (`tests/test_followup_runner.py`).

## 13) Troubleshooting

`401 Invalid webhook secret`:

- Confirm `TELEGRAM_WEBHOOK_SECRET` matches the value used in `setWebhook`.

Webhook not receiving events:

- Verify `PUBLIC_BASE_URL` is HTTPS and publicly reachable.
- Run `./set_webhook.sh` again and inspect `getWebhookInfo` output.
- Check reverse-proxy routing to app port.

`500 TELEGRAM_WEBHOOK_SECRET is not configured`:

- Set `TELEGRAM_WEBHOOK_SECRET` in `.env` and restart service.

`pdflatex` not found:

- Install MacTeX and ensure `pdflatex` is on PATH.

`No endpoints found for <model>`:

- Your configured `LLM_MODEL` currently has no active OpenRouter endpoints.
- Set `LLM_FALLBACK_MODELS` in `.env` (comma-separated) so requests auto-retry on alternate models.
