#!/usr/bin/env bash
set -euo pipefail

if [[ -f ".env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

: "${TELEGRAM_TOKEN:?TELEGRAM_TOKEN is required}"
: "${TELEGRAM_WEBHOOK_SECRET:?TELEGRAM_WEBHOOK_SECRET is required}"
: "${PUBLIC_BASE_URL:?PUBLIC_BASE_URL is required}"

WEBHOOK_PATH="${TELEGRAM_WEBHOOK_PATH:-/telegram/webhook}"
WEBHOOK_URL="${PUBLIC_BASE_URL%/}${WEBHOOK_PATH}"

echo "Setting webhook to: ${WEBHOOK_URL}"
curl -sS -X POST "https://api.telegram.org/bot${TELEGRAM_TOKEN}/setWebhook" \
  --data-urlencode "url=${WEBHOOK_URL}" \
  --data-urlencode "secret_token=${TELEGRAM_WEBHOOK_SECRET}" \
  --data-urlencode "drop_pending_updates=true"
echo

echo "Webhook info:"
curl -sS "https://api.telegram.org/bot${TELEGRAM_TOKEN}/getWebhookInfo"
echo
