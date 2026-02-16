# Telegram Webhook Service Specification (Implemented)

This project now uses webhook delivery for Telegram updates and does not use polling.

## Endpoints

- `GET /health`
  - Response: `{"status":"ok"}`
- `POST /telegram/webhook`
  - Requires header `X-Telegram-Bot-Api-Secret-Token`
  - Header must match `TELEGRAM_WEBHOOK_SECRET`
  - Invalid secret -> `401`
  - Misconfigured secret -> `500`
  - Valid request -> processed through `Application.process_update()` and returns `{"ok": true}`

## Runtime

- App entry: `app.py`
- Telegram handler wiring: `agents/inbox/adapter.py`
- Command: `python main.py webhook`

## Environment Variables

- `TELEGRAM_TOKEN`
- `TELEGRAM_WEBHOOK_SECRET`
- `PUBLIC_BASE_URL`
- `TELEGRAM_WEBHOOK_PATH` (default `/telegram/webhook`)
- `WEBHOOK_HOST` (default `0.0.0.0`)
- `WEBHOOK_PORT` (default `8000`)
- `WEBHOOK_PROCESS_TIMEOUT_SECONDS` (default `10`)

## Registration

Use `set_webhook.sh` to configure Telegram webhook URL + secret token.

## Security

- Secret-token header verification is enforced on every webhook request.
- Polling mode is removed from runtime path.
