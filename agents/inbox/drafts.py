"""
Draft generators for outreach messages.

Generates:
- Email drafts
- LinkedIn DMs (< 300 chars enforced)
- Referral request templates

All use versioned prompts from core/prompts/.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.llm import chat_text
from core.prompts import load_prompt


@dataclass
class DraftResult:
    """Result of a draft generation."""
    text: str
    draft_type: str
    char_count: int
    within_limit: bool
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost_estimate: float = 0.0


# ── Email draft ───────────────────────────────────────────────────

def generate_email_draft(
    applicant_name: str,
    applicant_summary: str,
    company: str,
    role: str,
    context: str = "first outreach",
) -> DraftResult:
    """Generate a professional email draft."""
    system = load_prompt("draft_email", version=1)
    user_msg = (
        f"Applicant: {applicant_name}\n"
        f"Background: {applicant_summary}\n"
        f"Company: {company}\n"
        f"Role: {role}\n"
        f"Context: {context}"
    )

    response = chat_text(system, user_msg)
    text = response.text.strip()

    return DraftResult(
        text=text,
        draft_type="email",
        char_count=len(text),
        within_limit=True,  # emails don't have a character limit
        prompt_tokens=response.prompt_tokens,
        completion_tokens=response.completion_tokens,
        total_tokens=response.total_tokens,
        cost_estimate=response.cost_estimate,
    )


# ── LinkedIn DM ───────────────────────────────────────────────────

LINKEDIN_CHAR_LIMIT = 300


def generate_linkedin_dm(
    applicant_name: str,
    applicant_positioning: str,
    company: str,
    role: str,
    target_name: str = "",
    target_title: str = "",
) -> DraftResult:
    """
    Generate a LinkedIn DM draft, strictly under 300 characters.

    If the LLM generates a message over the limit, it is truncated
    with an ellipsis.
    """
    system = load_prompt("draft_linkedin", version=1)
    user_msg = (
        f"Applicant: {applicant_name}\n"
        f"Positioning: {applicant_positioning}\n"
        f"Target person: {target_name or 'Unknown'} ({target_title or 'Unknown'})\n"
        f"Company: {company}\n"
        f"Role: {role}"
    )

    response = chat_text(system, user_msg)
    text = response.text.strip()

    within_limit = len(text) <= LINKEDIN_CHAR_LIMIT
    if not within_limit:
        # Hard truncate to enforce constraint
        text = text[:LINKEDIN_CHAR_LIMIT - 3].rstrip() + "..."

    return DraftResult(
        text=text,
        draft_type="linkedin_dm",
        char_count=len(text),
        within_limit=within_limit,
        prompt_tokens=response.prompt_tokens,
        completion_tokens=response.completion_tokens,
        total_tokens=response.total_tokens,
        cost_estimate=response.cost_estimate,
    )


# ── Referral template ────────────────────────────────────────────

def generate_referral_template(
    applicant_name: str,
    applicant_summary: str,
    company: str,
    role: str,
    referrer_context: str = "",
) -> DraftResult:
    """Generate a referral request template."""
    system = load_prompt("draft_referral", version=1)
    user_msg = (
        f"Applicant: {applicant_name}\n"
        f"Background: {applicant_summary}\n"
        f"Company: {company}\n"
        f"Role: {role}\n"
        f"Referrer context: {referrer_context or 'No prior relationship'}"
    )

    response = chat_text(system, user_msg)
    text = response.text.strip()

    return DraftResult(
        text=text,
        draft_type="referral",
        char_count=len(text),
        within_limit=True,
        prompt_tokens=response.prompt_tokens,
        completion_tokens=response.completion_tokens,
        total_tokens=response.total_tokens,
        cost_estimate=response.cost_estimate,
    )
