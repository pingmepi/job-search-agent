# Phase 2 Research: Resume Tailoring Safety

## Scope
Phase 2 must satisfy: `RES-01`, `RES-02`, `RES-03`, `RES-04`.

## Current Baseline (Repo-Tailored)
- `agents/inbox/agent.py` already executes resume flow end-to-end: base selection, LLM mutation, compile, condense retries, fallback compile, eval logging, and artifact persistence.
- `agents/inbox/resume.py` already enforces edit application inside marker-delimited regions (`%%BEGIN_EDITABLE` / `%%END_EDITABLE`) and supports base selection by keyword overlap score.
- `evals/hard.py` contains hard checks for edit scope and forbidden claims, but forbidden-claim detection is currently a coarse proper-noun heuristic.
- `tests/test_resume.py` covers editable region parsing, mutation bounds, and base selection scoring, but does not cover single-page loop outcomes or truthfulness edge cases.
- `tests/test_integration_pipeline_adapter.py` already validates compile fallback rollback behavior when first compile fails.

## Gap Summary Against Requirements
- `RES-01` (closest base + fit score metadata): mostly implemented, but fit score provenance and tie-break behavior are undocumented and untested at pipeline-level.
- `RES-02` (editable-only + grounded claims): edit-scope enforcement exists, but truthfulness checks can miss numeric inflation or subtle fabricated outcomes.
- `RES-03` (single-page with bounded retries + safe fallback): condense loop exists with bounded retries, but fallback semantics are not explicitly represented when still >1 page after retries.
- `RES-04` (always compilable PDF from mutation or rollback): compile rollback exists, but final status distinctions (mutated success vs fallback success vs total failure) need stronger contract clarity and assertions.

## Practical File-Level Implementation Approach

### RES-01: Selection determinism and metadata completeness
Target behavior:
- Keep keyword-overlap selection as default, but make scoring deterministic and auditable.
- Persist score inputs and tie-break reason so runs are explainable.

Files to modify:
- `agents/inbox/resume.py`
- `agents/inbox/agent.py`
- `core/contracts.py`
- `tests/test_resume.py`
- `tests/test_artifact_contracts.py`

Concrete changes:
- In `agents/inbox/resume.py`:
  - Add a helper that returns per-resume match details (`matched_skills`, `missing_skills`, normalized score).
  - Keep stable tie-breaker via sorted filename order (already present), but codify with explicit test.
- In `agents/inbox/agent.py`:
  - Include selection metadata in eval/context (`selected_from_count`, `matched_skills`, `missing_skills`).
- In `core/contracts.py`:
  - Extend `ResumeOutputArtifact` with optional `fit_score_details` object (schema-version bump to `1.1` if needed).
- In tests:
  - Add assertions for deterministic tie-break and artifact presence of fit-score details.

Tradeoff:
- More metadata increases artifact size slightly, but significantly improves traceability when scoring seems wrong.

### RES-02: Grounded mutation and truthfulness hardening
Target behavior:
- Keep current editable-region boundary enforcement.
- Add stricter grounding checks beyond proper nouns.

Files to modify:
- `agents/inbox/agent.py`
- `evals/hard.py`
- `tests/test_evals.py`
- `tests/test_resume.py`
- `core/prompts/resume_mutate_v1.txt`
- `core/prompts/resume_condense_v1.txt`

Concrete changes:
- In `evals/hard.py`:
  - Add `check_numeric_claim_regression(original_bullets, mutated_bullets)` to flag newly introduced percentage/absolute metrics not present in source corpus.
  - Add `check_new_entity_claims(...)` using broader token heuristics (proper nouns + all-caps org-style tokens).
- In `agents/inbox/agent.py`:
  - Compute and persist new truthfulness counters in `eval_results`.
  - Fail-safe policy: if truthfulness counters exceed threshold, re-run with zero mutations (base content) before compile.
- In prompts:
  - Strengthen output contract to require citation trace in each mutation reason (`source: original|bullet_bank`).
- In tests:
  - Add unit tests for invented metric and new-entity detection.
  - Add mutation test asserting unchanged non-editable regions still holds with aggressive mutation sets.

Tradeoff:
- Stricter checks can reject useful rewrites that rephrase existing quantified impact; mitigate via conservative threshold and explicit allowlist from original + bullet bank.

### RES-03: Single-page enforcement with explicit safe degradation
Target behavior:
- Keep bounded condense retries.
- Return explicit status when one-page is not achieved after retries.

Files to modify:
- `agents/inbox/agent.py`
- `agents/inbox/resume.py`
- `core/contracts.py`
- `tests/test_integration_pipeline_adapter.py`
- `tests/test_resume.py`

