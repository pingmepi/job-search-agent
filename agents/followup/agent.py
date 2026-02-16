"""
Follow-Up Agent — monitors job applications and generates follow-up drafts.

Responsibilities:
- Query jobs needing follow-up (+7 days, no status update)
- Generate follow-up drafts with escalation tiers
- Suggest next actions
"""

from __future__ import annotations

from datetime import datetime, timezone

from core.db import get_jobs_needing_followup, update_job
from core.llm import chat_text


# ── Escalation tiers ──────────────────────────────────────────────

ESCALATION_TIERS = {
    0: {
        "label": "1st follow-up",
        "tone": "polite and professional",
        "template": "gentle check-in referencing the application",
    },
    1: {
        "label": "2nd follow-up",
        "tone": "slightly more direct, adding value",
        "template": "follow-up with a relevant insight or article",
    },
    2: {
        "label": "3rd follow-up",
        "tone": "final, graceful close",
        "template": "brief closing note leaving the door open",
    },
}

MAX_FOLLOW_UPS = 3


# ── Follow-up detection ──────────────────────────────────────────

def detect_followups(*, db_path=None) -> list[dict]:
    """
    Find all jobs that need a follow-up.

    Returns list of job dicts enriched with `escalation_tier` info.
    """
    jobs = get_jobs_needing_followup(db_path=db_path)

    enriched = []
    for job in jobs:
        count = job.get("follow_up_count", 0)
        if count >= MAX_FOLLOW_UPS:
            continue  # exhausted all tiers

        tier = ESCALATION_TIERS.get(count, ESCALATION_TIERS[2])
        job["escalation_tier"] = tier
        job["tier_number"] = count
        enriched.append(job)

    return enriched


# ── Draft generation ──────────────────────────────────────────────

FOLLOWUP_SYSTEM_PROMPT = """\
You are writing a follow-up message for a job application.

Context:
- Company: {company}
- Role: {role}
- This is the {label} (tier {tier})
- Tone: {tone}
- Style: {template}

Rules:
1. Keep it under 150 words
2. Be professional and respectful of their time
3. Reference the specific role
4. Include a soft call to action
5. Do not be desperate or pushy

Return only the message text.
"""


def generate_followup_draft(job: dict) -> str:
    """
    Generate a follow-up draft for a single job.

    Parameters
    ----------
    job : enriched job dict from detect_followups()
    """
    tier = job.get("escalation_tier", ESCALATION_TIERS[0])
    tier_number = job.get("tier_number", 0)

    system = FOLLOWUP_SYSTEM_PROMPT.format(
        company=job["company"],
        role=job["role"],
        label=tier["label"],
        tier=tier_number + 1,
        tone=tier["tone"],
        template=tier["template"],
    )

    response = chat_text(system, f"Generate a {tier['label']} message.")
    return response.text


def _persist_followup_progress(job: dict, *, db_path=None) -> int:
    """Increment follow-up count and persist follow-up timestamp. Returns new count."""
    current_count = int(job.get("follow_up_count", 0) or 0)
    next_count = current_count + 1
    update_job(
        job["id"],
        db_path=db_path,
        follow_up_count=next_count,
        last_follow_up_at=datetime.now(timezone.utc).isoformat(),
    )
    return next_count


def generate_all_followups(*, db_path=None, persist_progress: bool = True) -> list[dict]:
    """
    Detect all pending follow-ups and generate drafts.

    Returns list of follow-up payloads.

    If persist_progress=True, increments `follow_up_count` and updates
    `last_follow_up_at` for each successfully generated draft.
    """
    jobs = detect_followups(db_path=db_path)
    results = []

    for job in jobs:
        draft = generate_followup_draft(job)
        next_count = int(job.get("follow_up_count", 0) or 0)
        if persist_progress:
            next_count = _persist_followup_progress(job, db_path=db_path)
        results.append({
            "job_id": job["id"],
            "company": job["company"],
            "role": job["role"],
            "tier": job["tier_number"] + 1,
            "draft": draft,
            "follow_up_count_after": next_count,
        })

    return results
