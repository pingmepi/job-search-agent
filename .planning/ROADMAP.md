# Roadmap: Job Search Agent

## Overview

This roadmap hardens the existing Telegram-first pipeline into a reliable, measurable v1 system: stable ingestion and contracts first, then safe resume generation, selective collateral delivery, release-blocking quality gates, and workflow/Linear lifecycle automation.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

- [x] **Phase 1: Intake Reliability and Contracts** - Stabilize input routing, replayability, and canonical artifact contracts. (completed 2026-03-05)
- [x] **Phase 2: Resume Tailoring Safety** - Deliver grounded, compile-safe, one-page resume tailoring with reliable fallback. (completed 2026-03-05)
- [x] **Phase 3: Collateral Selection and Delivery** - Generate only requested collateral and persist outputs in local and Drive application folders. (completed 2026-03-05)
- [ ] **Phase 4: Eval Gates and Release Quality** - Enforce CI quality thresholds with representative eval coverage and ATS signaling.
- [ ] **Phase 5: Workflow State and Linear Sync** - Persist follow-up progression and keep one up-to-date Linear issue per application run.

## Phase Details

### Phase 1: Intake Reliability and Contracts
**Goal**: Users can reliably submit jobs in Telegram while the system routes non-job content safely and persists replayable, versioned run artifacts.
**Depends on**: Nothing (first phase)
**Requirements**: ING-01, ING-02, ING-03, OPS-03, OPS-04
**Success Criteria** (what must be TRUE):
  1. User can submit a job as URL, image, or text in Telegram and pipeline processing starts without manual intervention.
  2. If URL extraction fails, user receives a clear screenshot fallback prompt and can continue the same workflow.
  3. Operator can replay a webhook event from persisted raw payloads using stable IDs and timestamps.
  4. Ambiguous/non-job and article-style inputs are handled by deterministic routing branches instead of failing the job pipeline.
  5. Each run persists canonical versioned JSON artifacts for extraction, resume output, and eval output.
**Plans**: 3/3 complete (`01-01`, `01-02`, `01-03`)

### Phase 2: Resume Tailoring Safety
**Goal**: Users receive tailored resumes that remain truthful, one-page, and always end in a compilable PDF artifact.
**Depends on**: Phase 1
**Requirements**: RES-01, RES-02, RES-03, RES-04
**Success Criteria** (what must be TRUE):
  1. System selects the closest resume base and records fit score with run metadata.
  2. Resume edits stay within editable regions and preserve grounded factual claims.
  3. Resume output passes single-page constraints with bounded condense retries and safe fallback behavior.
  4. Pipeline always returns a compilable PDF, either from mutated output or rollback base artifact.
**Plans**: 3/3 complete (`02-01`, `02-02`, `02-03`)

### Phase 3: Collateral Selection and Delivery
**Goal**: Users can choose exactly which outreach collateral to generate, with all artifacts organized per application across local and Drive storage.
**Depends on**: Phase 2
**Requirements**: COL-01, COL-02, COL-03
**Success Criteria** (what must be TRUE):
  1. User is asked which collateral type(s) to generate and only selected type(s) are produced.
  2. Generated collateral and resume artifacts are stored in a dedicated folder for each application context.
  3. Generated collateral and resume artifacts are uploaded to a per-application Google Drive folder structure.
**Plans**: 3/3 complete (`03-01`, `03-02`, `03-03`)

### Phase 4: Eval Gates and Release Quality
**Goal**: Release decisions are consistently blocked or passed by measurable quality gates across representative job-processing scenarios.
**Depends on**: Phase 3
**Requirements**: QAL-01, QAL-02, QAL-03, QAL-04
**Success Criteria** (what must be TRUE):
  1. CI blocks release when compile-success, forbidden-claims, or edit-scope thresholds fail.
  2. Eval suite runs at least 10 representative cases across URL/image/text ingestion and resume/collateral generation.
  3. Eval outputs include hard and soft metrics plus token usage, latency, and resolved cost for each run.
  4. ATS compliance signals are evaluated and can affect release significance decisions.
**Plans**: TBD

### Phase 5: Workflow State and Linear Sync
**Goal**: Application lifecycle state is persisted over time and reflected in a single continuously updated Linear issue per run.
**Depends on**: Phase 4
**Requirements**: OPS-01, OPS-02
**Success Criteria** (what must be TRUE):
  1. Follow-up detection and draft progression states are persisted and transition according to schedule-aware rules.
  2. Each application run creates or updates a corresponding Linear issue with core artifacts and eval summary.
  3. Reprocessing the same application updates prior issue context instead of creating duplicate issue trails.
**Plans**: TBD

## Progress

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Intake Reliability and Contracts | 3/3 | Complete    | 2026-03-05 |
| 2. Resume Tailoring Safety | 3/3 | Complete    | 2026-03-05 |
| 3. Collateral Selection and Delivery | 3/3 | Complete    | 2026-03-05 |
| 4. Eval Gates and Release Quality | 0/TBD | Not started | - |
| 5. Workflow State and Linear Sync | 0/TBD | Not started | - |
