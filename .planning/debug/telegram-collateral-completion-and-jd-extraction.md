---
status: awaiting_human_verify
trigger: "Investigate issue: telegram-collateral-completion-and-jd-extraction"
created: 2026-03-05T11:51:47Z
updated: 2026-03-05T12:51:54Z
---

## Current Focus

hypothesis: Mutation/condense JSON resilience and terminal-failure artifact cleanup fixes resolve the remaining partial failures.
test: Run deterministic regression suite including new mutation/condense retry + terminal-failure cleanup tests.
expecting: No `Expecting value` hard failures in mutation/condense on first malformed output; failed one-page terminal runs leave no misleading PDF artifacts.
next_action: user validates live Telegram flow for malformed mutation/condense outputs and terminal-failure artifact hygiene

## Symptoms

expected: After collateral selection, pipeline should complete and send Telegram success message with extracted JD + generated collateral summary; all collateral options (email/linkedin/referral/none) should work; JD extractor should robustly infer company/title when reasonably present in posting text.
actual: Resume and fallback resume are produced in local folder, but no completion notification is sent to Telegram for some runs. Selecting collateral options other than linkedin causes process failure. JD extraction throws schema error: "Missing or empty required field: 'company'".
errors: Telegram chat shows "Error: Missing or empty required field: 'company'" after selecting collateral and starting pipeline.
reproduction: 1) Send JD text to bot. 2) Bot asks collateral. 3) Choose a collateral (linkedin works in one case; others fail). 4) Pipeline may produce files but Telegram completion message missing, or process errors on missing company.
started: Started after recent Phase 3 collateral selection + storage changes (today, Mar 5 2026).

## Eliminated

## Evidence

- timestamp: 2026-03-05T11:52:40Z
  checked: agents/inbox/jd.py + core/prompts/jd_extract_v1.txt
  found: Prompt instructs empty string for unknown fields, but validate_jd_schema raises ValueError when company/role are empty.
  implication: Real JD text where model leaves company blank causes hard pipeline failure ("Missing or empty required field: 'company'").

- timestamp: 2026-03-05T11:52:48Z
  checked: agents/inbox/adapter.py::_normalize_collateral_selection
  found: Parser splits on comma first and only falls back to whitespace when comma split produces no parts, so input like "email linkedin" is treated as one unknown token and rejected.
  implication: Non-linkedin or mixed user responses can be rejected depending on formatting, matching collateral selection failures.

- timestamp: 2026-03-05T11:52:56Z
  checked: agents/inbox/adapter.py::_run_and_respond
  found: Success summary uses parse_mode='Markdown' with unescaped LLM-extracted fields (company/role/location/skills).
  implication: Certain extracted text can trigger Telegram Markdown parse errors, preventing completion confirmation even when local artifacts are generated.

- timestamp: 2026-03-05T11:53:04Z
  checked: tests/test_jd.py and integration test attempt
  found: JD unit tests pass current strict behavior; integration tests requiring telegram/openai dependencies cannot run in this environment.
  implication: Need targeted unit tests for new fallback and parser behavior; verify locally with dependency-independent tests.

- timestamp: 2026-03-05T11:54:40Z
  checked: tests/test_jd.py + tests/test_collateral.py
  found: Added and executed targeted regression tests for JD required-field backfill and collateral parsing; all tests passed (10 total).
  implication: Code-level regressions are fixed for the identified failure mechanisms; ready for Telegram workflow validation.

- timestamp: 2026-03-05T11:58:59Z
  checked: human verification checkpoint response
  found: Live run failed at JD stage with `LLM returned invalid JSON: Expecting value: line 1 column 1 (char 0)` after collateral selection.
  implication: Existing JD extraction parsing is insufficiently robust to non-JSON/transient LLM output; further fix required.

- timestamp: 2026-03-05T11:59:48Z
  checked: agents/inbox/jd.py extraction flow
  found: `extract_jd_with_usage` used single-attempt strict `json.loads(response.text)` and failed immediately on non-JSON output.
  implication: Any fenced/prefixed or transient empty content causes hard pipeline failure before downstream stages.

