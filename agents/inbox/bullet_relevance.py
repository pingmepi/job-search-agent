"""Bullet bank relevance scoring for JD-targeted resume mutation."""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

# Stripped during company-name comparison so "Acme Inc." matches "Acme".
# Longer forms first so "Corporation" wins over "Corp" on suffix match.
_COMPANY_SUFFIXES = (
    "corporation",
    "incorporated",
    "limited",
    "company",
    "corp",
    "ltd",
    "llc",
    "inc",
    "co",
)


def _normalize(text: str) -> str:
    """Lowercase and normalize hyphens/underscores to spaces."""
    if not text:
        return ""
    return re.sub(r"[-_]", " ", text.lower().strip())


def _normalize_company(name: str | None) -> str:
    """Case-fold, trim, collapse whitespace, strip trailing punctuation and one corporate suffix."""
    if not name:
        return ""
    norm = re.sub(r"\s+", " ", name.strip().lower()).rstrip(".,;:")
    for suffix in _COMPANY_SUFFIXES:
        if norm == suffix:
            return ""
        if norm.endswith(" " + suffix):
            norm = norm[: -(len(suffix) + 1)].rstrip(" .,;:")
            break
    return norm


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
    target_reference: str | None = None,
) -> list[dict]:
    """Select the top-N most relevant bullet bank entries for a JD.

    Each returned entry gets a ``_relevance_score`` field for logging.
    Returns all entries if the bank has fewer than ``top_n`` entries.

    When ``target_reference`` is set, bullets are first filtered to those whose
    ``reference`` field (the past employer or project where the work was done)
    matches — case-insensitive, suffix-tolerant. This blocks cross-company
    attribution in boomerang/return-to-former-employer applications. If no
    bullets match (the common case: applying to a company the candidate has
    not worked at), falls back to the unfiltered bank to preserve prior behavior.
    """
    target_norm = _normalize_company(target_reference)

    candidates = bullet_bank
    if target_norm:
        scoped = [b for b in bullet_bank if _normalize_company(b.get("reference")) == target_norm]
        if scoped:
            candidates = scoped
        else:
            logger.info(
                "bullet_bank: no entries matched target_reference=%r; "
                "falling back to unscoped bank",
                target_reference,
            )

    scored = []
    for bullet in candidates:
        score = score_bullet_relevance(bullet, jd_skills, jd_description)
        entry = dict(bullet)
        entry["_relevance_score"] = round(score, 4)
        scored.append(entry)

    scored.sort(key=lambda b: b["_relevance_score"], reverse=True)
    return scored[:top_n]
