Below is a **build-ready PRD** structured for:

* Codex / Augment / Antigravity consumption
* Test-driven development
* Linear task breakdown
* Multi-agent architecture (2 + 1 agents)
* Eval-first enforcement

This is explicit. No vibes.

---

# 📄 PRD v3 — Multi-Agent Job Application System

## Project Name: `inbox-agent`

---

# 1. Product Overview

## Vision

Build a deterministic, eval-driven, multi-agent system that:

* Converts job inputs (screenshot, URL, text) into complete application packs.
* Represents the user (Karan) with grounded contextual responses.
* Enforces structured follow-ups automatically.
* Logs measurable LLM performance on every run.

---

# 2. Agent Architecture

We are building **three agents**.

---

## 2.1 Agent 1 — Inbox Agent (Executor)

### Purpose

Generate complete job application packs and execute tool actions.

### Responsibilities

* Ingest job input (image, URL, text)
* Extract and structure JD
* Select resume base
* Mutate resume (bounded edits)
* Compile LaTeX
* Upload artifacts to Drive
* Create Calendar tasks
* Generate outreach drafts
* Run all hard evals
* Log telemetry

### Has Tool Permissions

* OCR
* Curl fetch
* LaTeX compile
* Google Drive write
* Google Calendar write

---

## 2.2 Agent 2 — Profile Agent (Representative)

### Purpose

Represent Karan’s professional identity and positioning.

### Responsibilities

* Answer questions about Karan
* Generate bios
* Generate tailored positioning summaries
* Generate referral messaging
* Select narrative angle (AI / Growth / Martech)
* Suggest resume base
* Never execute tools directly

### Read-Only Access To

* Canonical profile JSON
* Base resumes
* Bullet bank
* Truth pack
* Past job logs

---

## 2.3 Agent 3 — Follow-Up Agent

### Purpose

Ensure disciplined post-application engagement.

### Responsibilities

* Monitor job logs
* Detect upcoming follow-up events
* Generate follow-up drafts
* Escalation logic (2nd nudge vs 3rd nudge)
* Suggest next action

---

# 3. Routing Layer (Deterministic)

No routing LLM initially.

### Routing Rules

| Condition                        | Route             |
| -------------------------------- | ----------------- |
| Message contains image           | Inbox Agent       |
| Message contains URL             | Inbox Agent       |
| Message contains JD-like content | Inbox Agent       |
| Message asks about Karan/profile | Profile Agent     |
| Message ambiguous                | Ask clarification |

---

# 4. System Architecture

```
Telegram Adapter
    ↓
Router (Rules)
    ↓
Core Agent Engine
    ↓
Tool Executor
    ↓
Artifact Layer
    ↓
Drive / Calendar
    ↓
Eval Logger
```

Shared Storage:

* SQLite DB
* Canonical profile store
* Run logs
* Evals dataset

---

# 5. Data Models

---

## 5.1 Canonical Profile Store

`profile.json`

```json
{
  "identity": {
    "name": "Karan Mandalam",
    "roles": ["AI PM", "Growth PM", "Martech PM"]
  },
  "allowed_companies": [...],
  "allowed_tools": [...],
  "resume_bases": {
    "ai": "resumes/master_ai.tex",
    "growth": "resumes/master_growth.tex",
    "martech": "resumes/master_martech.tex"
  }
}
```

---

## 5.2 JD Schema

```json
{
  "company": "",
  "role": "",
  "location": "",
  "experience_required": "",
  "skills": [],
  "description": ""
}
```

Strict schema validation required.

---

## 5.3 Job Log Schema

```sql
jobs(
  id INTEGER PRIMARY KEY,
  company TEXT,
  role TEXT,
  jd_hash TEXT,
  fit_score INTEGER,
  resume_used TEXT,
  drive_link TEXT,
  created_at TIMESTAMP
);
```

---

# 6. Functional Requirements

---

## 6.1 Inbox Agent

### FR-IA-1: Ingestion

* Detect image / URL / text
* If URL:

  * Attempt curl probe
  * If blocked → request screenshot

### FR-IA-2: OCR

* Use Tesseract
* Clean via LLM
* Validate JD schema

### FR-IA-3: Resume Selection

* Compute keyword overlap
* Choose best base resume

### FR-IA-4: Resume Mutation

* Only modify editable regions
* Max 3 bullets rewritten
* No new companies/metrics

### FR-IA-5: Compile

* Must pass pdflatex
* If fail → revert

### FR-IA-6: Upload

Drive folder structure:

```
Jobs/{Company}/{Role}/
```

### FR-IA-7: Calendar

Create:

* Apply event
* Follow-up event (+7 days)

### FR-IA-8: Drafts

Generate:

* Email
* LinkedIn DM (<300 chars)
* Referral template

### FR-IA-9: Eval Logging

Log:

* compile_success
* edit_scope_violation
* forbidden_claims_count
* keyword_coverage
* latency
* tokens
* cost_estimate

---

## 6.2 Profile Agent

### FR-PA-1: Grounded Responses

Must answer using:

* profile.json
* resume bases
* bullet bank

### FR-PA-2: No Inventions

Must pass forbidden claims check.

### FR-PA-3: Narrative Selection

Can select role-family positioning.

---

## 6.3 Follow-Up Agent

### FR-FU-1: Follow-Up Detection

Detect:

* +7 days from application
* No status update

### FR-FU-2: Draft Follow-Up

Generate polite nudge.

---

# 7. Evaluation Framework (MANDATORY)

