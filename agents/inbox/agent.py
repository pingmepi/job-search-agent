"""
Inbox Agent — orchestrates the job application pipeline (KAR-61, PRD Phase 2).

This module is now a thin adapter: it builds a ToolPlan via the planner,
then delegates execution to the executor.  All step logic lives in executor.py.

Public API (unchanged):
    pack = run_pipeline(raw_text, image_path=..., selected_collateral=...,
                        skip_upload=..., skip_calendar=...)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from agents.inbox.executor import execute_plan
from agents.inbox.planner import build_tool_plan
from core.config import get_settings

SUPPORTED_COLLATERAL_TYPES = ("email", "linkedin", "referral")


@dataclass
class ApplicationPack:
    """Result of a full pipeline run."""

    jd: object  # JDSchema — typed in executor via TYPE_CHECKING
    resume_base: str
    mutated_tex: Optional[str] = None
    pdf_path: Optional[Path] = None
    output_dir: Optional[Path] = None
    drive_link: Optional[str] = None
    drive_uploads: dict = field(default_factory=dict)
    application_context_id: Optional[str] = None
    selected_collateral: list[str] = field(default_factory=list)
    generated_collateral: list[str] = field(default_factory=list)
    collateral_generation_status: str = "not_requested"
    collateral_generation_reason: Optional[str] = None
    collateral_files: dict[str, Optional[str]] = field(default_factory=dict)
    email_draft: Optional[str] = None
    linkedin_draft: Optional[str] = None
    referral_draft: Optional[str] = None
    job_id: Optional[int] = None
    run_id: Optional[str] = None
    eval_results: dict = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


def run_pipeline(
    raw_text: str,
    *,
    image_path: Optional[Path] = None,
    selected_collateral: Optional[list[str] | tuple[str, ...] | set[str]] = None,
    skip_upload: bool = False,
    skip_calendar: bool = False,
) -> ApplicationPack:
    """
    Execute the full job application pipeline.

    Builds a deterministic ToolPlan with the planner, then delegates
    execution to the executor which runs each step with retry logic.

    Parameters
    ----------
    raw_text : Raw JD text (or cleaned OCR output)
    image_path : If provided, run OCR first
    selected_collateral : Which outreach drafts to generate
    skip_upload : Skip Google Drive upload
    skip_calendar : Skip Google Calendar event creation
    """
    settings = get_settings()

    # ── Normalise collateral selection ────────────────────────────
    # Mirror existing validation so pack.errors is populated correctly
    # before handing off — collateral gating happens inside the executor
    # handler on draft steps; here we just surface invalid types early.
    normalised: list[str] = []
    invalid: list[str] = []
    collateral_status = "not_requested"
    collateral_reason: Optional[str] = None

    if selected_collateral is None:
        collateral_status = "blocked_missing_selection"
        collateral_reason = "Selection was not provided."
    else:
        seen: set[str] = set()
        for raw in selected_collateral:
            v = str(raw or "").strip().lower()
            if not v:
                continue
            if v not in SUPPORTED_COLLATERAL_TYPES:
                invalid.append(v)
            elif v not in seen:
                seen.add(v)
        normalised = [c for c in SUPPORTED_COLLATERAL_TYPES if c in seen]
        if invalid:
            collateral_status = "blocked_invalid_selection"
            collateral_reason = "Invalid collateral type(s): " + ", ".join(sorted(set(invalid)))
        elif not normalised:
            collateral_status = "skipped_no_selection"
            collateral_reason = "User explicitly chose no collateral."
        else:
            collateral_status = "selected"

    # ── Build plan ────────────────────────────────────────────────
    plan = build_tool_plan(
        raw_text,
        image_path=image_path,
        selected_collateral=normalised if not invalid else [],
        skip_upload=skip_upload,
        skip_calendar=skip_calendar,
    )

    # Placeholder JD filled in by jd_extract step
    from agents.inbox.jd import JDSchema

    placeholder_jd = JDSchema(
        company="",
        role="",
        location="",
        experience_required="",
        skills=[],
        description="",
    )

    pack = ApplicationPack(jd=placeholder_jd, resume_base="")
    pack.selected_collateral = normalised
    pack.collateral_files = {k: None for k in SUPPORTED_COLLATERAL_TYPES}
    pack.collateral_generation_status = collateral_status
    pack.collateral_generation_reason = collateral_reason

    if invalid:
        pack.errors.append(
            "Collateral generation skipped: Invalid collateral type(s): "
            + ", ".join(sorted(set(invalid)))
        )
    elif selected_collateral is None:
        pack.errors.append("Collateral generation skipped: explicit selection not provided.")

    # ── Execute plan ──────────────────────────────────────────────
    return execute_plan(plan, pack, settings)
