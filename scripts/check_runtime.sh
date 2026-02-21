#!/usr/bin/env bash

set -u

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ -f ".env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

PORT="${1:-${WEBHOOK_PORT:-8000}}"
PY_BIN="./.venv/bin/python"
if [[ ! -x "$PY_BIN" ]]; then
  PY_BIN="python3"
fi

section() {
  echo
  echo "=== $1 ==="
}

redact_secrets() {
  sed -E 's#bot[0-9]+:[A-Za-z0-9_-]+#bot<REDACTED>#g'
}

section "Runtime Check"
echo "repo: $ROOT_DIR"
echo "port: $PORT"
echo "python: $PY_BIN"

section "Listener"
if command -v lsof >/dev/null 2>&1; then
  if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN; then
    :
  else
    echo "No process is listening on port $PORT."
  fi
else
  echo "lsof not found; skipping port-listener check."
fi

section "Health Endpoint"
if command -v curl >/dev/null 2>&1; then
  health_body="$(curl -sS --max-time 3 "http://127.0.0.1:${PORT}/health" 2>/dev/null || true)"
  if [[ "$health_body" == *'"status":"ok"'* ]]; then
    echo "Health OK: $health_body"
  else
    echo "Health check did not return expected response."
    [[ -n "$health_body" ]] && echo "Response: $health_body"
  fi
else
  echo "curl not found; skipping health check."
fi

section "Process PID File"
if [[ -f runs/webhook.pid ]]; then
  pid="$(cat runs/webhook.pid)"
  echo "runs/webhook.pid: $pid"
  if kill -0 "$pid" 2>/dev/null; then
    echo "PID $pid is running."
  else
    echo "PID $pid is not running."
  fi
else
  echo "No runs/webhook.pid found."
fi

section "Recent Webhook Logs"
if [[ -f runs/webhook.log ]]; then
  tail -n 60 runs/webhook.log | redact_secrets
else
  echo "No runs/webhook.log found."
fi

section "Telegram Webhook Info"
if [[ -n "${TELEGRAM_TOKEN:-}" ]]; then
  curl -sS "https://api.telegram.org/bot${TELEGRAM_TOKEN}/getWebhookInfo" | redact_secrets || true
  echo
else
  echo "TELEGRAM_TOKEN missing; skipping getWebhookInfo."
fi

section "Database Stats"
"$PY_BIN" main.py db-stats || true

section "CI Gate"
if "$PY_BIN" main.py ci-gate; then
  echo "CI gate: PASS"
else
  echo "CI gate: FAIL"
fi
