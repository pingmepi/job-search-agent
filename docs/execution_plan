
# Job Search Agent – Execution & Task Plan

## Project

**Linear Project:** `job-search-agent`
**Owner:** Karan Mandalam
**Objective:** Build a deployable, agentic job application assistant that:

* Ingests Telegram links/screenshots
* Classifies intent (job/article/other)
* Extracts structured data
* Generates tailored LaTeX resume
* Stores artifacts in GDrive
* Updates task tracker (Linear)
* Evaluates LLM output quality via built-in evals

---

# Phase 0 – Foundation (Immediate | 0–1 day)

## Goal

Working webhook-based Telegram ingestion + structured pipeline skeleton.

## Tasks

### 1. Telegram Webhook Server

* [ ] Create bot via BotFather
* [ ] Set webhook endpoint (HTTPS required)
* [ ] Validate request signature
* [ ] Parse message payload
* [ ] Log raw input to `data/raw_events/`

### 2. Message Router (Agent Switch)

* [ ] Detect input type:

  * URL
  * Image (screenshot)
  * Plain text
* [ ] Route to:

  * JobAgent
  * ArticleAgent
  * DefaultMemoryAgent

### 3. Storage Layer

* [ ] Define directory structure:

  ```
  /data
  /resumes
  /jobs
  /evals
  /logs
  ```
* [ ] Create JSON schema for:

  * Job posting
  * Resume output
  * Evaluation result

### 4. Minimal LLM Wrapper

* [ ] Abstract provider (OpenAI / Gemini / OpenRouter)
* [ ] Logging of:

  * Prompt
  * Tokens
  * Cost
  * Latency
* [ ] Structured output enforcement (JSON schema)

---

# Phase 1 – Core Agent Capability (Deployable MVP | 1–2 days)

## Goal

End-to-end resume generation from job link or screenshot.

---

## JobAgent

### Step 1 – Content Extraction

#### For URLs

* [ ] Attempt:

  * direct HTML fetch
  * fallback to readability parser
* [ ] Extract:

  * Title
  * Company
  * Responsibilities
  * Requirements
  * Location
  * Skills

#### For Screenshot

* [ ] OCR pipeline (Tesseract or API)
* [ ] Extract text blocks
* [ ] Reconstruct structured JD

---

### Step 2 – Resume Matching Engine

Input:

* 5 base resumes (LaTeX source)
* Extracted JD JSON

Tasks:

* [ ] JD → Skill vector
* [ ] Resume selection logic
* [ ] Highlight match gaps
* [ ] Generate modified LaTeX
* [ ] Save:

  ```
  /resumes/generated/{company}_{role}.tex
  ```

---

### Step 3 – Evaluation Layer (Built-in Evals v1)

Metrics:

* Skill Coverage Score
* Keyword Overlap
* Missing Mandatory Requirements
* Hallucination Detection
* Formatting Integrity (LaTeX compile check)

Store results:

```
/evals/{company}_{role}.json
```

---

### Step 4 – Linear Integration

* [ ] Create issue:

  * Title: `Apply – {Company} – {Role}`
  * Labels: `job`, `resume-generated`
  * Attach resume link
  * Attach JD summary
* [ ] Status: “To Apply”

---

# Phase 2 – Intelligence & Memory (Next Iteration)

## Goal

Move from automation → agentic behavior.

### 1. Long-Term Profile Memory

* Structured tiered profile (Core + Projects + Anecdotes)
* Semantic retrieval
* Context compression

### 2. Feedback Loop

* Track:

  * Applied?
  * Interview?
  * Rejected?
* Correlate:

  * Resume modifications
  * JD match score
  * Response rate

### 3. Adaptive Resume Optimization

* Reinforcement logic:

  * If interviews ↑ for X pattern → weight more
  * If rejected repeatedly → deprioritize pattern

---

# Phase 3 – Productization Layer

## Architecture

* Dockerized
* Env config driven
* Provider-agnostic LLM
* Configurable storage backend

## Public Version

### Open Source Core

* Telegram ingestion
* JD extraction
* Resume generation
* Basic evals

### Paid Layer (Future SaaS)

* Cloud resume storage
* Resume A/B tracking
* Analytics dashboard
* Application performance metrics
* Multi-platform scraping connectors
* One-click export packs

Target pricing:
₹999–₹1999/month
Infra cost target: <20% of revenue
Primary cost driver: LLM tokens

---

# Agent Architecture

## RouterAgent

Determines:

* Which sub-agent to trigger
* What data is required
* What outputs must be produced

## JobAgent

JD extraction → Resume generation → Evaluation → Task creation

## ArticleAgent

Summarize → Extract insights → Suggest related reading

## ProfileAgent

Answers questions about Karan’s background
Used for:

* Referrals
* Networking drafts
* Recruiter responses

---

# Engineering Best Practices

* Test-driven development
* JSON schema validation for all LLM outputs
* Prompt versioning
* Cost tracking per request
* Deterministic temperature for resume generation
* Evaluation stored alongside output
* Modular provider interface
* Logging at every stage

---

# Evaluation Strategy

Every resume generation must log:

| Metric           | Description                    |
| ---------------- | ------------------------------ |
| Skill Coverage   | % JD skills reflected          |
| Gap Detection    | Critical missing requirements  |
| Relevance Score  | Semantic similarity            |
| Fabrication Risk | Non-existent skills introduced |
| LaTeX Validity   | Compiles successfully          |

---

# Deployment Goal (Public-Ready)

Minimum viable public version should:

* Accept Telegram job link
* Generate tailored resume
* Save LaTeX
* Log evaluation metrics
* Create Linear task
* Run via Docker
* Documented in README

Time to MVP: 48 hours
Time to product-ready polish: +2–3 days

---

This document now:

* Aligns to your Linear tracking
* Supports test-driven build
* Supports agent-based extensibility
* Positions you for public demo
* Makes it blog-worthy


