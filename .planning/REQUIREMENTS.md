# Requirements: Job Search Agent

**Defined:** 2026-03-05
**Core Value:** Given a job posting from Telegram, produce a truthful, ATS-safe, submission-ready application package with minimal manual effort.

## v1 Requirements

### Ingestion

- [ ] **ING-01**: User can submit a job posting via Telegram as URL, image, or text and trigger pipeline processing
- [ ] **ING-02**: If URL extraction fails, user receives a clear screenshot fallback prompt and can continue without manual debugging
- [ ] **ING-03**: Raw webhook payloads are persisted with stable IDs/timestamps for replay and debugging

### Resume Tailoring

- [ ] **RES-01**: System selects the closest resume base and records fit score with run metadata
- [ ] **RES-02**: Resume mutations are restricted to editable regions and preserve grounded factual claims
- [ ] **RES-03**: Final resume output passes single-page check with bounded condense retries and safe fallback behavior
- [ ] **RES-04**: Resume output compiles successfully to PDF or rolls back to a safe compilable base artifact

### Collateral

- [ ] **COL-01**: System asks the user which collateral they want for a job application and generates only the selected type(s), not all collateral by default
- [ ] **COL-02**: Generated collateral is stored in a dedicated folder per job application and linked to that application context
- [ ] **COL-03**: Generated collateral and resume artifacts are uploaded to Google Drive in a folder structure organized per job application

### Quality and Eval Gates

- [ ] **QAL-01**: CI gate enforces compile success, forbidden-claims, and edit-scope thresholds before release
- [ ] **QAL-02**: Eval suite includes at least 10 representative cases across URL/image/text ingestion and resume/collateral generation
- [ ] **QAL-03**: Eval outputs include hard + soft quality metrics, token usage, latency, and resolved cost per run
- [ ] **QAL-04**: ATS compliance checks are evaluated as release-significant quality signals

### Workflow and Integration

- [ ] **OPS-01**: Follow-up detection and draft progression are persisted with schedule-aware state transitions
- [ ] **OPS-02**: Pipeline can create or update a Linear issue per application run with core artifacts and eval summary
- [ ] **OPS-03**: Routing includes deterministic fallback for ambiguous/non-job inputs and article-style content handling
- [ ] **OPS-04**: Canonical JSON artifacts are persisted for job extraction, resume output, and eval report with schema versioning

## v2 Requirements

### Architecture Evolution

- **ARC-01**: Introduce planner/executor separation with explicit tool-plan schema and retry safety
- **ARC-02**: Add richer strategy/memory loop for application optimization across runs

### Productization

- **SAS-01**: Multi-user/tenant isolation with user-scoped credentials and artifacts
- **SAS-02**: OAuth onboarding and account-level settings management
- **SAS-03**: Operator dashboard for run status, artifact retrieval, and quality metrics
- **SAS-04**: Billing/usage metering for paid product paths

## Out of Scope

| Feature | Reason |
|---------|--------|
| Fully autonomous outbound sending without review | High-risk for job applications; keep human approval in control loop |
| Replacing deterministic routing with pure LLM routing in v1 | Increases regression/debug complexity before reliability goals are met |
| Full SaaS tenancy in current hardening milestone | Deferred to dedicated Phase 3 productization scope |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| ING-01 | Phase 1 | Complete |
| ING-02 | Phase 1 | Complete |
| ING-03 | Phase 1 | Complete |
| RES-01 | Phase 2 | Pending |
| RES-02 | Phase 2 | Pending |
| RES-03 | Phase 2 | Pending |
| RES-04 | Phase 2 | Pending |
| COL-01 | Phase 3 | Pending |
| COL-02 | Phase 3 | Pending |
| COL-03 | Phase 3 | Pending |
| QAL-01 | Phase 4 | Pending |
| QAL-02 | Phase 4 | Pending |
| QAL-03 | Phase 4 | Pending |
| QAL-04 | Phase 4 | Pending |
| OPS-01 | Phase 5 | Pending |
| OPS-02 | Phase 5 | Pending |
| OPS-03 | Phase 1 | Complete |
| OPS-04 | Phase 1 | Complete |

**Coverage:**
- v1 requirements: 18 total
- Mapped to phases: 18
- Unmapped: 0 ✓

---
*Requirements defined: 2026-03-05*
*Last updated: 2026-03-05 after Phase 1 execution*
