"""
Hard evaluation functions (PRD §7).

All functions return simple pass/fail values.
These are the non-negotiable constraints that CI gates on.
"""

from __future__ import annotations

from typing import Any


def check_jd_schema(jd: dict[str, Any]) -> bool:
    """Check that a JD dict has all required fields with correct types."""
    required_fields = {
        "company": str,
        "role": str,
        "location": str,
        "experience_required": str,
        "skills": list,
        "description": str,
    }
    for field, expected_type in required_fields.items():
        if field not in jd:
            return False
        if not isinstance(jd[field], expected_type):
            return False
    return True


def check_compile(pdf_path: str | None) -> bool:
    """Check that LaTeX compilation produced a PDF."""
    if pdf_path is None:
        return False
    from pathlib import Path
    return Path(pdf_path).exists()


def check_edit_scope(
    original_tex: str,
    mutated_tex: str,
    *,
    outside_changed: bool,
) -> bool:
    """
    Check that no edits were made outside editable regions.

    Parameters
    ----------
    outside_changed : pre-computed flag indicating if content
                      outside %%BEGIN_EDITABLE/%%END_EDITABLE changed.
    """
    return not outside_changed


def check_forbidden_claims(
    original_bullets: list[str],
    mutated_bullets: list[str],
    bullet_bank: list[str],
) -> int:
    """
    Count the number of potentially fabricated claims in mutated bullets.

    A "forbidden claim" is any proper noun or named entity that appears in
    the mutated text but NOT in the original bullets or the bullet bank.

    Returns the count of suspicious claims (0 = clean).
    """
    import re

    # Build the "allowed" corpus
    allowed_text = " ".join(original_bullets + bullet_bank).lower()

    forbidden_count = 0
    for bullet in mutated_bullets:
        # Extract capitalized words (simple proper-noun heuristic)
        proper_nouns = re.findall(r"\b[A-Z][a-z]+(?:\s[A-Z][a-z]+)*\b", bullet)
        for noun in proper_nouns:
            if noun.lower() not in allowed_text:
                forbidden_count += 1

    return forbidden_count


def check_draft_length(draft: str, *, max_chars: int = 300) -> bool:
    """Check that a draft is non-empty and under the character limit."""
    if not draft or not draft.strip():
        return False
    return len(draft) <= max_chars


def check_cost(cost: float, *, threshold: float = 0.15) -> bool:
    """Check that the cost is at or below the threshold."""
    return cost <= threshold
