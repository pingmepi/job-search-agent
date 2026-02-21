# Setup, Run, and Test Guide

Purpose: canonical command flow to get the app running and validate it end-to-end.

## Stage 1: Environment Setup

Run from repo root:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e ".[dev]"
```

Expected output:

- `pip` completes without dependency resolution errors.
- Editable install succeeds for package `inbox-agent`.

Quick validation:

```bash
python3 --version
./.venv/bin/python --version
```

Sample output in this repo:

```text
Python 3.9.6
Python 3.9.6
```

## Stage 2: Configure Environment Variables

```bash
cp .env.example .env
```

Minimum required for webhook runtime:

- `OPENROUTER_API_KEY`
- `TELEGRAM_TOKEN`
- `TELEGRAM_WEBHOOK_SECRET`
- `PUBLIC_BASE_URL`

Notes:

- `PUBLIC_BASE_URL` must be public HTTPS for Telegram webhook delivery.
- Use your fixed tunnel/domain URL as the default value.
- Keep `.env` local only (already gitignored).

## Stage 3: Initialize Database

```bash
./.venv/bin/python main.py init-db
```

Expected output:

```text
✅ Database initialized at /Users/karan/Desktop/job-search-agent/data/inbox_agent.db
```

## Stage 4: Baseline Test Suite (Fast Signal)

```bash
./.venv/bin/pytest -q tests/test_health.py tests/test_webhook_retries.py tests/test_followup_runner.py
```

Expected output pattern:

```text
........                                                                 [100%]
8 passed in <time>s
```

Sample run from current branch:

```text
........                                                                 [100%]
8 passed in 1.16s
```

## Stage 5: Runtime Data Sanity Check

```bash
./.venv/bin/python main.py db-stats
```

Expected output pattern:

```text
DB: <absolute-db-path>
Jobs: total=<n> applied=<n> follow_up_zero=<n> fit_score_nulls=<n> drive_link_empty=<n>
Runs: total=<n> completed=<n> tokens_nulls=<n> latency_nulls=<n> with_errors=<n>
Compile: success=<n> failure=<n>
```

## Stage 6: Run Webhook Server

```bash
./.venv/bin/python main.py webhook
```

Expected output pattern:

- Uvicorn startup logs with host/port from `.env` (defaults `0.0.0.0:8000`)
- No immediate crash during app startup

Health check in another terminal:

```bash
curl -sS http://127.0.0.1:8000/health
```

Expected response:

```json
{"status":"ok"}
```

Log verification:

- When running in foreground, webhook logs appear in the same terminal.
- Look for lines containing `Webhook request received` and `Webhook update processed`.

Optional background log capture:

```bash
mkdir -p runs
nohup ./.venv/bin/python main.py webhook > runs/webhook.log 2>&1 &
echo $! > runs/webhook.pid
tail -f runs/webhook.log
```

Process and port checks:

```bash
ps -fp "$(cat runs/webhook.pid)"
lsof -nP -iTCP:8000 -sTCP:LISTEN
```

If you see `address already in use` on startup:

```bash
lsof -tiTCP:8000 -sTCP:LISTEN
kill <PID>
sleep 1
lsof -nP -iTCP:8000 -sTCP:LISTEN
```

If `runs/webhook.pid` points to a dead process, clear it before restarting:

```bash
rm -f runs/webhook.pid
```

## Stage 7: Register Telegram Webhook

```bash
./set_webhook.sh
```

Expected output pattern:

```text
Setting webhook to: https://<your-domain>/telegram/webhook
{"ok":true,"result":true,"description":"Webhook was set"}
Webhook info:
{"ok":true,"result":{...}}
```

Important:

- `set_webhook.sh` reads `PUBLIC_BASE_URL` from `.env`.
- You do not need to run `cloudflared tunnel --url ...` if your fixed domain route is already active.
- Use quick Cloudflare tunnel only as a temporary backup URL.
- `set_webhook.sh` output is the source of truth for current webhook URL and status.
- If message processing retries/timeouts occur, increase `WEBHOOK_PROCESS_TIMEOUT_SECONDS` (for example: `45`) and prefer stable `LLM_MODEL`/fallback values.

If the script fails early, it will usually print:

- `TELEGRAM_TOKEN is required`
- `TELEGRAM_WEBHOOK_SECRET is required`
- `PUBLIC_BASE_URL is required`

## Stage 8: Optional Smoke Checks

Invalid secret should return `401`:

```bash
curl -i -X POST http://127.0.0.1:8000/telegram/webhook \
  -H "Content-Type: application/json" \
  -H "X-Telegram-Bot-Api-Secret-Token: wrong-secret" \
  -d '{"update_id":12345}'
```

Expected status: `401 Unauthorized`.

## Fast Command Reference

- Start webhook server: `./.venv/bin/python main.py webhook`
- Init DB: `./.venv/bin/python main.py init-db`
- DB stats: `./.venv/bin/python main.py db-stats`
- CI gate: `./.venv/bin/python main.py ci-gate`
- Run follow-up cycle once: `./.venv/bin/python main.py followup-runner --once`
- Run all tests: `./.venv/bin/pytest -q`
- Runtime snapshot (logs + health + webhook info): `./scripts/check_runtime.sh`
