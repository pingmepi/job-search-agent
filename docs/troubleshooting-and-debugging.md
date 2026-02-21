# Troubleshooting, Debugging, and Issue Log

Purpose: living operations doc for humans and agents investigating runtime/test failures.

## How To Use This Doc

- Check `Quick Triage` first.
- Run `Debug Command Pack`.
- If a new issue is found, append it to `Issue Log`.
- Keep fixes minimal and verifiable; include exact command evidence.

## Quick Triage

1. Confirm branch and clean state:

```bash
git status -sb
git branch -vv
```

2. Confirm env and interpreter:

```bash
./.venv/bin/python --version
test -f .env && echo ".env present" || echo ".env missing"
```

3. Confirm baseline tests:

```bash
./.venv/bin/pytest -q tests/test_health.py tests/test_webhook_retries.py tests/test_followup_runner.py
```

4. Confirm DB and stats:

```bash
./.venv/bin/python main.py init-db
./.venv/bin/python main.py db-stats
```

5. Confirm webhook app health:

```bash
curl -sS http://127.0.0.1:8000/health
```

## Common Errors and Quick Fixes

`401 Invalid webhook secret token`

- Cause: `X-Telegram-Bot-Api-Secret-Token` does not match `TELEGRAM_WEBHOOK_SECRET`.
- Fix: align `.env` + `set_webhook.sh` registration secret, then re-register webhook.

`500 TELEGRAM_WEBHOOK_SECRET is not configured.`

- Cause: missing/placeholder `TELEGRAM_WEBHOOK_SECRET`.
- Fix: set real secret in `.env`, restart service.

`TELEGRAM_TOKEN is required` (from `set_webhook.sh`)

- Cause: missing token in environment.
- Fix: set `TELEGRAM_TOKEN` in `.env`, re-run script.

`No endpoints found for <model>`

- Cause: selected OpenRouter model is unavailable.
- Fix: set `LLM_FALLBACK_MODELS` in `.env` (comma-separated), rerun flow/tests.

`pdflatex` not found

- Cause: LaTeX toolchain missing from PATH.
- Fix: install MacTeX and confirm `pdflatex --version`.

Webhook not receiving Telegram updates

- Cause: non-HTTPS or unreachable `PUBLIC_BASE_URL`, proxy misroute, or stale webhook config.
- Fix: verify endpoint reachability, re-run `./set_webhook.sh`, inspect `getWebhookInfo` response.

`I ran cloudflared quick tunnel, but webhook still points to fixed domain`

- Cause: quick tunnel command does not update Telegram webhook automatically.
- Fix: update `PUBLIC_BASE_URL` in `.env` to desired URL and re-run `./set_webhook.sh`.

`Do I need cloudflared running all the time?`

- Answer: only if your active webhook URL depends on that local quick tunnel process.
- If using a stable fixed domain route, quick tunnel is optional backup only.

`[Errno 48] error while attempting to bind ... address already in use`

- Cause: another process already owns webhook port `8000` (or configured `WEBHOOK_PORT`).
- Fix:

```bash
lsof -tiTCP:8000 -sTCP:LISTEN
kill <PID>
sleep 1
lsof -nP -iTCP:8000 -sTCP:LISTEN
```

`runs/webhook.pid` exists but process is not running

- Cause: stale PID file from failed startup.
- Fix:

```bash
rm -f runs/webhook.pid
```

`Webhook update failed after retries` with high latency

- Cause: processing timed out before pipeline finished.
- Fix:
  - Increase `WEBHOOK_PROCESS_TIMEOUT_SECONDS` (example `45`).
  - Use stable `LLM_MODEL` and smaller fallback set to reduce repeated `404` retry overhead.
  - Restart webhook service after `.env` changes.

## Debug Command Pack

Use this exact sequence for incident triage:

```bash
./.venv/bin/python main.py init-db
./.venv/bin/python main.py db-stats
./.venv/bin/pytest -q
./.venv/bin/python main.py followup-runner --dry-run --once
```

