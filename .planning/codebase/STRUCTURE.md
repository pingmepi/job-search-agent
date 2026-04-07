# Structure

## Top-Level Layout

- `agents/`: domain agent implementations and adapter glue
- `core/`: shared infrastructure utilities (config, db, llm, routing, prompts)
- `integrations/`: third-party service adapters (Google Drive, Calendar)
- `evals/`: quality checks and CI evaluation gate
- `tests/`: unit/integration/e2e test modules
- `docs/`: runbooks, setup, troubleshooting, webhook docs
- `scripts/`: operational shell scripts
- `profile/`: canonical candidate profile + bullet bank inputs
- `resumes/`: source `.tex` and exported PDF resume assets
- `data/`: PostgreSQL connection config (previously SQLite; migrated at commit `e18a794`)
- `runs/`: generated runtime artifacts and outputs
- `.planning/codebase/`: architecture mapping documents

## Key Code Locations

### Entry and Runtime
- `main.py`: CLI command dispatcher (`webhook`, `init-db`, `ci-gate`, `db-stats`, `followup-runner`, `auth-google`, `replay-webhook`, `runs`)
- `app.py`: FastAPI app creation and webhook runtime lifecycle

### Agent Domain
- `agents/inbox/agent.py`: primary job-application pipeline orchestration
- `agents/inbox/adapter.py`: Telegram handlers and router-to-agent dispatch
- `agents/inbox/ocr.py`: OCR pipeline for screenshot ingestion
- `agents/inbox/jd.py`: JD extraction and caching logic
- `agents/inbox/resume.py`: resume region parsing, mutation application, PDF compile utilities
- `agents/inbox/url_ingest.py`: URL extraction + content fetch helpers
- `agents/followup/agent.py`: follow-up detection and draft generation
- `agents/followup/runner.py`: scheduled execution wrapper with run telemetry
- `agents/profile/agent.py`: grounded profile answering and narrative selection
- `agents/article/agent.py`: article summarization and job-search signal extraction
- `agents/inbox/planner.py`: deterministic tool plan assembly (zero LLM calls)
- `agents/inbox/executor.py`: resilient 12-step execution with retry and graceful degradation
- `agents/inbox/bullet_relevance.py`: JD-aware bullet bank relevance scoring for mutation selection

### Shared Infrastructure
- `core/config.py`: environment-backed immutable settings singleton
- `core/router.py`: deterministic routing engine
- `core/db.py`: PostgreSQL schema, migrations, and CRUD helpers (`psycopg2`)
- `core/llm.py`: OpenRouter-backed LLM gateway
- `core/prompts/`: versioned prompt text files (`*_v{n}.txt`)

### External Integrations
- `integrations/google_auth.py`: shared OAuth module (headless-safe, env-var bootstrap, tenacity retry)
- `integrations/drive.py`: Drive folder creation and PDF upload (uses shared auth)
- `integrations/calendar.py`: Calendar event creation (uses shared auth)

### Evaluation and QA
- `evals/hard.py`, `evals/soft.py`: rule-based checks
- `evals/logger.py`: run/eval logging helpers
- `evals/ci_gate.py`: CI gate entrypoint
- `tests/test_*.py`: pytest suite by subsystem

## Directory Conventions

### Packaging and Modules
- Python package roots declared in `pyproject.toml`: `core*`, `agents*`, `integrations*`, `evals*`
- Package directories include `__init__.py`
- Modules are grouped by domain first (`agents/inbox`, `agents/profile`, etc.)

### Naming Patterns
- Files: snake_case module names (example: `url_ingest.py`, `extract_pdfs.py`)
- Tests: `tests/test_<module_or_flow>.py`
- Prompts: `<prompt_name>_v<version>.txt` (example: `jd_extract_v1.txt`)
- Shell utilities: `.sh` scripts under `scripts/` (e.g., `pre-commit`, `install-hooks.sh`)

### Runtime Data Locations
- DB: PostgreSQL via `DATABASE_URL` env var (previously `data/inbox_agent.db`)
- Run outputs/artifacts: `runs/artifacts/`
- Profile source of truth: `profile/profile.json` and `profile/bullet_bank.json`
- Resume sources: `resumes/*.tex`; additional generated/exported docs under `resumes/Resumes/`
- Credentials: `credentials/` (OAuth material and tokens)

## Logical Grouping by Concern
- Transport/API concern: `app.py`, `agents/inbox/adapter.py`
- Control flow concern: `core/router.py`, CLI in `main.py`
- Business/domain concern: `agents/*/agent.py`, `agents/followup/runner.py`
- Infrastructure concern: `core/config.py`, `core/db.py`, `core/llm.py`
- Integration concern: `integrations/*.py`
- Verification concern: `evals/*.py`, `tests/*.py`
- Code quality: `scripts/pre-commit`, `scripts/install-hooks.sh`, `.claude/commands/review-fix.md`, `.claude/commands/review-check.md`

## Database Tables
- `jobs`: job applications (company, role, fit_score, calendar_apply_event_id, etc.)
- `runs`: per-agent-invocation telemetry (run_id, agent, tokens, cost, latency, eval_results)
- `run_steps`: per-step audit trail within a run
- `webhook_events`: raw Telegram webhook envelopes
- `article_signals`: job-search signals extracted by ArticleAgent (run_id, signal_text)

## Notable Structural Characteristics
- The project is intentionally flat at top-level for quick discoverability.
- Domain logic is centralized by agent type, not by technical layer per feature.
- Shared cross-cutting concerns are consolidated under `core/`.
- The inbox pipeline is the most structurally dense module cluster.

## Cross-Reference Map (Fast Orientation)
- Start service: `main.py` -> `app.py` -> `agents/inbox/adapter.py`
- Route decision: `agents/inbox/adapter.py` -> `core/router.py`
- Inbox execution: `agents/inbox/adapter.py` -> `agents/inbox/agent.py`
- Follow-up schedule: `main.py` -> `agents/followup/runner.py` -> `agents/followup/agent.py`
- Profile response: `agents/inbox/adapter.py` -> `agents/profile/agent.py`
- Article response: `agents/inbox/adapter.py` -> `core/router.py` -> `agents/article/agent.py`
- Persistence: agents -> `core/db.py`
- LLM calls: agents -> `core/llm.py` with prompts from `core/prompts/`
