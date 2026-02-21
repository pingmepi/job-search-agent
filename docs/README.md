# Job Search Agent - Runbook

This document explains how to run the full `job-search-agent` project in webhook mode (no Telegram polling).

## Related Operational Docs

- Setup + staged test flow: `docs/setup-and-test.md`
- Troubleshooting + issue log: `docs/troubleshooting-and-debugging.md`

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
LLM_MODEL=stepfun/step-3.5-flash:free
LLM_FALLBACK_MODELS=qwen/qwen3-coder:free,meta-llama/llama-3.2-3b-instruct:free,meta-llama/llama-3.3-70b-instruct:free,mistralai/mistral-small-3.1-24b-instruct:free,deepseek/deepseek-r1-0528:free,openai/gpt-oss-120b:free,arcee-ai/trinity-mini:free

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

## 6b) Service Logs and Verification

If running in foreground (`python main.py webhook`), logs print directly in that terminal.

One-command runtime snapshot:

```bash
./scripts/check_runtime.sh
```

One-command webhook restart:

```bash
./scripts/restart_webhook.sh
```

Useful checks from another terminal:

```bash
curl -sS http://127.0.0.1:8000/health
lsof -nP -iTCP:8000 -sTCP:LISTEN
```

Optional background run with file logs:

```bash
mkdir -p runs
nohup ./.venv/bin/python main.py webhook > runs/webhook.log 2>&1 &
echo $! > runs/webhook.pid
tail -f runs/webhook.log
```

Process checks:

```bash
ps -fp "$(cat runs/webhook.pid)"
tail -n 100 runs/webhook.log
```

If startup fails with `address already in use`:

```bash
lsof -tiTCP:8000 -sTCP:LISTEN
kill <PID>
sleep 1
lsof -nP -iTCP:8000 -sTCP:LISTEN
```

Then restart webhook:

```bash
nohup ./.venv/bin/python main.py webhook > runs/webhook.log 2>&1 &
echo $! > runs/webhook.pid
```

Webhook registration verification:

```bash
./set_webhook.sh
```

Expected: `Webhook info` output includes your configured `PUBLIC_BASE_URL`.

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

## 8) Primary URL Flow (Recommended)

Use your fixed domain from `.env` (example: `https://bot.merekapade.com`).

1. Set `PUBLIC_BASE_URL` in `.env` to your fixed HTTPS domain.
2. Start app:

```bash
python main.py webhook
```

3. Register webhook:

```bash
./set_webhook.sh
```

4. Confirm output shows:

```text
Setting webhook to: https://<your-fixed-domain>/telegram/webhook
```

## 8b) Backup: Quick Cloudflare Tunnel (Temporary)

Use only when your fixed domain route is unavailable.

1. Start app:

```bash
python main.py webhook
```

2. Start temporary tunnel in another terminal:

```bash
cloudflared tunnel --url http://localhost:8000
```

3. Copy the shown `https://<random>.trycloudflare.com` URL and set it as `PUBLIC_BASE_URL` in `.env`.
4. Run `./set_webhook.sh` again.
5. Keep the `cloudflared` process running; when it stops, webhook delivery stops.

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

Operational check shortcut:

- `./scripts/check_runtime.sh` -> listener, health, log tail, Telegram webhook info, DB stats, CI gate

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

`[Errno 48] ... address already in use`:

- Cause: another process already listens on `WEBHOOK_PORT` (default `8000`).
- Fix: identify and stop the existing listener (`lsof ...`, `kill <pid>`), then restart webhook.

Webhook retries then fails after ~30s:

- Cause: pipeline work exceeded webhook processing timeout and retried 3 times.
- Fix: increase `WEBHOOK_PROCESS_TIMEOUT_SECONDS` in `.env` (example `45`) and reduce slow/failing model retries by setting stable `LLM_MODEL` + `LLM_FALLBACK_MODELS`.
