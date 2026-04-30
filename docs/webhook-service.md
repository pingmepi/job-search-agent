# Telegram Webhook Service - Design Notes (Historical)

Last updated: 2026-04-30

This file is retained as a short design-history note.
For active operator instructions, use `docs/RUNBOOK.md`.

## Scope

- This project runs in webhook mode only (no polling).
- Runtime entry point: `python main.py webhook`.
- Endpoints:
  - `GET /health`
  - `POST /telegram/webhook`

## Security Contract

- Every webhook request must include `X-Telegram-Bot-Api-Secret-Token`.
- Header must match `TELEGRAM_WEBHOOK_SECRET`.
- Invalid secret returns `401`.

## Canonical Operational Docs

- Runtime setup and env vars: `docs/RUNBOOK.md`
- Quick webhook behavior reference: `docs/webhook-service-instructions.md`
- Troubleshooting: `docs/troubleshooting-and-debugging.md`
