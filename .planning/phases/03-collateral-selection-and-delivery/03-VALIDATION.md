---
phase: 3
slug: collateral-selection-and-delivery
status: draft
nyquist_compliant: true
wave_0_complete: false
created: 2026-03-05
---

# Phase 3 - Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest |
| **Config file** | `pyproject.toml` |
| **Quick run command** | `./.venv/bin/pytest -q tests/test_integration_pipeline_adapter.py tests/test_followup.py` |
| **Full suite command** | `./.venv/bin/pytest -q` |
| **Estimated runtime** | ~120 seconds |

## Sampling Rate

- **After every task commit:** run quick command
- **After every wave:** run full suite
- **Before verify-work:** full suite green
- **Max feedback latency:** 180 seconds

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 3-01-01 | 01 | 1 | COL-01 | integration | `./.venv/bin/pytest -q tests/test_integration_pipeline_adapter.py -k collateral` | ❌ W0 | ⬜ pending |
| 3-01-02 | 01 | 1 | COL-01 | unit | `./.venv/bin/pytest -q tests/test_followup.py` | ✅ | ⬜ pending |
| 3-02-01 | 02 | 1 | COL-02 | integration | `./.venv/bin/pytest -q tests/test_integration_pipeline_adapter.py -k artifact` | ✅ | ⬜ pending |
| 3-03-01 | 03 | 2 | COL-03 | integration | `./.venv/bin/pytest -q tests/test_integration_pipeline_adapter.py -k drive` | ❌ W0 | ⬜ pending |

## Wave 0 Requirements

- [ ] Add collateral selection tests in `tests/test_integration_pipeline_adapter.py`
- [ ] Add Drive-folder-organization tests for per-application upload path behavior

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Telegram user prompt flow for selecting collateral types | COL-01 | User interaction UX/timing | Send JD and verify prompt asks for collateral type selection before generation |
| Drive folder naming/readability for application context | COL-03 | Human naming semantics | Verify uploaded files land in expected `Jobs/{Company}/{Role}/{hash}` style structure |

## Validation Sign-Off

- [x] All tasks mapped to automated checks or Wave 0 dependencies
- [x] Sampling continuity preserved
- [x] No watch-mode flags
- [x] `nyquist_compliant: true` set

**Approval:** pending