Linked to: Evals Doc v2

Hard constraints:

* JD schema valid
* LaTeX compile success
* Edit-scope enforcement
* Forbidden claim detection
* Draft length enforcement
* Cost < threshold

Soft constraints:

* Resume relevance score (LLM judge)
* JD extraction accuracy score

CI must fail if:

* compile success < 95%
* forbidden claims > 0
* edit violations > 0

---

# 8. Development Phases

---

## Phase 0 — Core Executor (TDD)

Deliverables:

* Telegram bot
* OCR pipeline
* JD structuring
* Resume mutation
* Compile
* Drive upload
* Calendar creation
* Eval logging

Tests required before merge:

* JD schema test
* Compile test
* Editable region test
* Forbidden claim test
* Draft length test

---

## Phase 1 — Intelligence Layer

Add:

* Bullet bank selection
* Fit scoring
* Job DB
* Versioning
* Structured eval suite with regression checks

---

## Phase 2 — Planner Mode

* Tool plan JSON
* Tool executor validation
* Retry logic
* Memory-influenced base selection

---

## Phase 3 — SaaS Readiness

* Multi-user support
* OAuth flows
* Dashboard
* Billing
* Usage metering

---

# 9. Linear Task Breakdown

Example Epic Structure:

### Epic 1: Infrastructure

* Setup repo structure
* Setup SQLite schema
* Setup Drive + Calendar OAuth

### Epic 2: Inbox Agent Core

* Implement Telegram adapter
* Implement ingestion routing
* Implement OCR pipeline
* Implement JD schema validation

### Epic 3: Resume Engine

* Implement editable region enforcement
* Implement mutation logic
* Implement compile test

### Epic 4: Integrations

* Drive upload
* Calendar events

### Epic 5: Eval Framework

* Hard evals
* Soft evals
* Logging system
* Regression runner

### Epic 6: Profile Agent

* Context grounding
* Narrative selection
* Forbidden claim enforcement

### Epic 7: Follow-Up Agent

* Scheduler
* Draft generator

---

# 10. Best Practices (Non-Negotiable)

1. Test before feature.
2. Never allow resume mutation outside marked regions.
3. Always log token usage.
4. Cache JD hashes to avoid reprocessing.
5. Keep LLM prompts versioned.
6. Separate planner from executor.
7. No silent failures.
8. Always compile before upload.
9. Fail loudly in CI.
10. Keep model config centralized.

---

# 11. Repository Structure

```
core/
agents/
  inbox/
  profile/
  followup/
integrations/
evals/
tests/
resumes/
profile/
runs/
```

---

# 12. Success Criteria

System is production-ready when:

* 10+ eval cases pass
* Compile success ≥ 95%
* No forbidden claims across test suite
* Avg cost per job < $0.15
* End-to-end latency < 60 sec

---

# 13. PRD ↔ Linear Traceability (Synced 2026-02-15)

Linear project used for execution tracking: `job-search-agent`  
https://linear.app/karans/project/job-search-agent-d5014a28b093

## 13.1 Functional Requirements Mapping

| PRD Requirement | Linear Issue(s) | Status |
| --- | --- | --- |
| FR-IA-1 Ingestion (URL fetch + screenshot fallback) | KAR-50 | Todo |
| FR-IA-2 OCR pipeline + cleanup + schema validation hardening | KAR-52 | Todo |
| FR-IA-3 Resume selection (keyword overlap, fit score) | KAR-53 | Todo |
| FR-IA-4 Resume mutation constraints | KAR-42, KAR-44 | Done |
| FR-IA-5 Compile + failure rollback | KAR-45, KAR-54 | Mixed (Done + Todo) |
| FR-IA-6 Drive upload | KAR-55 | Todo |
| FR-IA-7 Calendar events | KAR-55 | Todo |
| FR-IA-8 Draft generation | KAR-46 | Done |
| FR-IA-9 Eval logging completeness | KAR-48, KAR-57 | Mixed (Done + Todo) |
| FR-PA-1 Grounded responses | KAR-56 | Todo |
| FR-PA-2 No inventions / forbidden claims | KAR-56 | Todo |
| FR-PA-3 Narrative selection | KAR-63 | Done |
| FR-FU-1 Follow-up detection (+7d, no update, scheduled) | KAR-49, KAR-58 | Todo |
| FR-FU-2 Follow-up draft generation | KAR-64 | Done |

## 13.2 Eval / CI / Success Criteria Mapping

| PRD Item | Linear Issue(s) | Status |
| --- | --- | --- |
| Hard eval constraints implementation | KAR-48 | Done |
| Soft eval constraints | KAR-59 | Todo |
| CI thresholds + 10+ eval cases | KAR-60, KAR-51 | Todo |
| Cost/latency target instrumentation | KAR-57, KAR-60 | Todo |

## 13.3 Phase Mapping

| Phase | Linear Issue(s) | Status |
| --- | --- | --- |
| Phase 0 Core Executor hardening | KAR-42..KAR-60 | In progress |
| Phase 1 Intelligence Layer | KAR-53, KAR-57, KAR-59 | In progress |
| Phase 2 Planner Mode | KAR-61 | Todo |
| Phase 3 SaaS Readiness | KAR-62 | Todo |

## 13.4 Sync Rule

On each PRD requirement change:
1. Create/update corresponding Linear issue(s).
2. Update this mapping table in the same PR.
3. Ensure issue IDs appear in commit/PR descriptions for traceability.
