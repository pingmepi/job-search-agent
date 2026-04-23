# Job Search Agent

Webhook-first multi-agent system for job application automation.

Each inbox pipeline run now produces:
- a tailored resume PDF
- optional outreach drafts
- a structured markdown application report with A-F sections
- a Google Drive folder containing the generated artifacts

Telegram-originated inbox submissions are treated as manually vetted job posts.
That signal is persisted on the `jobs` table as `user_vetted=1` so downstream
scanner/dashboard/integrity logic can distinguish user-approved intake from
other pipeline entry points.

## Deployment

Runs on **Railway** (Docker + managed PostgreSQL). The service is always-on — no local machine required.

- Platform: [railway.app](https://railway.app) — Docker container with Tesseract + minimal TexLive
- Database: Railway-managed PostgreSQL (`DATABASE_URL` auto-injected)
- Health endpoint: `GET /health`
- Webhook endpoint: `POST /telegram/webhook`

## Quick Start (local dev)

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
- `DATABASE_URL` — PostgreSQL connection string (e.g. `postgresql://localhost/inbox_agent`)

3. Initialize DB:

```bash
python main.py init-db
```

This command also applies schema migrations, including the `jobs.user_vetted`
column used for Telegram-vetted intake tracking.

4. Start webhook server:

```bash
python main.py webhook
```

5. Register Telegram webhook:

```bash
./set_webhook.sh
```

## Commands

- `python main.py webhook` — start Telegram webhook service
- `python main.py init-db` — create/migrate PostgreSQL tables
- `python main.py ci-gate` — run CI eval gate
- `python main.py db-stats` — show table counts and health
- `python main.py pipeline-check` — validate DB/artifact integrity, report presence, and follow-up drift
- `python main.py followup-runner --once` — execute one follow-up detection/generation cycle
- `pytest -q` — run tests (DB tests skip automatically if `DATABASE_URL` not set)

## Documentation

- Full runbook: `docs/README.md`
- Setup and test guide: `docs/setup-and-test.md`
- Webhook spec/status: `docs/webhook-service.md`
- Product requirements: `PRD.md`
- Current tracker: `TRACKER.md`
- Session handoff: `AGENT_HANDOFF.md`
