# Job Search Agent

Webhook-first multi-agent system that turns job inputs (text, URL, screenshot) into tailored application packages.

## Where To Look

- Project overview and architecture: `docs/PROJECT_OVERVIEW.md`
- Operational runbook (setup, env, webhook, ops): `docs/RUNBOOK.md`
- Architectural decisions (ADR log): `docs/decisions.md`
- Current status and Linear mapping: `TRACKER.md`
- Short session handoff: `AGENT_HANDOFF.md`

## Quick Start

1. Create environment and install deps:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e ".[dev]"
```

2. Configure env:

```bash
cp .env.example .env
```

Required values:

- `OPENROUTER_API_KEY`
- `TELEGRAM_TOKEN`
- `TELEGRAM_WEBHOOK_SECRET`
- `PUBLIC_BASE_URL`
- `DATABASE_URL` (example: `postgresql://user:password@localhost:5432/inbox_agent`)

3. Initialize DB:

```bash
python main.py init-db
```

4. Start webhook:

```bash
python main.py webhook
```

5. Register webhook:

```bash
./set_webhook.sh
```

## Common Commands

- `python main.py webhook`
- `python main.py init-db`
- `python main.py ci-gate`
- `python main.py pipeline-check`
- `python main.py regression-run [--json] [--case <id>]`
- `python main.py runs [run_id] [--steps] [--limit N]`
- `python main.py db-stats`
- `python main.py eval-report [--json]`
- `python main.py feedback <run_id> --label <helpful|not_helpful> [--reason <text>]`
- `python main.py feedback-report [--days N]`
- `python main.py followup-runner [--once] [--dry-run] [--interval-minutes N]`
- `python main.py replay-webhook [options]`
- `python main.py build-skill-index`
- `python main.py auth-google`
- `python main.py encode-token`
- `.venv/bin/pytest -q -m "not live"`

See `docs/RUNBOOK.md` for the full operator workflow.
