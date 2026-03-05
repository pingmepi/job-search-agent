---
phase: 1
slug: intake-reliability-and-contracts
status: draft
nyquist_compliant: true
wave_0_complete: false
created: 2026-03-05
---

# Phase 1 - Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest |
| **Config file** | `pyproject.toml` |
| **Quick run command** | `./.venv/bin/pytest -q tests/test_router.py tests/test_url_ingest.py tests/test_webhook_api_e2e.py` |
| **Full suite command** | `./.venv/bin/pytest -q` |
| **Estimated runtime** | ~120 seconds |

---

## Sampling Rate

- **After every task commit:** Run `./.venv/bin/pytest -q tests/test_router.py tests/test_url_ingest.py tests/test_webhook_api_e2e.py`
- **After every plan wave:** Run `./.venv/bin/pytest -q`
- **Before `$gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 180 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 1-01-01 | 01 | 1 | ING-03 | integration | `./.venv/bin/pytest -q tests/test_webhook_events.py` | ✅ | ⬜ pending |
| 1-01-02 | 01 | 1 | ING-03 | unit | `./.venv/bin/pytest -q tests/test_db.py` | ✅ | ⬜ pending |
| 1-02-01 | 02 | 1 | OPS-03 | unit | `./.venv/bin/pytest -q tests/test_router.py tests/test_router_article_handling.py` | ❌ W0 | ⬜ pending |
| 1-02-02 | 02 | 1 | ING-02 | integration | `./.venv/bin/pytest -q tests/test_url_ingest.py tests/test_integration_pipeline_adapter.py` | ✅ | ⬜ pending |
| 1-03-01 | 03 | 2 | OPS-04 | unit | `./.venv/bin/pytest -q tests/test_artifact_contracts.py` | ❌ W0 | ⬜ pending |
| 1-03-02 | 03 | 2 | ING-01 | integration | `./.venv/bin/pytest -q tests/test_webhook_api_e2e.py tests/test_webhook_retries.py` | ✅ | ⬜ pending |

*Status: ⬜ pending / ✅ green / ❌ red / ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_webhook_events.py` - webhook event persistence + replay path coverage
- [ ] `tests/test_router_article_handling.py` - deterministic article/ambiguous route tests
- [ ] `tests/test_artifact_contracts.py` - canonical artifact schema/version checks

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Telegram UX for URL failure fallback prompt wording | ING-02 | User-facing clarity depends on final message text | Send blocked URL through bot and confirm prompt tells user to send screenshot |
| Replay command safety for side effects | ING-03 | Needs human confirmation for `skip_upload/skip_calendar` default behavior | Replay a stored event and verify no Drive/Calendar side effect unless explicitly enabled |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all missing references
- [x] No watch-mode flags
- [x] Feedback latency < 180s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
