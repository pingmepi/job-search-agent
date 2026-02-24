"""
JD extraction and schema validation.

Handles:
- LLM-based JD extraction from raw text
- Strict schema validation (PRD §5.2)
- Hash-based caching to avoid reprocessing
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any


@dataclass
class JDSchema:
    """Validated job description — mirrors PRD §5.2."""

    company: str
    role: str
    location: str
    experience_required: str
    skills: list[str]
    description: str

    @property
    def jd_hash(self) -> str:
        """Deterministic hash for dedup / caching."""
        payload = json.dumps(
            {"company": self.company, "role": self.role, "description": self.description},
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode()).hexdigest()[:16]


# ── In-memory cache (hash → JDSchema) ────────────────────────────
_jd_cache: dict[str, JDSchema] = {}


def validate_jd_schema(data: dict[str, Any]) -> JDSchema:
    """
    Validate a dict against the JD schema.

    Raises ValueError if required fields are missing or wrong type.
    """
    required = ["company", "role"]
    for key in required:
        if key not in data or not isinstance(data[key], str) or not data[key].strip():
            raise ValueError(f"Missing or empty required field: '{key}'")

    # skills must be a list
    skills = data.get("skills", [])
    if not isinstance(skills, list):
        raise TypeError(f"'skills' must be a list, got {type(skills).__name__}")

    jd = JDSchema(
        company=data["company"].strip(),
        role=data["role"].strip(),
        location=data.get("location", "").strip(),
        experience_required=data.get("experience_required", "").strip(),
        skills=[s.strip() for s in skills if isinstance(s, str)],
        description=data.get("description", "").strip(),
    )

    # Cache it
    _jd_cache[jd.jd_hash] = jd
    return jd


def get_cached_jd(jd_hash: str) -> JDSchema | None:
    """Return a cached JD if we've seen this hash before."""
    return _jd_cache.get(jd_hash)


def extract_jd_from_text(raw_text: str) -> JDSchema:
    """
    Use LLM to extract structured JD from raw text, then validate.

    Requires an active OpenRouter key.
    """
    from core.llm import chat_text
    from core.prompts import load_prompt

    system_prompt = load_prompt("jd_extract", version=1)

    response = chat_text(system_prompt, raw_text, json_mode=True)

    try:
        data = json.loads(response.text)
    except json.JSONDecodeError as e:
        raise ValueError(f"LLM returned invalid JSON: {e}") from e

    return validate_jd_schema(data)


def extract_jd_with_usage(raw_text: str) -> tuple[JDSchema, dict[str, float | int]]:
    """
    Extract JD and return token/cost usage for the extraction call.

    Returns
    -------
    tuple of (JDSchema, usage)
    """
    from core.llm import chat_text
    from core.prompts import load_prompt

    system_prompt = load_prompt("jd_extract", version=1)
    response = chat_text(system_prompt, raw_text, json_mode=True)

    try:
        data = json.loads(response.text)
    except json.JSONDecodeError as e:
        raise ValueError(f"LLM returned invalid JSON: {e}") from e

    jd = validate_jd_schema(data)
    usage = {
        "prompt_tokens": response.prompt_tokens,
        "completion_tokens": response.completion_tokens,
        "total_tokens": response.total_tokens,
        "cost_estimate": response.cost_estimate,
        "generation_id": response.generation_id,
    }
    return jd, usage
