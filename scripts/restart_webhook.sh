#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ -f ".env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

PORT="${WEBHOOK_PORT:-8000}"
PID_FILE="runs/webhook.pid"
LOG_FILE="runs/webhook.log"
PY_BIN="./.venv/bin/python"

if [[ ! -x "$PY_BIN" ]]; then
  echo "ERROR: $PY_BIN not found. Activate/install the venv first." >&2
  exit 1
fi

mkdir -p runs

echo "Restarting webhook service on port $PORT"

if [[ -f "$PID_FILE" ]]; then
  OLD_PID="$(cat "$PID_FILE" || true)"
  if [[ -n "${OLD_PID:-}" ]] && kill -0 "$OLD_PID" 2>/dev/null; then
    echo "Stopping existing webhook pid: $OLD_PID"
    kill "$OLD_PID" 2>/dev/null || true
    sleep 1
  fi
  rm -f "$PID_FILE"
fi

# Clear any lingering listener on the target port to avoid bind conflicts.
if command -v lsof >/dev/null 2>&1; then
  PORT_PIDS="$(lsof -tiTCP:"$PORT" -sTCP:LISTEN || true)"
  if [[ -n "$PORT_PIDS" ]]; then
    echo "Stopping lingering listener(s) on port $PORT: $PORT_PIDS"
    # shellcheck disable=SC2086
    kill $PORT_PIDS 2>/dev/null || true
    sleep 1
  fi
fi

TEX_DIR="/Library/TeX/texbin"
if [[ -d "$TEX_DIR" ]]; then
  export PATH="$TEX_DIR:$PATH"
fi

echo "Starting webhook..."
/usr/bin/nohup "$PY_BIN" main.py webhook > "$LOG_FILE" 2>&1 &
NEW_PID=$!
echo "$NEW_PID" > "$PID_FILE"
sleep 2

if kill -0 "$NEW_PID" 2>/dev/null; then
  echo "Webhook started. pid=$NEW_PID"
  echo "Log file: $LOG_FILE"
else
  echo "Webhook failed to start. Recent logs:"
  tail -n 80 "$LOG_FILE" || true
  exit 1
fi

if command -v lsof >/dev/null 2>&1; then
  echo
  echo "Listener check:"
  lsof -nP -iTCP:"$PORT" -sTCP:LISTEN || true
fi
