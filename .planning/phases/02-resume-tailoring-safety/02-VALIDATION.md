---
phase: 2
slug: resume-tailoring-safety
status: draft
nyquist_compliant: true
wave_0_complete: false
created: 2026-03-05
---

# Phase 2 - Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest |
| **Config file** | `pyproject.toml` |
| **Quick run command** | `./.venv/bin/pytest -q tests/test_resume.py tests/test_integration_pipeline_adapter.py tests/test_evals.py` |
| **Full suite command** | `./.venv/bin/pytest -q` |
| **Estimated runtime** | ~150 seconds |

---

## Sampling Rate

- **After every task commit:** Run `./.venv/bin/pytest -q tests/test_resume.py tests/test_evals.py`
- **After every plan wave:** Run `./.venv/bin/pytest -q tests/test_integration_pipeline_adapter.py tests/test_resume.py tests/test_evals.py`
- **Before `$gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 180 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 2-01-01 | 01 | 1 | RES-01 | unit | `./.venv/bin/pytest -q tests/test_resume.py` | ✅ | ⬜ pending |
| 2-01-02 | 01 | 1 | RES-02 | unit | `./.venv/bin/pytest -q tests/test_resume.py tests/test_evals.py` | ✅ | ⬜ pending |
| 2-02-01 | 02 | 1 | RES-03 | integration | `./.venv/bin/pytest -q tests/test_integration_pipeline_adapter.py` | ✅ | ⬜ pending |
| 2-02-02 | 02 | 1 | RES-04 | integration | `./.venv/bin/pytest -q tests/test_integration_pipeline_adapter.py tests/test_resume.py` | ✅ | ⬜ pending |

*Status: ⬜ pending / ✅ green / ❌ red / ⚠️ flaky*

---

## Wave 0 Requirements

Existing infrastructure covers all phase requirements.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Readability and ATS scan quality of final one-page resume | RES-03 | Requires human quality judgment beyond strict page count | Generate resume for realistic JD and verify one-page readability + ATS parser compatibility |
| Truthfulness review on rewritten bullets | RES-02 | Business-grounding check is semantic and profile-specific | Compare mutated bullets with bullet bank/profile and confirm no fabricated claims |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 180s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
