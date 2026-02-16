# Job Search Agent

Webhook-first multi-agent system for job application automation.

## Current Runtime Mode

Telegram ingestion runs via **webhook service** (FastAPI). Polling is not used.

- Health endpoint: `GET /health`
- Webhook endpoint: `POST /telegram/webhook`

## Quick Start

1. Create environment and install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e ".[dev]"
```

2. Configure environment:

```bash
cp .env.example .env
```

Set at minimum:

- `OPENROUTER_API_KEY`
- `TELEGRAM_TOKEN`
- `TELEGRAM_WEBHOOK_SECRET`
- `PUBLIC_BASE_URL`

3. Initialize DB:

```bash
python main.py init-db
```

4. Start webhook server:

```bash
python main.py webhook
```

5. Register Telegram webhook:

```bash
./set_webhook.sh
```

## Commands

- `python main.py webhook` -> start Telegram webhook service
- `python main.py init-db` -> initialize SQLite DB
- `python main.py ci-gate` -> run CI eval gate
- `python main.py followup-runner --once` -> execute one follow-up detection/generation cycle
- `.venv/bin/pytest -q` -> run tests

## Documentation

- Full runbook: `docs/README.md`
- Webhook spec/status: `docs/webhook-service.md`
- Product requirements: `PRD.md`
- Current tracker: `TRACKER.md`
- Session handoff: `AGENT_HANDOFF.md`
