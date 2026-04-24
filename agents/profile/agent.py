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
import logging
import time
from pathlib import Path
from typing import Optional
from uuid import uuid4

from core.config import get_settings
from core.db import complete_run, insert_run
from core.llm import LLMResponse, chat_text

logger = logging.getLogger(__name__)

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
    if any(
        kw in query_lower for kw in ["growth", "acquisition", "retention", "conversion", "funnel"]
    ):
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

    # Build allowed corpus from structured profile + bullet bank content.
    allowed_parts = [json.dumps(profile), " ".join(str(b.get("bullet", "")) for b in bullet_bank)]
    allowed_text = " ".join(allowed_parts).lower()

    def _is_allowed(snippet: str) -> bool:
        return snippet.lower() in allowed_text

    # 1) Named entities (capitalized multi-word spans), e.g., "Stripe Finance".
    entity_candidates = re.findall(r"\b[A-Z][a-z]+(?:\s[A-Z][a-z]+)+\b", response_text)

    # 2) Metric/value claims, e.g., "increased conversion by 40%", "5x growth".
    metric_patterns = [
        r"\d+(?:\.\d+)?%",
        r"\b\d+(?:\.\d+)?x\b",
        r"\b(?:increased|reduced|improved|grew|growth|decreased)\b[^.]{0,40}\b\d+(?:\.\d+)?%?\b",
    ]
    metric_candidates: list[str] = []
    for pattern in metric_patterns:
        metric_candidates.extend(re.findall(pattern, response_text, flags=re.IGNORECASE))

    # Dynamically include allowed_tools from profile.json
    allowed_tools = set(profile.get("allowed_tools", []))

    common_entities = {
        # Roles & Titles
        "Product Manager",
        "Senior Product",
        "Technical Product Manager",
        "Program Manager",
        "Product Management",
        "Product Strategist",
        "Associate Consultant",
        "Solution Architect",

        # Domains & Concepts
        "Agentic AI",
        "Data Science",
        "Machine Learning",
        "Customer Experience",
        "Marketing Automation",
        "Workflow Orchestration",
        "Product Lifecycle",
        "Growth Strategy",
        "Funnel Optimization",
        "Implementation Lifecycle",

        # Professional Skills
        "Stakeholder Management",
        "Cross Functional",
        "Business Administration",
        "Decision Support",
        "Master Of",

        # Technical Concepts
        "Data Pipelines",
        "System Reliability",
        "Prompt Design",
        "Attribution Modeling",
        "Reporting Frameworks",
    } | allowed_tools

    ungrounded: set[str] = set()
    for candidate in entity_candidates:
        if candidate in common_entities:
            continue
        if not _is_allowed(candidate):
            ungrounded.add(candidate)

    for candidate in metric_candidates:
        if not _is_allowed(candidate):
            ungrounded.add(candidate)

    return sorted(ungrounded)


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
    text, narrative, ungrounded, _resp = answer_with_telemetry(
        query, profile_path=profile_path, bullet_bank_path=bullet_bank_path
    )
    return text, narrative, ungrounded


def answer_with_telemetry(
    query: str,
    *,
    profile_path: Optional[Path] = None,
    bullet_bank_path: Optional[Path] = None,
) -> tuple[str, str, list[str], LLMResponse]:
    """
    Answer a question and also return the raw LLMResponse for telemetry.

    Returns
    -------
    (response_text, narrative_used, ungrounded_claims, llm_response)
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

    return llm_response.text, narrative, ungrounded, llm_response


# ── Logged runner ────────────────────────────────────────────────


def run_profile_agent(
    query: str,
    *,
    profile_path: Optional[Path] = None,
    bullet_bank_path: Optional[Path] = None,
) -> tuple[str, str, list[str]]:
    """
    Run the profile agent with full telemetry logging.

    Logs a run to the ``runs`` table with token usage, latency, and
    grounding eval results. Returns the same tuple as ``answer()``.
    """
    run_id = f"profile-{uuid4().hex[:12]}"
    insert_run(run_id, "profile_agent")

    t0 = time.monotonic()
    try:
        text, narrative, ungrounded, llm_resp = answer_with_telemetry(
            query, profile_path=profile_path, bullet_bank_path=bullet_bank_path
        )
        latency_ms = int((time.monotonic() - t0) * 1000)

        complete_run(
            run_id,
            status="completed",
            tokens_used=llm_resp.total_tokens,
            latency_ms=latency_ms,
            eval_results={
                "ungrounded_claims": len(ungrounded),
                "narrative": narrative,
            },
        )
        return text, narrative, ungrounded

    except Exception as exc:
        latency_ms = int((time.monotonic() - t0) * 1000)
        logger.exception("Profile agent failed run_id=%s", run_id)
        complete_run(
            run_id,
            status="failed",
            latency_ms=latency_ms,
            errors=[str(exc)],
        )
        raise
