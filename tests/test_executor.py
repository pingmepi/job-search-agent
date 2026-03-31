"""
Tests for agents/inbox/executor.py (KAR-61).

All tests mock out IO/LLM/DB dependencies.
Covers: step dispatching, retry behaviour, fatal-step abort,
graceful degradation, StepResult fields, and execute_plan flow.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from agents.inbox.executor import (
    ExecutionContext,
    StepResult,
    _is_transient_error,
    _keyword_coverage,
    _outside_editable_content_changed,
    _run_step_with_retry,
    execute_plan,
)
from agents.inbox.planner import (
    TOOL_CALENDAR,
    TOOL_COMPILE,
    TOOL_DB_LOG,
    TOOL_JD_EXTRACT,
    TOOL_RESUME_MUTATE,
    TOOL_RESUME_SELECT,
    ToolStep,
    build_tool_plan,
)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_pack():
    """Return a minimal ApplicationPack-like namespace."""
    from agents.inbox.agent import ApplicationPack
    from agents.inbox.jd import JDSchema
    jd = JDSchema(
        company="Acme", role="AI PM", location="Remote",
        experience_required="3yr", skills=["python"], description="Own the roadmap.",
    )
    pack = ApplicationPack(jd=jd, resume_base="master_ai.tex")
    pack.collateral_files = {"email": None, "linkedin": None, "referral": None}
    return pack


def _make_settings(tmp_path: Path):
    import os
    return SimpleNamespace(
        database_url=os.environ.get("DATABASE_URL", ""),
        runs_dir=tmp_path / "runs",
        resumes_dir=tmp_path,
        profile_path=tmp_path / "profile.json",
        bullet_bank_path=tmp_path / "bullet_bank.json",
        max_cost_per_job=1.0,
    )


def _make_plan(*, skip_upload=True, skip_calendar=True, selected_collateral=None):
    return build_tool_plan(
        "AI PM role at Acme",
        skip_upload=skip_upload,
        skip_calendar=skip_calendar,
        selected_collateral=selected_collateral or [],
    )


def _make_ctx(tmp_path: Path, plan=None):
    import time
    if plan is None:
        plan = _make_plan()
    settings = _make_settings(tmp_path)
    return ExecutionContext(
        run_id="test-run-id",
        start_time=time.time(),
        plan=plan,
        settings=settings,
    )


# ── _is_transient_error ───────────────────────────────────────────────────────


class TestIsTransientError:
    def test_rate_limit_is_transient(self):
        assert _is_transient_error(Exception("rate limit exceeded")) is True

    def test_429_is_transient(self):
        assert _is_transient_error(Exception("429 too many requests")) is True

    def test_connection_error_is_transient(self):
        assert _is_transient_error(Exception("connection refused")) is True

    def test_value_error_is_not_transient(self):
        assert _is_transient_error(ValueError("bad input")) is False

    def test_key_error_is_not_transient(self):
        assert _is_transient_error(KeyError("missing")) is False


# ── _keyword_coverage ─────────────────────────────────────────────────────────


class TestKeywordCoverage:
    def test_all_skills_present(self):
        assert _keyword_coverage(["python", "sql"], "python sql developer") == 1.0

    def test_no_skills_present(self):
        assert _keyword_coverage(["go", "rust"], "python java developer") == 0.0

    def test_partial_coverage(self):
        cov = _keyword_coverage(["python", "sql", "rust"], "python sql")
        assert abs(cov - 2 / 3) < 0.01

    def test_empty_skills_returns_one(self):
        assert _keyword_coverage([], "any text") == 1.0


# ── _outside_editable_content_changed ────────────────────────────────────────


class TestOutsideEditableChanged:
    def test_only_editable_changed_returns_false(self):
        original = "header\n%%BEGIN_EDITABLE\nold\n%%END_EDITABLE\nfooter"
        mutated  = "header\n%%BEGIN_EDITABLE\nnew\n%%END_EDITABLE\nfooter"
        assert _outside_editable_content_changed(original, mutated) is False

    def test_outside_changed_returns_true(self):
        original = "header\n%%BEGIN_EDITABLE\nold\n%%END_EDITABLE\nfooter"
        mutated  = "CHANGED\n%%BEGIN_EDITABLE\nold\n%%END_EDITABLE\nfooter"
        assert _outside_editable_content_changed(original, mutated) is True


# ── StepResult ────────────────────────────────────────────────────────────────


class TestStepResult:
    def test_success_result(self):
        r = StepResult(step_name="jd_extract", success=True, attempts=1)
        assert r.success is True
        assert r.error is None

    def test_failure_result(self):
        r = StepResult(step_name="compile", success=False, attempts=2, error="boom")
        assert r.success is False
        assert r.attempts == 2
        assert "boom" in r.error


# ── _run_step_with_retry ──────────────────────────────────────────────────────


class TestRunStepWithRetry:
    def test_unknown_tool_returns_failure(self, tmp_path):
        step = ToolStep(name="bad_step", tool="nonexistent_tool")
        pack = _make_pack()
        ctx = _make_ctx(tmp_path)
        result = _run_step_with_retry(step, pack, ctx)
        assert result.success is False
        assert "Unknown tool" in (result.error or "")

    def test_successful_handler_returns_success(self, tmp_path, monkeypatch):
        """A handler that succeeds should return StepResult(success=True)."""
        from agents.inbox import executor as ex

        def _fake_jd_handler(step, pack, ctx):
            return pack

        monkeypatch.setitem(ex._HANDLERS, TOOL_JD_EXTRACT, _fake_jd_handler)

        step = ToolStep(name="jd_extract", tool=TOOL_JD_EXTRACT,
                        retry_on_transient=True, max_attempts=3)
        pack = _make_pack()
        ctx = _make_ctx(tmp_path)
        result = _run_step_with_retry(step, pack, ctx)
        assert result.success is True
        assert result.attempts == 1

    def test_non_transient_error_does_not_retry(self, tmp_path, monkeypatch):
        """A ValueError (non-transient) should fail on first attempt."""
        from agents.inbox import executor as ex

        call_count = {"n": 0}

        def _failing_handler(step, pack, ctx):
            call_count["n"] += 1
            raise ValueError("bad data")

        monkeypatch.setitem(ex._HANDLERS, TOOL_JD_EXTRACT, _failing_handler)

        step = ToolStep(name="jd_extract", tool=TOOL_JD_EXTRACT,
                        retry_on_transient=True, max_attempts=3)
        pack = _make_pack()
        ctx = _make_ctx(tmp_path)
        result = _run_step_with_retry(step, pack, ctx)
        assert result.success is False
        assert call_count["n"] == 1  # no retries for non-transient

    def test_transient_error_retries_up_to_max(self, tmp_path, monkeypatch):
        """A transient error should retry up to max_attempts."""
        from agents.inbox import executor as ex

        call_count = {"n": 0}

        def _transient_handler(step, pack, ctx):
            call_count["n"] += 1
            raise ConnectionError("rate limit exceeded")  # transient

        monkeypatch.setitem(ex._HANDLERS, TOOL_JD_EXTRACT, _transient_handler)
        monkeypatch.setattr(ex, "_is_transient_error", lambda _exc: True)
        monkeypatch.setattr("time.sleep", lambda _: None)

        step = ToolStep(name="jd_extract", tool=TOOL_JD_EXTRACT,
                        retry_on_transient=True, max_attempts=3)
        pack = _make_pack()
        ctx = _make_ctx(tmp_path)
        result = _run_step_with_retry(step, pack, ctx)
        assert result.success is False
        assert call_count["n"] == 3


# ── execute_plan ──────────────────────────────────────────────────────────────


class TestExecutePlan:
    def test_step_failure_appended_to_errors(self, tmp_path, monkeypatch):
        """A failed step should append an error message to pack.errors."""
        import agents.inbox.executor as ex
        from agents.inbox.jd import JDSchema

        def _fail(step, pack, ctx):
            raise RuntimeError("extraction failed")

        monkeypatch.setitem(ex._HANDLERS, TOOL_JD_EXTRACT, _fail)

        plan = _make_plan(skip_upload=True, skip_calendar=True)
        pack = _make_pack()
        settings = _make_settings(tmp_path)

        monkeypatch.setattr("core.db.init_db", lambda: None)

        result_pack = execute_plan(plan, pack, settings)
        assert any("jd_extract" in e or "extraction failed" in e for e in result_pack.errors)

    def test_fatal_step_abort_stops_pipeline(self, tmp_path, monkeypatch):
        """If resume_select fails, subsequent steps should not run."""
        import agents.inbox.executor as ex

        subsequent_ran = {"ran": False}

        def _fail_select(step, pack, ctx):
            raise FileNotFoundError("no resumes")

        def _track_compile(step, pack, ctx):
            subsequent_ran["ran"] = True
            return pack

        monkeypatch.setitem(ex._HANDLERS, TOOL_RESUME_SELECT, _fail_select)
        monkeypatch.setitem(ex._HANDLERS, TOOL_COMPILE, _track_compile)
        monkeypatch.setattr("core.db.init_db", lambda: None)

        # Give jd_extract a working mock so we reach resume_select
        def _ok_jd(step, pack, ctx):
            return pack

        monkeypatch.setitem(ex._HANDLERS, TOOL_JD_EXTRACT, _ok_jd)
        monkeypatch.setitem(ex._HANDLERS, TOOL_RESUME_MUTATE, _ok_jd)

        plan = _make_plan(skip_upload=True, skip_calendar=True)
        pack = _make_pack()
        settings = _make_settings(tmp_path)

        execute_plan(plan, pack, settings)
        assert subsequent_ran["ran"] is False

    def test_non_fatal_step_failure_continues(self, tmp_path, monkeypatch):
        """A non-fatal failed step should not halt subsequent steps."""
        import agents.inbox.executor as ex

        calendar_ran = {"ran": False}

        def _ok(step, pack, ctx):
            return pack

        def _fail_compile(step, pack, ctx):
            raise RuntimeError("compile boom")

        def _track_calendar(step, pack, ctx):
            calendar_ran["ran"] = True
            return pack

        for tool in [TOOL_JD_EXTRACT, TOOL_RESUME_SELECT, TOOL_RESUME_MUTATE, TOOL_DB_LOG, "eval_log"]:
            monkeypatch.setitem(ex._HANDLERS, tool, _ok)

        monkeypatch.setitem(ex._HANDLERS, TOOL_COMPILE, _fail_compile)
        monkeypatch.setitem(ex._HANDLERS, "calendar", _track_calendar)
        monkeypatch.setattr("core.db.init_db", lambda: None)

        plan = _make_plan(skip_upload=True, skip_calendar=False)
        pack = _make_pack()
        settings = _make_settings(tmp_path)

        execute_plan(plan, pack, settings)
        assert calendar_ran["ran"] is True