Concrete changes:
- In `agents/inbox/agent.py`:
  - Track `single_page_target_met` boolean independently from compile success.
  - Add explicit terminal branches:
    - `ONE_PAGE_MET`
    - `ONE_PAGE_NOT_MET_USED_TIGHT_LAYOUT`
    - `ONE_PAGE_NOT_MET_FALLBACK_BASE`
  - After final condense/tight attempt, if page count still >1, force fallback compile of base resume and mark reason in errors/evals.
- In `core/contracts.py`:
  - Add fields `single_page_target_met` and `single_page_status` to `ResumeOutputArtifact`.
- In tests:
  - Add integration test where condense retries are exhausted and verify fallback decision and status fields.

Tradeoff:
- Fallback to base may reduce job relevance but preserves submission safety and requirement conformance.

### RES-04: Compile fallback reliability and artifact guarantees
Target behavior:
- Always emit a compilable PDF path when either mutated or base compile succeeds.
- Emit explicit failure contract when both fail.

Files to modify:
- `agents/inbox/agent.py`
- `core/contracts.py`
- `tests/test_integration_pipeline_adapter.py`
- `tests/test_artifact_contracts.py`

Concrete changes:
- In `agents/inbox/agent.py`:
  - Introduce `compile_outcome` enum-like string in eval context:
    - `mutated_success`
    - `fallback_success`
    - `compile_failed`
  - Ensure `resume_output.json` is still written even on total compile failure with `compile_success=false` and null `pdf_path`.
- In `core/contracts.py`:
  - Include `compile_outcome` and optional `compile_error_summary`.
- In tests:
  - Extend existing compile fallback integration test to assert artifact fields.
  - Add dual-failure test (mutated compile fails and fallback compile fails) to confirm explicit failed outcome contract.

Tradeoff:
- Persisting failed artifacts increases failure visibility and postmortem value, but requires consumers to handle null `pdf_path` cleanly.

## Recommended Sequencing (Exact Repo)
1. Contract extension first (`core/contracts.py`, contract tests): add `single_page_*`, `compile_outcome`, and optional fit-score details.
2. Resume-selection observability (`agents/inbox/resume.py`, `agents/inbox/agent.py`, resume tests): deterministic details and metadata plumbing.
3. Truthfulness hardening (`evals/hard.py`, prompt files, agent eval payload, eval tests): numeric/entity checks and conservative fail-safe behavior.
4. Single-page terminal-state refactor (`agents/inbox/agent.py`, integration tests): explicit statuses and forced safe fallback when condense cannot reach 1 page.
5. Compile outcome finalization (`agents/inbox/agent.py`, artifact tests): guarantee consistent artifact semantics across success/fallback/failure.
6. Full regression pass and CI gate verification.

Why this order:
- Contract-first avoids rework when plumbing new status fields.
- Truthfulness and single-page logic depend on artifact semantics being defined.
- Compile outcome and fallback logic should be validated after status taxonomy exists.

## Risks and Tradeoffs

### Truthfulness risk
- Risk: Current forbidden-claim detection can miss fabricated metrics, renamed teams, or subtle inflation.
- Mitigation: Add metric/entity delta checks and source-trace metadata on mutations; fallback to base content when violations exceed threshold.
- Tradeoff: Higher false-positive risk on benign rewording.

### Single-page enforcement risk
- Risk: Condense passes may preserve compile success but still exceed one page, causing hidden requirement drift.
- Mitigation: Track `single_page_target_met` explicitly and enforce terminal fallback when unmet.
- Tradeoff: More runs may end with less-tailored base output.

### Compile fallback risk
- Risk: Mutated compile and fallback compile can both fail (e.g., environment `pdflatex` issue), producing no PDF.
- Mitigation: Explicit `compile_outcome=compile_failed`, error summary, and deterministic artifact emission for triage.
- Tradeoff: Requirement intent says “always returns compilable PDF,” but infra-level failures can still prevent this; represent this clearly in evals and CI.

## Validation Architecture

Validation layers:
- Unit checks for selection determinism, edit-scope protection, and new truthfulness detectors.
- Integration checks for condense retry bounds, single-page terminal status, and compile fallback outcomes.
- Contract checks ensuring `resume_output.json` carries new fields consistently.

Concrete commands:
```bash
./.venv/bin/pytest -q tests/test_resume.py tests/test_evals.py tests/test_artifact_contracts.py
./.venv/bin/pytest -q tests/test_integration_pipeline_adapter.py
./.venv/bin/pytest -q
./.venv/bin/python -m evals.ci_gate
```

Optional focused command during development:
```bash
./.venv/bin/pytest -q tests/test_integration_pipeline_adapter.py -k "compile_fallback or single_page"
```

Phase 2 exit assertions:
- `RES-01`: best resume selection and fit score details are deterministic and persisted.
- `RES-02`: edits remain in editable regions and truthfulness checks catch fabricated claims/metrics.
- `RES-03`: single-page enforcement is bounded and terminal behavior is explicit/safe.
- `RES-04`: compile outcome is explicit, with reliable rollback path and artifact-level reporting.
