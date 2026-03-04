# Structure

## Top-Level Layout
- `main.py`: CLI command dispatcher for runtime operations (`webhook`, `init-db`, `ci-gate`, `db-stats`, `followup-runner`).
- `app.py`: FastAPI webhook application and server startup.
- `agents/`: business-facing agent modules (inbox, followup, profile).
- `core/`: shared platform services (config, DB, LLM, router, prompts).
- `integrations/`: Google API adapters (Drive, Calendar).
- `evals/`: hard/soft quality checks, CI gate, run logger.
- `tests/`: pytest suite for modules and integration paths.
- `profile/`: profile and bullet-bank source data.
- `resumes/`: master LaTeX resume templates and exported PDFs.
- `runs/`: runtime artifacts and JSON telemetry logs.
- `docs/`: operational runbooks and service docs.
- `scripts/`: environment/runtime helper scripts.
- `data/`: SQLite DB location (`data/inbox_agent.db` by default).
- `credentials/`: OAuth client secrets and token files for Google integrations.

## Package-Level Map

### `agents/`
- `agents/inbox/agent.py`: primary job-application pipeline orchestrator.
- `agents/inbox/adapter.py`: Telegram handlers and routing bridge.
- `agents/inbox/jd.py`: JD extraction and schema validation.
- `agents/inbox/ocr.py`: OCR pipeline and quality gate.
- `agents/inbox/resume.py`: editable-region parsing, mutation, LaTeX compile.
- `agents/inbox/drafts.py`: email/LinkedIn/referral draft generators.
- `agents/inbox/url_ingest.py`: URL fetch and HTML-to-text extraction.
- `agents/followup/agent.py`: follow-up detection/tiering/draft generation.
- `agents/followup/runner.py`: scheduled follow-up cycle runner.
- `agents/profile/agent.py`: profile-grounded Q&A.

### `core/`
- `core/config.py`: `Settings` singleton, `.env` load, path resolution.
- `core/db.py`: SQLite schema, migrations, CRUD, stats helpers.
- `core/llm.py`: OpenRouter client wrapper and cost resolution.
- `core/router.py`: deterministic message router.
- `core/prompts/__init__.py`: versioned prompt loader.
- `core/prompts/*.txt`: prompt templates (`*_v1.txt`).

### `integrations/`
- `integrations/drive.py`: Drive folder creation and PDF upload.
- `integrations/calendar.py`: application/follow-up calendar events.

### `evals/`
- `evals/hard.py`: non-negotiable checks (schema, edit scope, cost, etc.).
- `evals/soft.py`: LLM-judged quality scores.
- `evals/logger.py`: run telemetry persistence.
- `evals/ci_gate.py`: CI-facing eval gate command.

## Data and Artifacts
- `profile/profile.json`: canonical identity/profile facts.
- `profile/bullet_bank.json`: approved bullet corpus used for mutation grounding.
- `resumes/master_*.tex`: editable base resume templates.
- `runs/artifacts/<company>_<role>_<hash>/`: generated PDFs and drafts per application run.
- `runs/run-*.json`: run-level telemetry snapshots.
- `data/inbox_agent.db`: SQLite store (`jobs`, `runs`).

## Tests Layout
- Unit-style module tests are mostly named `tests/test_<module>.py`.
- Cross-module behavior tests include files such as `tests/test_webhook_api_e2e.py` and `tests/test_integration_pipeline_adapter.py`.
- Async endpoint behavior uses pytest async mode configured in `pyproject.toml` (`asyncio_mode = "auto"`).

## Naming and Organization Conventions
- Python modules use snake_case filenames (for example `url_ingest.py`, `followup/runner.py`).
- Packages use explicit `__init__.py` files (`agents/__init__.py`, `core/__init__.py`, etc.).
- Prompt files follow `{name}_v{version}.txt` in `core/prompts/` (for example `jd_extract_v1.txt`, `resume_mutate_v1.txt`).
- Resume templates follow `master_<variant>.tex` in `resumes/`.
- Runtime IDs follow prefixed patterns:
- telemetry runs: `run-<12 hex>` (`evals/logger.py`).
- follow-up cycles: `followup-<12 hex>` (`agents/followup/runner.py`).
- Generated artifact folders use slugified `{company}_{role}_{jd_hash8}`.

## Practical Navigation Shortcuts
- Start reading runtime behavior from `main.py` then `app.py`.
- For inbound message handling, follow `agents/inbox/adapter.py` → `core/router.py` and `agents/inbox/agent.py`.
- For persistence/telemetry, inspect `core/db.py` and `evals/logger.py`.
- For model prompts and generation behavior, inspect `core/prompts/*.txt` and `core/llm.py`.
