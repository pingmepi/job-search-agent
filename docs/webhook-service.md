You are a senior backend engineer responsible for configuring a production-ready Telegram webhook service.

Your objective:
Build a webhook-based Telegram bot service (no polling) using FastAPI and python-telegram-bot that:

- Receives Telegram updates via webhook
- Verifies Telegram secret token
- Supports text, URL, and image messages
- Is structured for future expansion (OCR, JD parsing, resume generation)
- Is deployable behind HTTPS using Caddy or Nginx
- Is written cleanly and testably

You will be provided:
- TELEGRAM_BOT_TOKEN
- TELEGRAM_WEBHOOK_SECRET
- PUBLIC_BASE_URL (e.g., https://domain.com)

Do NOT use polling.
Do NOT write throwaway code.
Do NOT inline secrets.
Use environment variables only.

---

## Requirements

### 1. Stack
- Python 3.11+
- FastAPI
- python-telegram-bot v21+
- Uvicorn
- python-dotenv

### 2. Architecture

Structure the project as:

project_root/
  app.py
  bot/
    handlers.py
    router.py
  config.py
  requirements.txt
  .env.example
  README.md

- app.py → FastAPI app + webhook endpoint
- handlers.py → Telegram message handlers
- router.py → Deterministic routing (image/url/text detection)
- config.py → Load env variables
- No business logic yet, only structured stubs

---

### 3. Webhook Requirements

- Endpoint: /telegram/webhook
- Verify header: X-Telegram-Bot-Api-Secret-Token
- Reject invalid secret with 401
- Process update via Application.process_update()
- Return JSON {"ok": true}

- Add health check endpoint: GET /health → returns {"status":"ok"}

---

### 4. Telegram Handlers

Support:

- /start command
- Text messages
- Photo messages

Behavior:

If photo:
  respond "Image received"

If text contains URL:
  respond "URL received"

If plain text:
  respond "Text received"

No heavy processing yet.

---

### 5. Webhook Registration Script

Generate a shell script `set_webhook.sh` that:

- Reads TELEGRAM_BOT_TOKEN
- Reads TELEGRAM_WEBHOOK_SECRET
- Reads PUBLIC_BASE_URL
- Calls Telegram setWebhook API
- Sets drop_pending_updates=true
- Sets secret_token
- Prints webhook info

---

### 6. Deployment Instructions

Provide:

- uvicorn command
- Example Caddyfile config
- Example Nginx config
- Example Dockerfile (optional but preferred)

---

### 7. Best Practices

- Log update_id and request time
- Add request timeout handling
- Keep webhook handler async
- Structure code for future queue integration
- Do not hardcode domain paths
- Keep handler functions small

---

### 8. Testing

Add minimal test file:

tests/test_health.py

Test that:
- /health returns 200
- invalid secret on webhook returns 401

---

### 9. Output Format

Provide:
1. File tree
2. Full code per file
3. Setup instructions
4. Webhook registration instructions
5. How to run locally with Cloudflare Tunnel
6. How to deploy on VPS

---

Important:
This is a production foundation.
Do not simplify.
Do not omit security verification.
Do not use polling.
Structure code cleanly for future agents (Inbox Agent, Profile Agent, Follow-Up Agent).
