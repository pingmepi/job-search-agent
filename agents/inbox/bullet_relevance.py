"""Bullet bank relevance scoring for JD-targeted resume mutation."""

from __future__ import annotations

import re


def _normalize(text: str) -> str:
    """Lowercase and normalize hyphens/underscores to spaces."""
    if not text:
        return ""
    return re.sub(r"[-_]", " ", text.lower().strip())


def score_bullet_relevance(
    bullet: dict,
    jd_skills: list[str],
    jd_description: str,
) -> float:
    """Score a single bullet bank entry against a JD.

    Scoring:
      60% weight: tag overlap (bullet tags vs JD skills)
      40% weight: keyword overlap (JD skills as substrings in bullet text)

    Returns a float in [0.0, 1.0].
    """
    jd_skills = [s for s in jd_skills if s]
    if not jd_skills:
        return 0.0

    tags = [_normalize(t) for t in bullet.get("tags", [])]
    bullet_text = _normalize(bullet.get("bullet", ""))
    normalized_skills = [_normalize(s) for s in jd_skills]

    # Tag overlap: fraction of bullet tags that match any JD skill
    if tags:
        tag_matches = sum(
            1 for tag in tags if any(skill in tag or tag in skill for skill in normalized_skills)
        )
        tag_score = tag_matches / len(tags)
    else:
        tag_score = 0.0

    # Keyword overlap: fraction of JD skills found in bullet text
    keyword_matches = sum(1 for skill in normalized_skills if skill in bullet_text)
    keyword_score = keyword_matches / len(normalized_skills)

    return 0.6 * tag_score + 0.4 * keyword_score


def select_relevant_bullets(
    bullet_bank: list[dict],
    jd_skills: list[str],
    jd_description: str,
    top_n: int = 12,
) -> list[dict]:
    """Select the top-N most relevant bullet bank entries for a JD.

    Each returned entry gets a ``_relevance_score`` field for logging.
    Returns all entries if the bank has fewer than ``top_n`` entries.
    """
    scored = []
    for bullet in bullet_bank:
        score = score_bullet_relevance(bullet, jd_skills, jd_description)
        entry = dict(bullet)
        entry["_relevance_score"] = round(score, 4)
        scored.append(entry)

    scored.sort(key=lambda b: b["_relevance_score"], reverse=True)
    return scored[:top_n]