Or run the consolidated check script:

```bash
./scripts/check_runtime.sh
```

Service log checks:

```bash
tail -n 100 runs/webhook.log
tail -f runs/webhook.log
ps -fp "$(cat runs/webhook.pid)"
lsof -nP -iTCP:8000 -sTCP:LISTEN
```

If running webhook in foreground instead of background, inspect the active terminal output directly.

If webhook server is running:

```bash
curl -i http://127.0.0.1:8000/health
curl -i -X POST http://127.0.0.1:8000/telegram/webhook \
  -H "Content-Type: application/json" \
  -H "X-Telegram-Bot-Api-Secret-Token: wrong-secret" \
  -d '{"update_id":12345}'
```

Expected:

- `/health` returns HTTP `200` with `{"status":"ok"}`
- invalid secret returns HTTP `401`

Telegram-side verification:

```bash
./set_webhook.sh
```

Check `Webhook info` output for:

- expected `url`
- `pending_update_count`
- non-error response (`"ok": true`)

## Issue Log (Living Section)

Append newest entries at the top.

### Template

```md
#### [YYYY-MM-DD] <short title>
- Reporter: <name/agent>
- Branch/commit: <branch> / <sha>
- Symptom: <what failed>
- Repro command: `<exact command>`
- Observed output: `<key error text>`
- Root cause: <confirmed or suspected>
- Fix: <what changed>
- Verification: `<test/command proving fix>`
- Follow-up action: <optional hardening/test/docs>
```

### Current Known Items

#### [2026-02-21] Webhook secret mismatch returns 401 by design
- Reporter: Codex
- Branch/commit: `main` / `a97e997`
- Symptom: webhook POST rejected with unauthorized status.
- Repro command: `curl -i -X POST http://127.0.0.1:8000/telegram/webhook -H "X-Telegram-Bot-Api-Secret-Token: wrong-secret" -d '{"update_id":12345}'`
- Observed output: HTTP `401`.
- Root cause: header does not match configured secret.
- Fix: set correct `TELEGRAM_WEBHOOK_SECRET` and re-register webhook.
- Verification: webhook requests with matching secret are accepted.
- Follow-up action: keep secret rotation notes in deployment docs.

#### [2026-02-21] Model endpoint unavailability requires fallback
- Reporter: Codex
- Branch/commit: `main` / `a97e997`
- Symptom: LLM call fails when primary model has no active endpoint.
- Repro command: covered by `tests/test_llm.py`.
- Observed output: `No endpoints found for ...`.
- Root cause: model availability drift on provider side.
- Fix: configure `LLM_FALLBACK_MODELS` and keep at least one stable fallback.
- Verification: fallback behavior test passes.
- Follow-up action: add periodic check for active model availability.

#### [2026-02-21] Port `8000` bind conflicts caused repeated webhook startup failures
- Reporter: Codex
- Branch/commit: `main` / working tree (uncommitted docs)
- Symptom: `ERROR: [Errno 48] ... address already in use`
- Repro command: `./.venv/bin/python main.py webhook`
- Observed output: bind failure followed by immediate shutdown.
- Root cause: existing Python listener was already bound to `*:8000`.
- Fix: identify listener with `lsof -tiTCP:8000 -sTCP:LISTEN`, stop process, clear stale `runs/webhook.pid`, restart webhook.
- Verification: `/health` returns `200` and webhook updates are received from Telegram IPs.
- Follow-up action: use `./scripts/check_runtime.sh` before restarts to catch port/PID issues early.

## Best Practices

- Prefer deterministic, low-latency tests first (`test_health`, `test_webhook_retries`, `test_followup_runner`).
- Keep `.env` aligned with deployment secrets before webhook registration.
- Always record exact failing command and first error line before changing code.
- Validate fixes with both a targeted test and one broader regression command.
- Update this document when any new class of failure appears.
