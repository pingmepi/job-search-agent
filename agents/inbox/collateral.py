"""Collateral selection parsing utilities."""

from __future__ import annotations

import re
from typing import Optional

COLLATERAL_TYPES = ("email", "linkedin", "referral")
COLLATERAL_ALIASES = {
    "email": "email",
    "mail": "email",
    "linkedin": "linkedin",
    "li": "linkedin",
    "connection": "linkedin",
    "referral": "referral",
    "ref": "referral",
}


def normalize_collateral_selection(text: str) -> tuple[Optional[list[str]], bool]:
    """
    Parse free-form collateral input.

    Returns (selection, is_valid):
    - selection None => invalid/ambiguous
    - [] => explicit no-collateral
    """
    raw = (text or "").strip().lower()
    if not raw:
        return None, False

    if raw in {"none", "no", "skip", "n/a"}:
        return [], True

    if raw in {"all", "everything"}:
        return list(COLLATERAL_TYPES), True

    tokens = [t for t in re.split(r"[\s,;/&|+]+", raw) if t]
    if not tokens:
        return None, False

    seen: set[str] = set()
    for token in tokens:
        mapped = COLLATERAL_ALIASES.get(token)
        if not mapped:
            return None, False
        seen.add(mapped)

    ordered = [item for item in COLLATERAL_TYPES if item in seen]
    return ordered, bool(ordered)
