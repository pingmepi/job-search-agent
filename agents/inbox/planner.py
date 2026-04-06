"""
Planner for the Inbox Agent (KAR-61, PRD Phase 2).

The planner produces a deterministic ToolPlan — a typed, ordered list of
steps to execute — from the pipeline inputs.  It does NOT call any LLM.
Routing decisions match PRD §3 deterministic rules.

Usage:
    plan = build_tool_plan(
        raw_text="...",
        image_path=None,
        selected_collateral=["email", "linkedin"],
        skip_upload=False,
        skip_calendar=False,
    )
    # plan.steps is a list[ToolStep] in execution order.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

# ── Tool name constants ────────────────────────────────────────────────────────
# Keep as string literals so they're easy to assert against in tests and
# dispatch in the executor without importing the whole module tree.

TOOL_OCR = "ocr"
TOOL_JD_EXTRACT = "jd_extract"
TOOL_RESUME_SELECT = "resume_select"
TOOL_RESUME_MUTATE = "resume_mutate"
TOOL_COMPILE = "compile"
TOOL_CALENDAR = "calendar"
TOOL_DRAFT_EMAIL = "draft_email"
TOOL_DRAFT_LINKEDIN = "draft_linkedin"
TOOL_DRAFT_REFERRAL = "draft_referral"
TOOL_DRIVE_UPLOAD = "drive_upload"
TOOL_DB_LOG = "db_log"
TOOL_EVAL_LOG = "eval_log"

# Canonical ordering — used to validate / sort steps.
TOOL_ORDER: list[str] = [
    TOOL_OCR,
    TOOL_JD_EXTRACT,
    TOOL_RESUME_SELECT,
    TOOL_RESUME_MUTATE,
    TOOL_COMPILE,
    TOOL_CALENDAR,
    TOOL_DRAFT_EMAIL,
    TOOL_DRAFT_LINKEDIN,
    TOOL_DRAFT_REFERRAL,
    TOOL_DRIVE_UPLOAD,
    TOOL_DB_LOG,
    TOOL_EVAL_LOG,
]


# ── Data model ────────────────────────────────────────────────────────────────


@dataclass
class ToolStep:
    """A single planned execution step."""

    name: str
    """Human-readable label, usually matches tool."""

    tool: str
    """Tool key — matched by the executor dispatch table."""

    params: dict[str, Any] = field(default_factory=dict)
    """Arbitrary key/value params forwarded to the executor handler."""

    retry_on_transient: bool = False
    """Whether the executor should retry on transient LLM/network errors."""

    max_attempts: int = 1
    """Total attempts (including first).  Meaningful only when retry_on_transient=True."""


@dataclass
class ToolPlan:
    """
    Ordered execution plan produced by build_tool_plan().

    Attributes
    ----------
    steps : Ordered list of steps the executor will run.
    input_mode : "image" | "url" | "text"
    skip_upload : Drive upload disabled.
    skip_calendar : Calendar event creation disabled.
    selected_collateral : Normalised, ordered list of requested collateral types.
    raw_text : Original input text (preserved for executor use).
    image_path : Original image path if provided.
    """

    steps: list[ToolStep]
    input_mode: str
    skip_upload: bool
    skip_calendar: bool
    selected_collateral: list[str]
    raw_text: str = ""
    image_path: Optional[Path] = None

    # --- helpers ---

    def tool_names(self) -> list[str]:
        """Return the tool key for every step in plan order."""
        return [s.tool for s in self.steps]

    def get_step(self, tool: str) -> Optional[ToolStep]:
        """Return the first step with the given tool key, or None."""
        for s in self.steps:
            if s.tool == tool:
                return s
        return None

    def has_tool(self, tool: str) -> bool:
        """Return True if the plan contains a step for the given tool key."""
        return any(s.tool == tool for s in self.steps)


# ── Planner ───────────────────────────────────────────────────────────────────

_SUPPORTED_COLLATERAL = ("email", "linkedin", "referral")

_COLLATERAL_TOOL = {
    "email": TOOL_DRAFT_EMAIL,
    "linkedin": TOOL_DRAFT_LINKEDIN,
    "referral": TOOL_DRAFT_REFERRAL,
}


def _detect_input_mode(raw_text: str, image_path: Optional[Path]) -> str:
    if image_path:
        return "image"
    if raw_text and re.search(r"https?://", raw_text):
        return "url"
    return "text"


def _normalise_collateral(
    selected: Optional[list[str] | tuple[str, ...] | set[str]],
) -> list[str]:
    """Return deduplicated, canonically-ordered valid collateral types."""
    if not selected:
        return []
    seen: set[str] = set()
    for raw in selected:
        v = str(raw or "").strip().lower()
        if v in _SUPPORTED_COLLATERAL:
            seen.add(v)
    return [c for c in _SUPPORTED_COLLATERAL if c in seen]


def build_tool_plan(
    raw_text: str,
    *,
    image_path: Optional[Path] = None,
    selected_collateral: Optional[list[str] | tuple[str, ...] | set[str]] = None,
    skip_upload: bool = False,
    skip_calendar: bool = False,
) -> ToolPlan:
    """
    Build a deterministic execution plan from pipeline inputs.

    No LLM is called.  Steps are assembled by inspecting the inputs
    according to PRD §3 deterministic routing rules.

    Parameters
    ----------
    raw_text : Raw JD text or OCR-cleaned text.
    image_path : If provided, an OCR step is prepended.
    selected_collateral : Iterable of "email" | "linkedin" | "referral".
    skip_upload : Omit the drive_upload step.
    skip_calendar : Omit the calendar step.

    Returns
    -------
    ToolPlan with steps in canonical execution order.
    """
    input_mode = _detect_input_mode(raw_text, image_path)
    normalised_collateral = _normalise_collateral(selected_collateral)

    steps: list[ToolStep] = []

    # 1. OCR — only when image input
    if image_path:
        steps.append(
            ToolStep(
                name="ocr",
                tool=TOOL_OCR,
                params={"image_path": str(image_path)},
                retry_on_transient=True,
                max_attempts=2,
            )
        )

    # 2. JD extraction — always
    steps.append(
        ToolStep(
            name="jd_extract",
            tool=TOOL_JD_EXTRACT,
            params={"input_mode": input_mode},
            retry_on_transient=True,
            max_attempts=3,
        )
    )

    # 3. Resume selection — always
    steps.append(
        ToolStep(
            name="resume_select",
            tool=TOOL_RESUME_SELECT,
            params={},
        )
    )

    # 4. Resume mutation — always
    steps.append(
        ToolStep(
            name="resume_mutate",
            tool=TOOL_RESUME_MUTATE,
            params={},
            retry_on_transient=True,
            max_attempts=3,
        )
    )

    # 5. Compile — always
    steps.append(
        ToolStep(
            name="compile",
            tool=TOOL_COMPILE,
            params={},
        )
    )

    # 6. Calendar — skip if requested
    if not skip_calendar:
        steps.append(
            ToolStep(
                name="calendar",
                tool=TOOL_CALENDAR,
                params={},
            )
        )

    # 7. Drafts — one step per requested collateral type
    for collateral_type in normalised_collateral:
        tool_key = _COLLATERAL_TOOL[collateral_type]
        steps.append(
            ToolStep(
                name=f"draft_{collateral_type}",
                tool=tool_key,
                params={"collateral_type": collateral_type},
                retry_on_transient=True,
                max_attempts=2,
            )
        )

    # 8. Drive upload — skip if requested
    if not skip_upload:
        steps.append(
            ToolStep(
                name="drive_upload",
                tool=TOOL_DRIVE_UPLOAD,
                params={},
            )
        )

    # 9. DB log — always
    steps.append(
        ToolStep(
            name="db_log",
            tool=TOOL_DB_LOG,
            params={},
        )
    )

    # 10. Eval log — always
    steps.append(
        ToolStep(
            name="eval_log",
            tool=TOOL_EVAL_LOG,
            params={},
        )
    )

    return ToolPlan(
        steps=steps,
        input_mode=input_mode,
        skip_upload=skip_upload,
        skip_calendar=skip_calendar,
        selected_collateral=normalised_collateral,
        raw_text=raw_text,
        image_path=image_path,
    )
