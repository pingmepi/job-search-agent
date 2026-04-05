"""
Tests for agents/inbox/planner.py (KAR-61).

Covers: build_tool_plan step assembly, conditional step inclusion,
ordering, ToolStep field population, and ToolPlan helpers.
"""

from __future__ import annotations

from pathlib import Path

from agents.inbox.planner import (
    TOOL_CALENDAR,
    TOOL_COMPILE,
    TOOL_DB_LOG,
    TOOL_DRAFT_EMAIL,
    TOOL_DRAFT_LINKEDIN,
    TOOL_DRAFT_REFERRAL,
    TOOL_DRIVE_UPLOAD,
    TOOL_EVAL_LOG,
    TOOL_JD_EXTRACT,
    TOOL_OCR,
    TOOL_RESUME_MUTATE,
    TOOL_RESUME_SELECT,
    build_tool_plan,
)

# ── Fixtures ──────────────────────────────────────────────────────────────────

TEXT_INPUT = "We are hiring a Senior AI PM at Acme Inc, full-time remote."
URL_INPUT = "https://example.com/jobs/ai-pm"


# ── Core assembly tests ───────────────────────────────────────────────────────


class TestBuildToolPlanBasic:
    def test_text_input_contains_core_steps(self):
        plan = build_tool_plan(TEXT_INPUT)
        tools = plan.tool_names()
        for required in [
            TOOL_JD_EXTRACT,
            TOOL_RESUME_SELECT,
            TOOL_RESUME_MUTATE,
            TOOL_COMPILE,
            TOOL_DB_LOG,
            TOOL_EVAL_LOG,
        ]:
            assert required in tools, f"Missing step: {required}"

    def test_text_input_has_no_ocr_step(self):
        plan = build_tool_plan(TEXT_INPUT)
        assert TOOL_OCR not in plan.tool_names()

    def test_image_input_includes_ocr_first(self):
        plan = build_tool_plan("", image_path=Path("/tmp/screenshot.png"))
        tools = plan.tool_names()
        assert tools[0] == TOOL_OCR

    def test_image_input_mode_is_image(self):
        plan = build_tool_plan("", image_path=Path("/tmp/x.png"))
        assert plan.input_mode == "image"

    def test_url_input_mode_is_url(self):
        plan = build_tool_plan(URL_INPUT)
        assert plan.input_mode == "url"

    def test_text_input_mode_is_text(self):
        plan = build_tool_plan(TEXT_INPUT)
        assert plan.input_mode == "text"


# ── Conditional step tests ────────────────────────────────────────────────────


class TestConditionalSteps:
    def test_skip_upload_removes_drive_upload(self):
        plan = build_tool_plan(TEXT_INPUT, skip_upload=True)
        assert TOOL_DRIVE_UPLOAD not in plan.tool_names()

    def test_no_skip_upload_includes_drive_upload(self):
        plan = build_tool_plan(TEXT_INPUT, skip_upload=False)
        assert TOOL_DRIVE_UPLOAD in plan.tool_names()

    def test_skip_calendar_removes_calendar(self):
        plan = build_tool_plan(TEXT_INPUT, skip_calendar=True)
        assert TOOL_CALENDAR not in plan.tool_names()

    def test_no_skip_calendar_includes_calendar(self):
        plan = build_tool_plan(TEXT_INPUT, skip_calendar=False)
        assert TOOL_CALENDAR in plan.tool_names()

    def test_email_collateral_only(self):
        plan = build_tool_plan(TEXT_INPUT, selected_collateral=["email"])
        tools = plan.tool_names()
        assert TOOL_DRAFT_EMAIL in tools
        assert TOOL_DRAFT_LINKEDIN not in tools
        assert TOOL_DRAFT_REFERRAL not in tools

    def test_all_collateral_types_included(self):
        plan = build_tool_plan(TEXT_INPUT, selected_collateral=["email", "linkedin", "referral"])
        tools = plan.tool_names()
        assert TOOL_DRAFT_EMAIL in tools
        assert TOOL_DRAFT_LINKEDIN in tools
        assert TOOL_DRAFT_REFERRAL in tools

    def test_empty_collateral_no_draft_steps(self):
        plan = build_tool_plan(TEXT_INPUT, selected_collateral=[])
        tools = plan.tool_names()
        assert TOOL_DRAFT_EMAIL not in tools
        assert TOOL_DRAFT_LINKEDIN not in tools
        assert TOOL_DRAFT_REFERRAL not in tools

    def test_none_collateral_no_draft_steps(self):
        plan = build_tool_plan(TEXT_INPUT, selected_collateral=None)
        tools = plan.tool_names()
        assert TOOL_DRAFT_EMAIL not in tools

    def test_invalid_collateral_types_ignored(self):
        plan = build_tool_plan(TEXT_INPUT, selected_collateral=["email", "smoke_signal"])
        assert TOOL_DRAFT_EMAIL in plan.tool_names()
        assert plan.selected_collateral == ["email"]

    def test_duplicate_collateral_deduplicated(self):
        plan = build_tool_plan(TEXT_INPUT, selected_collateral=["email", "email", "linkedin"])
        assert plan.tool_names().count(TOOL_DRAFT_EMAIL) == 1


