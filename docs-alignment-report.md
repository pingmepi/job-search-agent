# Docs Alignment Report — job-search-agent (`inbox-agent`)

Scanned 11 doc surfaces against ~41 Python source files on 2026-04-29 (HEAD `8c4619f`).
Re-run after PR #30 (commit `8ec48cb`) fixed prior HIGH findings on `.env.example` and PRD Phase 3 mapping.

## Summary
- HIGH: 0
- MED:  3
- LOW:  2

## Findings

### [MED] config-env-drift — Wrong Telegram token env var name in webhook spec
**File:** [docs/webhook-service.md:14](docs/webhook-service.md#L14), [docs/webhook-service.md:95](docs/webhook-service.md#L95)
**Says:** `TELEGRAM_BOT_TOKEN` (lines 14 and 95)
**Actually:** Code, [set_webhook.sh](set_webhook.sh), [.env.example](.env.example), [docs/webhook-service-instructions.md](docs/webhook-service-instructions.md), and `core/config.py:48` all use `TELEGRAM_TOKEN`. No code path reads `TELEGRAM_BOT_TOKEN`.
**Fix:** Replace both occurrences of `TELEGRAM_BOT_TOKEN` with `TELEGRAM_TOKEN` in [docs/webhook-service.md](docs/webhook-service.md).

### [MED] version-drift — Webhook spec claims Python 3.11+, repo targets 3.9
**File:** [docs/webhook-service.md:28](docs/webhook-service.md#L28)
**Says:** "Python 3.11+"
**Actually:** [pyproject.toml:5](pyproject.toml#L5) declares `requires-python = ">=3.9"` (and `target-version = "py39"`); [docs/setup-and-test.md:31](docs/setup-and-test.md#L31) prints `Python 3.9.6` as the verified version.
**Fix:** Change line 28 to "Python 3.9+" so the spec matches `pyproject.toml` and the setup guide.

### [MED] config-env-drift — Runbook env section is a stale subset of `.env.example`
**File:** [docs/README.md:73-103](docs/README.md#L73-L103) (Section 4 "Environment Configuration")
**Says:** A `.env`-style block presented under "Set required values," listing 14 vars.
**Actually:** [.env.example](.env.example) lists 22 vars, and `core/config.py` reads all of them. The runbook block omits: `TELEGRAM_ALLOWED_CHAT_IDS`, `TELEGRAM_ENABLE_DRIVE_UPLOAD`, `TELEGRAM_ENABLE_CALENDAR_EVENTS`, `OCR_MIN_TEXT_CHARS`, `OCR_MIN_ALPHA_CHARS`, `OCR_REQUIRE_JD_INDICATOR`, `ENFORCE_SINGLE_PAGE`, `MAX_CONDENSE_RETRIES`, and `GOOGLE_TOKEN_B64`.
**Fix:** Either (a) replace the inline block with a pointer to `.env.example` as the source of truth, or (b) sync the listed vars and label optional ones explicitly.

### [LOW] stale-instruction — Webhook spec is a prompt brief, not current-state docs
**File:** [docs/webhook-service.md:1-29](docs/webhook-service.md#L1-L29)
**Says:** Opens with "You are a senior backend engineer responsible for configuring a production-ready Telegram webhook service..." — i.e. an LLM prompt brief used to generate the original implementation.
**Actually:** Implementation has shipped; [docs/webhook-service-instructions.md](docs/webhook-service-instructions.md) is the actual current-state spec (endpoints, env vars, runtime). Two coexisting docs with similar names invite confusion.
**Fix:** Either rename `docs/webhook-service.md` to `docs/webhook-service-prompt.md` (or move under `.planning/`), or add a banner at the top noting it's historical and pointing at `webhook-service-instructions.md`.

### [LOW] dead-link — Scanner false-positives in interview-prep artifact
**File:** [interview-prep/ai-product-builder.md](interview-prep/ai-product-builder.md) (113 hits)
**Says:** Markdown links of form `[core/router.py:99](core/router.py#L99)` use GitHub-style `#L<line>` fragment anchors.
**Actually:** Targeted source files exist; only the line-anchor fragment is unresolvable by the local-filesystem scanner. No real broken links in user-facing docs (README, PRD, `docs/*` all clean).
**Fix:** Either teach `find_dead_doc_links.py` to ignore `#L\d+(-L\d+)?` fragments when the base path resolves, or add a `noqa`-style suppression for the `interview-prep/` directory. No action needed in the docs themselves.

## Clean Areas

- **`.env.example` ↔ `core/config.py`** — All 22 env vars read by `core/config.py` are now present in `.env.example` (previous HIGH from `8ec48cb`-era report fixed in PR #30).
- **CLI surface** — All 12 subcommands dispatched in [main.py:177-338](main.py#L177-L338) (`webhook`, `init-db`, `ci-gate`, `db-stats`, `pipeline-check`, `runs`, `followup-runner`, `replay-webhook`, `eval-report`, `build-skill-index`, `auth-google`, `encode-token`) are documented in [README.md:73-85](README.md#L73-L85).
- **PRD Phase 3 mapping** — `PRD.md` §13.3 now decomposes Phase 3 into A–F reports / pipeline checks / Drive (Done) and Portal scanner / Operator dashboard (Todo); the previous HIGH "Phase 3 Workflow Product Surface | Todo" row is gone.
- **Python version** — `pyproject.toml` (`>=3.9`), `README.md`, and `docs/setup-and-test.md` all consistent at Python 3.9+ (only outlier is `docs/webhook-service.md` — see MED above).
- **Stack versions** — `python-telegram-bot>=21.0`, `fastapi>=0.111.0`, `uvicorn>=0.30.0` in `pyproject.toml` match the spec in `docs/webhook-service.md`.
- **Webhook endpoints** — `GET /health` and `POST /telegram/webhook` documented in `README.md:22-23` and `docs/webhook-service-instructions.md:7-14` match `app.py` routes.

## Sampling note

Exhaustively scanned: root markdown (`README.md`, `PRD.md`, `AGENTS.md`, `TRACKER.md`, `AGENT_HANDOFF.md`), `docs/*.md`, `.env.example`, `pyproject.toml`, `core/config.py`, `main.py`, `app.py`, `set_webhook.sh`. Sampled (not exhaustive): files under `agents/`, `core/`, `integrations/` for env-var and import references via grep. `.planning/` and `BUILD_LOG.md` excluded as internal/historical.
