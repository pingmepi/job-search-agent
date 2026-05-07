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


# Common capitalized words that are NOT proper nouns — these appear at
# sentence starts or as generic business terms and should not trigger the
# fabrication detector.
_COMMON_SKIP_WORDS = frozenset(
    {
        "product",
        "senior",
        "junior",
        "lead",
        "manager",
        "platform",
        "team",
        "data",
        "engineering",
        "operations",
        "business",
        "strategy",
        "growth",
        "marketing",
        "technical",
        "analytics",
        "design",
        "development",
        "customer",
        "revenue",
        "sales",
        "cross",
        "functional",
        "built",
        "drove",
        "launched",
        "designed",
        "implemented",
        "defined",
        "managed",
        "developed",
        "created",
        "established",
        "optimized",
        "reduced",
        "increased",
        "improved",
        "integrated",
        "automated",
        "delivered",
        "streamlined",
        "scaled",
        "led",
        "spearheaded",
        "architected",
        "orchestrated",
        "partnered",
        "collaborated",
        "mentored",
        "owned",
        "leveraged",
        "utilized",
        "facilitated",
        "coordinated",
        "analyzed",
        "conducted",
    }
)


def _normalize_latex(text: str) -> str:
    """Strip common LaTeX escaping so numeric/entity comparisons match."""
    import re as _re

    text = text.replace("\\%", "%")
    text = text.replace("\\$", "$")
    text = text.replace("\\&", "&")
    text = text.replace("\\sim", "")
    text = _re.sub(r"(?<!-)--(?!-)", "-", text)  # em-dash to hyphen
    text = text.replace("~", " ")
    return text


def check_forbidden_claims_per_bullet(
    original_bullets: list[str],
    mutated_bullets: list[str],
    bullet_bank: list[str],
    jd_text: str = "",
    allowed_tools: list[str] | None = None,
    profile_text: str = "",
) -> list[dict]:
    """Evaluate each mutated bullet individually for fabricated claims.

    Returns a list of dicts, one per mutated bullet:
    ``[{"bullet": str, "index": int, "flagged": bool, "reasons": list[str]}]``
    """
    import re

    # Build the allowed corpus (LaTeX-normalized so metrics match)
    allowed_text = _normalize_latex(
        " ".join(original_bullets + bullet_bank).lower()
        + " "
        + jd_text.lower()
        + " "
        + profile_text.lower()
    )

    # Build skip set: common words + allowed tools
    skip_words = set(_COMMON_SKIP_WORDS)
    for tool in allowed_tools or []:
        skip_words.add(tool.lower())

    results: list[dict] = []
    for idx, bullet in enumerate(mutated_bullets):
        reasons: list[str] = []

        # Numeric claim drift
        for token in re.findall(r"\b\d+(?:\.\d+)?%?\b", bullet):
            if token.lower() not in allowed_text:
                reasons.append(f"num:{token.lower()}")

        # Entity detection — only multi-word capitalized sequences
        # (catches "Goldman Sachs", skips "Product")
        for entity in re.findall(r"\b[A-Z][a-z]+(?:\s[A-Z][a-z]+)+\b", bullet):
            if entity.lower() not in allowed_text:
                # Only flag if there are unknown words after removing skip words
                unknown = [
                    w
                    for w in entity.lower().split()
                    if w not in skip_words and w not in allowed_text
                ]
                if unknown:
                    reasons.append(f"ent:{entity.lower()}")

        # Single capitalized words — only flag if NOT in skip set
        for word in re.findall(r"\b[A-Z][a-z]+\b", bullet):
            if word.lower() not in skip_words and word.lower() not in allowed_text:
                reasons.append(f"ent:{word.lower()}")

        results.append(
            {
                "bullet": bullet,
                "index": idx,
                "flagged": len(reasons) > 0,
                "reasons": reasons,
            }
        )

    return results


def check_scope_violations(
    mutations: list[dict],
    regions: list,
    bullet_bank: list[dict],
) -> list[dict]:
    """Return SWAP mutations where the placed bullet's reference doesn't match the region.

    Deterministic — no LLM call. Each violation dict contains:
    {bullet_id, bullet_reference, placed_in_region, original_bullet}
    """
    from agents.inbox.bullet_relevance import _normalize_company

    bank_by_id = {b["id"]: b for b in bullet_bank if b.get("id")}
    violations: list[dict] = []
    for mutation in mutations:
        if mutation.get("type") != "SWAP":
            continue
        source = mutation.get("source", "")
        bullet_id = source.replace("bank:", "").strip()
        bullet = bank_by_id.get(bullet_id)
        if not bullet:
            continue
        bullet_ref = _normalize_company(bullet.get("reference"))
        original = mutation.get("original", "")
        for region in regions:
            if original in region.content:
                region_ref = _normalize_company(region.reference) if region.reference else None
                if region_ref and bullet_ref and bullet_ref != region_ref:
                    violations.append(
                        {
                            "bullet_id": bullet_id,
                            "bullet_reference": bullet.get("reference"),
                            "placed_in_region": region.reference,
                            "original_bullet": original[:80],
                        }
                    )
                break
    return violations


def check_forbidden_claims(
    original_bullets: list[str],
    mutated_bullets: list[str],
    bullet_bank: list[str],
    jd_text: str = "",
    allowed_tools: list[str] | None = None,
    profile_text: str = "",
) -> int:
    """Count the number of mutated bullets with potentially fabricated claims.

    Thin wrapper around ``check_forbidden_claims_per_bullet`` that returns
    a single int for backward compatibility with CI gate and existing tests.
    """
    per_bullet = check_forbidden_claims_per_bullet(
        original_bullets,
        mutated_bullets,
        bullet_bank,
        jd_text=jd_text,
        allowed_tools=allowed_tools,
        profile_text=profile_text,
    )
    return sum(1 for b in per_bullet if b["flagged"])


def check_draft_length(draft: str, *, max_chars: int = 300) -> bool:
    """Check that a draft is non-empty and under the character limit."""
    if not draft or not draft.strip():
        return False
    return len(draft) <= max_chars


def check_cost(cost: float, *, threshold: float = 0.15) -> bool:
    """Check that the cost is at or below the threshold."""
    return cost <= threshold
