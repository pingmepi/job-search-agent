"""
Profile Agent — represents Karan's professional identity.

Read-only agent that:
- Answers questions about Karan grounded in profile.json + bullet bank
- Generates bios and positioning summaries
- Selects narrative angle (AI / Growth / Martech)
- Enforces forbidden-claim constraints

Never executes tools directly — only returns text.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from core.config import get_settings
from core.llm import chat_text, LLMResponse


# ── Data loading ──────────────────────────────────────────────────

def load_profile(profile_path: Optional[Path] = None) -> dict:
    """Load the canonical profile JSON."""
    path = profile_path or get_settings().profile_path
    return json.loads(path.read_text(encoding="utf-8"))


def load_bullet_bank(bullet_bank_path: Optional[Path] = None) -> list[dict]:
    """Load the bullet bank JSON."""
    path = bullet_bank_path or get_settings().bullet_bank_path
    return json.loads(path.read_text(encoding="utf-8"))


# ── Narrative selection ───────────────────────────────────────────

VALID_NARRATIVES = {"ai", "growth", "martech"}


def select_narrative(query: str, profile: dict) -> str:
    """
    Select the best narrative angle based on the query.

    Returns one of: 'ai', 'growth', 'martech'
    """
    query_lower = query.lower()

    # Simple keyword-based selection
    if any(kw in query_lower for kw in ["ai", "ml", "machine learning", "llm", "data science"]):
        return "ai"
    if any(kw in query_lower for kw in ["growth", "acquisition", "retention", "conversion", "funnel"]):
        return "growth"
    if any(kw in query_lower for kw in ["martech", "marketing", "automation", "crm", "campaign"]):
        return "martech"

    # Default to the first role listed
    roles = profile.get("identity", {}).get("roles", [])
    if roles:
        first_role = roles[0].lower()
        if "ai" in first_role:
            return "ai"
        if "growth" in first_role:
            return "growth"
        if "martech" in first_role:
            return "martech"

    return "ai"  # ultimate fallback


# ── Forbidden claims check ────────────────────────────────────────

def check_response_grounding(
    response_text: str,
    profile: dict,
    bullet_bank: list[dict],
) -> list[str]:
    """
    Check if a response is grounded in the profile and bullet bank.

    Returns a list of potentially ungrounded claims (empty = clean).
    """
    import re

    # Build allowed corpus
    allowed_parts = [
        json.dumps(profile),
        " ".join(b["bullet"] for b in bullet_bank),
    ]
    allowed_text = " ".join(allowed_parts).lower()

    # Extract company/org names from response (capitalized multi-word sequences)
    potential_claims = re.findall(r"\b[A-Z][a-z]+(?:\s[A-Z][a-z]+)+\b", response_text)

    ungrounded = []
    for claim in potential_claims:
        if claim.lower() not in allowed_text:
            # Skip common English phrases
            common = {"Product Manager", "Senior Product", "Business Administration",
                      "Product Management", "Data Science", "Machine Learning",
                      "Cross Functional", "Master Of"}
            if claim not in common:
                ungrounded.append(claim)

    return ungrounded


# ── Main agent function ───────────────────────────────────────────

PROFILE_SYSTEM_PROMPT = """\
You are a professional representative for {name}. You answer questions about \
their background, skills, and experience.

RULES:
1. Only use facts from the provided profile and bullet bank.
2. Never invent companies, metrics, roles, or achievements.
3. Be professional, concise, and helpful.
4. When asked for a "bio" or "positioning", use the narrative angle that best fits.

PROFILE:
{profile_json}

BULLET BANK:
{bullet_bank_json}
"""


def answer(
    query: str,
    *,
    profile_path: Optional[Path] = None,
    bullet_bank_path: Optional[Path] = None,
) -> tuple[str, str, list[str]]:
    """
    Answer a question about Karan using grounded context.

    Returns
    -------
    (response_text, narrative_used, ungrounded_claims)
    """
    profile = load_profile(profile_path)
    bullet_bank = load_bullet_bank(bullet_bank_path)

    narrative = select_narrative(query, profile)
    identity = profile.get("identity", {})

    system = PROFILE_SYSTEM_PROMPT.format(
        name=identity.get("name", "the candidate"),
        profile_json=json.dumps(profile, indent=2),
        bullet_bank_json=json.dumps(bullet_bank, indent=2),
    )

    user_msg = f"[Narrative angle: {narrative}]\n\nQuestion: {query}"

    llm_response = chat_text(system, user_msg)

    # Check grounding
    ungrounded = check_response_grounding(llm_response.text, profile, bullet_bank)

    return llm_response.text, narrative, ungrounded
