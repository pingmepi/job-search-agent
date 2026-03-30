# Stack Research

**Domain:** Brownfield Telegram job-application automation
**Researched:** 2026-03-05
**Overall Confidence:** HIGH

## Current Stack in Repo (Keep)

| Technology | Current Version in Repo | Role in System | Recommendation | Rationale | Confidence |
|---|---|---|---|---|---|
| Python | `>=3.9` | Runtime for webhook, agents, evals | Keep now, target Python 3.12 in next hardening window | Current code is stable on 3.9+; 3.12 upgrade gives better perf/security window without architecture churn | HIGH |
| FastAPI + Uvicorn | `fastapi>=0.111.0`, `uvicorn>=0.30.0` | Webhook HTTP service | Keep | Correct fit for webhook-first Telegram ingestion; already integrated and test-covered | HIGH |
| python-telegram-bot | `>=21.0` | Telegram update parsing and bot operations | Keep | Mature async support and already deeply wired into adapter/runtime | HIGH |
| OpenAI Python SDK (OpenRouter-compatible usage) | `openai>=1.30.0` | LLM calls for JD extraction, resume mutation, drafts | Keep | Already standardized in `core/llm.py` with fallback model handling | HIGH |
| Pydantic | `>=2.7.0` | Data validation/modeling | Keep and expand usage for formal artifacts | Required for upcoming JSON artifact contracts and stricter IO boundaries | HIGH |
| SQLite (`sqlite3`) | stdlib | Local job/run persistence | Keep for single-user brownfield phase | Lowest migration risk while finishing Phase 0/1 reliability work | HIGH |
| pytest + pytest-asyncio + httpx | `pytest>=8.2.0`, `pytest-asyncio>=0.23.0`, `httpx>=0.27.0` | Unit/integration/webhook tests | Keep | Already aligned with async FastAPI + telegram handler test strategy | HIGH |
| OCR/PDF toolchain | `pytesseract`, `Pillow`, `pypdf` | OCR fallback and document processing | Keep | Matches current image/PDF ingestion requirements | HIGH |

## Recommended Additions for Next Phase

| Addition | Suggested Version | Use It For | Why Now (Prescriptive) | Confidence |
|---|---|---|---|---|
| `pytest-cov` | `>=5.0` | Coverage visibility for CI gate reliability | Add immediately and fail CI on minimum coverage for critical modules (`agents/inbox`, `core/db`, `evals`) | HIGH |
| `respx` | `>=0.21` | Deterministic mocking of external HTTP integrations | Needed to reliably test Telegram/OpenRouter/Linear request paths without flaky network assumptions | HIGH |
| `jsonschema` (or Pydantic-only contracts) | `>=4.23` | Enforce persisted job/resume/eval artifact schemas | Supports KAR-75 with explicit validation at write/read boundaries | HIGH |
| `tenacity` | `>=9.0` | Retry policy standardization | Replace ad hoc retry patterns for webhook downstream calls and integration I/O | MEDIUM |
| `structlog` | `>=24.4` | Structured logs for replay/debug workflows | Makes webhook event replay and CI failure diagnosis substantially faster | MEDIUM |
| `linear-sdk` (or stable GraphQL wrapper) | latest stable | Linear issue create/update automation (KAR-76) | Prefer official/maintained SDK over hand-rolled HTTP payload logic | MEDIUM |

## Stack Decisions for Brownfield Constraints

| Decision | Prescription | Rationale | Confidence |
|---|---|---|---|
| Persistence for current milestone | Stay on SQLite, add schema/version discipline and artifact tables first | Avoid premature Postgres migration while reliability backlog is open | HIGH |
| Agent orchestration | Keep deterministic router + explicit handlers; avoid full autonomous planner path in this phase | Matches project constraint on predictability and eval-driven hardening | HIGH |
| Background scheduling | Keep current runner CLI cadence; only add lightweight scheduler if operationally necessary | Prevents avoidable infra complexity before SaaS phase | HIGH |
| LLM framework choice | Keep direct SDK integration (`openai` client) | Minimizes abstraction overhead and preserves tight eval/control loops | HIGH |

## What Not to Use (This Phase)

| Avoid | Why | Use Instead | Confidence |
|---|---|---|---|
| LangChain/LlamaIndex-style orchestration frameworks | Adds indirection and nondeterminism for a pipeline that requires strict routing/eval controls | Direct typed service modules + explicit prompts + Pydantic schemas | HIGH |
| Celery/RabbitMQ distributed task stack | Operationally heavy for current single-user webhook workload | Existing follow-up runner pattern (or lightweight queue only if proven needed) | HIGH |
| Early Postgres + Redis split for v1 hardening | Increases migration/testing surface before core reliability targets are met | SQLite with explicit migration/versioning until SaaS readiness phase | HIGH |
| Multiple ORMs introduced now | Refactor cost without immediate product payoff | Keep current `sqlite3` layer; introduce one repository abstraction only when multi-user work starts | MEDIUM |
| Replacing deterministic router with LLM router | Conflicts with current constraint on determinism/testability | Keep deterministic routing, add fallback memory-agent branch as scoped handler | HIGH |

## Version Compatibility Notes

| Package | Compatible With | Notes |
|---|---|---|
| `fastapi>=0.111.0` | `pydantic>=2.7.0` | Current repo pairing is correct for Pydantic v2 |
| `python-telegram-bot>=21.0` | Async application lifecycle in FastAPI lifespan | Keep async startup/shutdown integration pattern already in `app.py` |
| `pytest-asyncio>=0.23.0` | `pytest>=8.2.0` | Current async test config (`asyncio_mode=auto`) is appropriate |

## Next-Phase Stack Profile (Recommended Baseline)

- Runtime: Python 3.11/3.12 target, FastAPI webhook service, python-telegram-bot adapter.
- Persistence: SQLite + explicit artifact schema validation and migration discipline.
- AI layer: OpenAI SDK (OpenRouter-compatible), typed request/response models, fallback model list.
- Quality gates: pytest + pytest-asyncio + pytest-cov + respx; CI thresholds tied to eval success metrics.
- Observability: structured logs and persisted raw webhook payloads for replay/debug.

## Sources

- `/Users/karan/Desktop/job-search-agent/.planning/PROJECT.md` (project scope, active constraints, phase priorities)
- `/Users/karan/Desktop/job-search-agent/pyproject.toml` (current dependencies and version floors)
- `/Users/karan/Desktop/job-search-agent/README.md` (runtime commands and operating model)
- `/Users/karan/Desktop/job-search-agent/app.py` and `/Users/karan/Desktop/job-search-agent/core/db.py` (webhook architecture + persistence model)

---
*Stack research for: brownfield Telegram job-application automation*
*Researched: 2026-03-05*
