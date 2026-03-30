# Phase 3 Research: Collateral Selection and Delivery

## Scope
Phase 3 must satisfy: `COL-01`, `COL-02`, `COL-03`.

## Current Baseline (Repo-Tailored)
- `agents/inbox/agent.py` always generates all three drafts (`email`, `linkedin`, `referral`) in Step 8 and persists them to the run output folder.
- `agents/inbox/adapter.py` does not ask users which collateral types they want; it only triggers the pipeline after routing.
- `integrations/drive.py` only uploads a single PDF and does not upload draft text artifacts.
- Pipeline artifacts are currently split between:
  - run-scoped canonical JSON: `runs/artifacts/<run_id>/{job_extraction,resume_output,eval_output}.json`
  - app-scoped output folder: `runs/artifacts/<company>_<role>_<jd_hash8>/` for PDF + drafts
- `tests/test_integration_pipeline_adapter.py` validates pipeline execution and flags, but not collateral selection behavior.

## Gap Summary Against Requirements
- `COL-01`: missing explicit user choice and selective generation; current behavior is generate-all.
- `COL-02`: local storage mostly exists but linkage to application context is fragmented across two directory keys (`run_id` and `company_role_hash`).
- `COL-03`: Drive upload only covers PDF; collateral drafts are not uploaded into the same per-application folder structure.

## Practical File-Level Implementation Approach

### COL-01: Selective collateral generation from user choice
Target behavior:
- System asks collateral preference before running draft generation.
- Only selected collateral type(s) are generated and persisted.

Files to modify:
- `agents/inbox/adapter.py`
- `agents/inbox/agent.py`
- `agents/inbox/drafts.py`
- `tests/test_integration_pipeline_adapter.py`

Concrete changes:
- In `agents/inbox/adapter.py`:
  - Add a lightweight collateral selection interaction for `INBOX` routes.
  - Parse explicit user choice into a normalized set (`email`, `linkedin`, `referral`).
  - Pass this selection into `run_pipeline(..., selected_collateral=...)`.
- In `agents/inbox/agent.py`:
  - Extend `run_pipeline` signature with `selected_collateral: set[str] | None`.
  - Default to safe behavior when unset (recommended: all three for backward compatibility), but use strict selective generation when provided.
  - Gate each generator call (`generate_email_draft`, `generate_linkedin_dm`, `generate_referral_template`) by selection.
  - Add eval/context fields: `selected_collateral`, `generated_collateral`.
- In `agents/inbox/drafts.py`:
  - Keep generator APIs unchanged; do not over-couple with selection logic.
- In tests:
  - Add cases asserting only selected drafts are generated and non-selected drafts stay `None`.

Tradeoff:
- Multi-turn Telegram UX increases adapter complexity; keeping selection normalization in adapter avoids contaminating lower-level pipeline logic.

### COL-02: Dedicated local folder per application context
Target behavior:
- One canonical local folder per application context containing resume + selected collateral.
- Canonical artifacts and produced files cross-reference each other.

Files to modify:
- `agents/inbox/agent.py`
- `core/contracts.py`
- `core/artifacts.py` (optional small helper extension)
- `tests/test_artifact_contracts.py`
- `tests/test_integration_pipeline_adapter.py`

Concrete changes:
- In `agents/inbox/agent.py`:
  - Normalize on a single application folder key, e.g. `run_id`, for produced files (`pdf`, drafts).
  - Write selected drafts into that same run folder.
  - Add produced-file manifest in run context (`produced_files`) with absolute paths.
- In `core/contracts.py`:
  - Extend `ResumeOutputArtifact` (or add collateral section) with:
    - `application_output_dir`
    - `collateral_files` map (`email`, `linkedin`, `referral` -> path/null)
  - Preserve schema validation rigor for missing/non-selected types.
- In `core/artifacts.py`:
  - Optionally add helper for writing text artifacts atomically in run-scoped folder.
- In tests:
  - Assert resume PDF and selected collateral exist in one folder and are linked in artifact JSON.

Tradeoff:
- Consolidating into run-scoped folder simplifies traceability and replay, but changes existing filesystem layout used by manual inspection.

### COL-03: Drive upload for resume + selected collateral per application folder
Target behavior:
- Drive structure reflects application context and includes resume + selected collateral files.
- Upload failures remain non-fatal but are reported clearly.

Files to modify:
- `integrations/drive.py`
- `agents/inbox/agent.py`
- `tests/test_integration_pipeline_adapter.py`

Concrete changes:
- In `integrations/drive.py`:
  - Replace single-file upload API with batch-capable API, e.g. `upload_application_artifacts(files, company, role, run_id)`.
  - Create per-application folder: `Jobs/{Company}/{Role}/{run_id}/`.
  - Upload both PDF and selected draft text files; return per-file Drive links.
- In `agents/inbox/agent.py`:
  - Build upload file list from generated local artifacts.
  - Persist returned Drive links into run context and eval artifacts.
  - Keep `skip_upload` behavior unchanged.
- In tests:
  - Mock drive upload to verify selected artifacts are sent, not all possible artifacts.
  - Assert drive metadata is logged in run context.

Tradeoff:
- More Drive API calls per run increase latency; batch upload within one folder limits operational complexity and keeps file discoverability high.

## Recommended Sequencing (Exact Repo)
1. Pipeline contract changes first in `agents/inbox/agent.py` for `selected_collateral` and generated manifest plumbing.
2. Adapter-side selection capture in `agents/inbox/adapter.py` and pass-through into pipeline.
3. Local artifact unification and contract updates in `core/contracts.py` (+ tests).
4. Drive integration expansion in `integrations/drive.py` and upload path wiring in pipeline.
5. Integration test expansion in `tests/test_integration_pipeline_adapter.py` to cover selectivity + storage + upload semantics.
6. Full regression run.

Why this order:
- Selective generation contract must exist before UI interaction and before storage/upload layers can consume it.
- Contract updates before Drive changes prevent schema drift between local and remote artifact metadata.

## Risks and Tradeoffs
- Input ambiguity risk:
  - Free-form Telegram responses may be ambiguous for collateral choice.
  - Mitigation: deterministic parser with explicit confirmation fallback.
- Backward compatibility risk:
  - Existing callers expect current `run_pipeline` signature.
  - Mitigation: keep `selected_collateral=None` default path behavior stable.
- Drive reliability risk:
  - Partial upload failures can desync local and remote folders.
  - Mitigation: return per-file upload status and persist failed-file list in run context.

## Validation Architecture
Validation layers:
- Unit tests for selection parsing and selective generation decisions.
- Integration tests for end-to-end folder outputs and upload payload composition.
- Artifact contract tests for new collateral metadata fields.

Concrete verification commands:
```bash
./.venv/bin/pytest -q tests/test_integration_pipeline_adapter.py -k "collateral or drive or pipeline"
./.venv/bin/pytest -q tests/test_artifact_contracts.py
./.venv/bin/pytest -q tests/test_integration_pipeline_adapter.py tests/test_artifact_contracts.py
./.venv/bin/pytest -q
```

Optional manual verification:
```bash
./.venv/bin/python main.py webhook
# Send Telegram JD input, choose only "email"
# Verify local folder contains PDF + email only
# Verify Drive folder Jobs/<Company>/<Role>/<run_id>/ contains matching files
```

Phase 3 exit assertions:
- `COL-01`: user choice is captured and only selected collateral types are generated.
- `COL-02`: resume + selected collateral are stored in one dedicated local application folder and linked in artifacts.
- `COL-03`: selected local artifacts are uploaded to a per-application Drive folder with persisted links/status.