- timestamp: 2026-03-05T12:00:05Z
  checked: tests/test_jd.py + tests/test_collateral.py
  found: Added robust parsing/retry tests (fenced JSON, prefixed JSON, invalid-first-then-valid retry, transient 429 retry); full targeted suite passes (14 tests).
  implication: JD extraction is now resilient to common non-JSON wrappers and transient errors in a deterministic bounded manner.

- timestamp: 2026-03-05T12:19:46Z
  checked: human verification checkpoint response + live logs
  found: Webhook `wait_for(..., timeout=90)` timed out before handler completion; pipeline finished later but no Telegram completion message was delivered. Additional defect: mutated + fallback artifacts can both be 2 pages yet flow still reports completion success.
  implication: Need runtime timeout model that preserves in-flight update completion and strict terminal one-page enforcement.

- timestamp: 2026-03-05T12:23:45Z
  checked: app.py webhook processing loop
  found: `asyncio.wait_for(runtime.telegram_app.process_update(...))` cancellation on timeout combined with immediate in-flight cleanup allows completion path loss.
  implication: Must shield timed-out task and finalize state asynchronously on background completion.

- timestamp: 2026-03-05T12:24:20Z
  checked: agents/inbox/agent.py compile fallback path
  found: Fallback compile status was marked success even when page count remained >1.
  implication: Must treat terminal multi-page fallback as hard failure (`compile_success=false`, explicit error).

- timestamp: 2026-03-05T12:24:58Z
  checked: regression test run
  found: `pytest -q tests/test_jd.py tests/test_collateral.py tests/test_webhook_timeout_background.py tests/test_one_page_terminal_enforcement.py` => 16 passed.
  implication: New timeout and one-page enforcement logic is verified in deterministic tests.

- timestamp: 2026-03-05T12:50:00Z
  checked: human verification checkpoint response
  found: Telegram now correctly returns explicit failure, but terminal-failed run still leaves 2-page mutated/fallback PDFs; mutation/condense still fail on non-JSON outputs with `Expecting value: line 1 column 1 (char 0)`.
  implication: Need JSON-robust retry in mutation+condense and artifact hygiene cleanup for terminal failures.

- timestamp: 2026-03-05T12:51:20Z
  checked: agents/inbox/agent.py mutation + condense flow
  found: Both paths used direct `json.loads(response.text)` with no retry/recovery.
  implication: Non-JSON/fenced/prefixed model output causes immediate mutation/condense failure.

- timestamp: 2026-03-05T12:51:54Z
  checked: regression test run
  found: `pytest -q tests/test_jd.py tests/test_collateral.py tests/test_webhook_timeout_background.py tests/test_one_page_terminal_enforcement.py tests/test_resume_json_retry.py` => 17 passed.
  implication: Mutation/condense retry resilience and terminal-failure PDF cleanup are working in deterministic tests.

## Resolution

root_cause: Multi-cause issue: prior fixes landed, but resume mutation/condense still used brittle direct JSON parsing with no retry, and terminal-failure runs retained misleading PDF artifacts.
fix: Added shared JSON object extraction + bounded retry for mutation/condense LLM steps in `agents/inbox/agent.py`; added terminal-failure PDF cleanup to remove non-compliant PDFs when one-page terminal constraint fails.
verification: `pytest -q tests/test_jd.py tests/test_collateral.py tests/test_webhook_timeout_background.py tests/test_one_page_terminal_enforcement.py tests/test_resume_json_retry.py` -> 17 passed.
files_changed:
  - app.py
  - agents/inbox/jd.py
  - agents/inbox/adapter.py
  - agents/inbox/collateral.py
  - agents/inbox/agent.py
  - tests/test_jd.py
  - tests/test_collateral.py
  - tests/test_webhook_retries.py
  - tests/test_integration_pipeline_adapter.py
  - tests/test_webhook_timeout_background.py
  - tests/test_one_page_terminal_enforcement.py
  - tests/test_resume_json_retry.py
