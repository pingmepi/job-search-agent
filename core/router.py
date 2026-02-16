"""
Deterministic message router (PRD §3).

Routes incoming messages to the correct agent based on content analysis.
No LLM involved — pure pattern matching.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any


class AgentTarget(str, Enum):
    INBOX = "inbox"
    PROFILE = "profile"
    FOLLOWUP = "followup"
    CLARIFY = "clarify"


@dataclass
class RouteResult:
    target: AgentTarget
    reason: str


# ── Patterns ──────────────────────────────────────────────────────

_URL_PATTERN = re.compile(r"https?://[^\s]+", re.IGNORECASE)

_PROFILE_KEYWORDS = [
    "about karan",
    "tell me about",
    "who is karan",
    "karan's background",
    "karan's experience",
    "bio",
    "profile",
    "positioning",
    "introduce yourself",
    "what does karan",
    "karan's skills",
]

_JD_INDICATORS = [
    "responsibilities",
    "requirements",
    "qualifications",
    "job description",
    "we are looking for",
    "what we are looking for",
    "what we're looking for",
    "about the job",
    "you will",
    "about the role",
    "what you'll do",
    "what youll do",
    "must have",
    "nice to have",
    "experience required",
    "years of experience",
    "apply now",
    "job title",
    "role:",
    "company:",
    "location:",
]

_FOLLOWUP_KEYWORDS = [
    "follow up",
    "follow-up",
    "followup",
    "pending applications",
    "nudge",
    "check status",
]


def _normalize_text(text: str) -> str:
    """Normalize punctuation variants used in chat copy/pastes."""
    return (
        text.lower()
        .replace("’", "'")
        .replace("‘", "'")
        .replace("`", "'")
    )


def route(
    text: str | None = None,
    *,
    has_image: bool = False,
    has_url: bool | None = None,
) -> RouteResult:
    """
    Determine which agent should handle a message.

    Parameters
    ----------
    text : the message text (may be None for image-only messages)
    has_image : True if the message contains an image attachment
    has_url : override URL detection (auto-detected from text if None)
    """
    # Rule 1: Image → Inbox (likely a JD screenshot)
    if has_image:
        return RouteResult(AgentTarget.INBOX, "Message contains image (likely JD screenshot)")

    if text is None:
        return RouteResult(AgentTarget.CLARIFY, "No text or image provided")

    text_lower = _normalize_text(text).strip()

    # Rule 2: URL → Inbox (likely a job listing link)
    if has_url is None:
        has_url = bool(_URL_PATTERN.search(text))
    if has_url:
        return RouteResult(AgentTarget.INBOX, "Message contains URL (likely job listing)")

    # Rule 3: Follow-up keywords
    if any(kw in text_lower for kw in _FOLLOWUP_KEYWORDS):
        return RouteResult(AgentTarget.FOLLOWUP, "Message asks about follow-ups")

    # Rule 4: Profile keywords
    if any(kw in text_lower for kw in _PROFILE_KEYWORDS):
        return RouteResult(AgentTarget.PROFILE, "Message asks about Karan / profile")

    # Rule 5: JD-like content → Inbox
    jd_score = sum(1 for ind in _JD_INDICATORS if ind in text_lower)
    if jd_score >= 2:
        return RouteResult(AgentTarget.INBOX, f"Message looks like a JD ({jd_score} indicators)")

    # Rule 6: Ambiguous → ask for clarification
    return RouteResult(AgentTarget.CLARIFY, "Message is ambiguous — need clarification")