# ── Ordering tests ────────────────────────────────────────────────────────────


class TestStepOrdering:
    def test_jd_extract_before_resume_select(self):
        plan = build_tool_plan(TEXT_INPUT)
        tools = plan.tool_names()
        assert tools.index(TOOL_JD_EXTRACT) < tools.index(TOOL_RESUME_SELECT)

    def test_compile_before_drive_upload(self):
        plan = build_tool_plan(TEXT_INPUT, skip_upload=False)
        tools = plan.tool_names()
        assert tools.index(TOOL_COMPILE) < tools.index(TOOL_DRIVE_UPLOAD)

    def test_db_log_before_eval_log(self):
        plan = build_tool_plan(TEXT_INPUT)
        tools = plan.tool_names()
        assert tools.index(TOOL_DB_LOG) < tools.index(TOOL_EVAL_LOG)

    def test_ocr_is_first_when_image(self):
        plan = build_tool_plan("x", image_path=Path("/tmp/img.png"))
        assert plan.tool_names()[0] == TOOL_OCR


# ── ToolStep field tests ──────────────────────────────────────────────────────


class TestToolStepFields:
    def test_jd_extract_step_has_retry(self):
        plan = build_tool_plan(TEXT_INPUT)
        step = plan.get_step(TOOL_JD_EXTRACT)
        assert step is not None
        assert step.retry_on_transient is True
        assert step.max_attempts >= 2

    def test_resume_mutate_step_has_retry(self):
        plan = build_tool_plan(TEXT_INPUT)
        step = plan.get_step(TOOL_RESUME_MUTATE)
        assert step is not None
        assert step.retry_on_transient is True

    def test_ocr_step_params_contain_image_path(self):
        plan = build_tool_plan("", image_path=Path("/tmp/shot.png"))
        step = plan.get_step(TOOL_OCR)
        assert step is not None
        assert "image_path" in step.params

    def test_draft_step_params_contain_collateral_type(self):
        plan = build_tool_plan(TEXT_INPUT, selected_collateral=["email"])
        step = plan.get_step(TOOL_DRAFT_EMAIL)
        assert step is not None
        assert step.params.get("collateral_type") == "email"


# ── ToolPlan helper tests ─────────────────────────────────────────────────────


class TestToolPlanHelpers:
    def test_has_tool_returns_true_for_present(self):
        plan = build_tool_plan(TEXT_INPUT)
        assert plan.has_tool(TOOL_JD_EXTRACT) is True

    def test_has_tool_returns_false_for_absent(self):
        plan = build_tool_plan(TEXT_INPUT, skip_upload=True)
        assert plan.has_tool(TOOL_DRIVE_UPLOAD) is False

    def test_get_step_returns_none_for_absent(self):
        plan = build_tool_plan(TEXT_INPUT, skip_upload=True)
        assert plan.get_step(TOOL_DRIVE_UPLOAD) is None

    def test_tool_names_length_matches_steps(self):
        plan = build_tool_plan(TEXT_INPUT)
        assert len(plan.tool_names()) == len(plan.steps)

    def test_plan_stores_raw_text(self):
        plan = build_tool_plan(TEXT_INPUT)
        assert plan.raw_text == TEXT_INPUT
