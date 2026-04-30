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
import re
import time
from dataclasses import dataclass, replace
from typing import Any

from core.json_utils import extract_first_json_object as _extract_first_json_object


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


def _is_transient_llm_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    transient_markers = (
        "rate limit",
        "too many requests",
        "429",
        "timeout",
        "timed out",
        "connection",
        "temporarily unavailable",
        "server error",
        "503",
        "502",
        "504",
    )
    return any(marker in msg for marker in transient_markers)


def _parse_json_object_from_llm_text(text: str) -> dict[str, Any]:
    """
    Parse a JSON object from common LLM response formats.

    Supported forms:
    - pure JSON object
    - fenced JSON block
    - prefixed/suffixed text containing one JSON object
    """
    candidate = (text or "").strip()
    if not candidate:
        raise ValueError("LLM returned empty response.")

    try:
        parsed = json.loads(candidate)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", candidate, flags=re.IGNORECASE)
    if fenced:
        block = fenced.group(1).strip()
        try:
            parsed = json.loads(block)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

    extracted = _extract_first_json_object(candidate)
    if extracted:
        try:
            parsed = json.loads(extracted)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError as exc:
            raise ValueError(f"LLM returned invalid JSON object: {exc}") from exc

    snippet = candidate[:180].replace("\n", " ")
    raise ValueError(f"LLM response did not contain a parseable JSON object. Preview: {snippet!r}")


def _extract_by_patterns(text: str, patterns: list[str]) -> str:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE)
        if not match:
            continue
        value = (match.group(1) or "").strip(" -:\t")
        if value:
            return value
    return ""


def _fill_missing_required_fields(data: dict[str, Any], raw_text: str) -> dict[str, Any]:
    """
    Backfill required JD fields when LLM output leaves them blank.

    Keeps strict schema validation but tries deterministic extraction first.
    """
    normalized = dict(data or {})
    text = raw_text or ""

    company = str(normalized.get("company", "") or "").strip()
    role = str(normalized.get("role", "") or "").strip()

    if not company:
        company = _extract_by_patterns(
            text,
            [
                r"^\s*(?:company|organization|employer)\s*[:\-]\s*(.+)$",
                r"\b([A-Z][A-Za-z0-9&.\-]*(?:\s+(?!is\b)[A-Z][A-Za-z0-9&.\-]*){0,5})\s+is\s+hiring\b",
                r"\b([A-Z][A-Za-z0-9&.\-]*(?:\s+[A-Z][A-Za-z0-9&.\-]*){0,5})\s+hiring\b",
                r"\bat\s+([A-Z][A-Za-z0-9&.\-]*(?:\s+[A-Z][A-Za-z0-9&.\-]*){0,5})\b",
            ],
        )

    if not role:
        role = _extract_by_patterns(
            text,
            [
                r"^\s*(?:job title|title|role|position)\s*[:\-]\s*(.+)$",
                r"^\s*([A-Z][A-Za-z0-9/\-+&() ]{3,80}(?:Engineer|Developer|Manager|Analyst|Scientist|Designer|Lead|Specialist|Consultant|Director|Architect))\s*$",
                r"hiring\s+(?:for\s+)?(?:an?\s+)?([A-Z][A-Za-z0-9/\-+&() ]{3,80})",
            ],
        )

    normalized["company"] = company or "Unknown Company"
    normalized["role"] = role or "Unknown Role"
    return normalized


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
    data = _parse_json_object_from_llm_text(response.text)
    normalized = _fill_missing_required_fields(data, raw_text)
    return validate_jd_schema(normalized)


def extract_jd_with_usage(raw_text: str) -> tuple[JDSchema, dict[str, float | int]]:
    """
    Extract JD and return token/cost usage for the extraction call.

    Returns
    -------
    tuple of (JDSchema, usage)
    """
    from core.llm import chat_text
    from core.prompts import load_prompt

    system_prompt = load_prompt("jd_extract", version=2)
    response = None
    last_error: Exception | None = None
    for attempt in range(1, 4):
        try:
            response = chat_text(system_prompt, raw_text, json_mode=True)
            data = _parse_json_object_from_llm_text(response.text)
            normalized = _fill_missing_required_fields(data, raw_text)
            jd = validate_jd_schema(normalized)
            break
        except Exception as exc:
            last_error = exc
            is_retryable = _is_transient_llm_error(exc) or isinstance(exc, ValueError)
            if attempt < 3 and is_retryable:
                time.sleep(0.2 * attempt)
                continue
            raise
    else:
        if last_error:
            raise last_error
        raise RuntimeError("JD extraction failed without a concrete error.")

    # If skills came back empty on a non-trivial JD, retry ONCE with a stronger
    # nudge. Skill-sparse extraction is the dominant cause of zero-fit-score
    # resume selection (see run-144b1afaef4a RCA).
    if not jd.skills and len(raw_text or "") > 200:
        nudge = (
            "Your previous extraction returned an empty `skills` array. "
            "Re-read the JD carefully. Extract at least 3 skills covering tools, "
            "methodologies, domains, AND functional responsibilities. The JD may "
            "be in a non-English language — extract regardless of source language. "
            "Return the same JSON schema."
        )
        try:
            retry_response = chat_text(
                system_prompt,
                f"{raw_text}\n\n---\n{nudge}",
                json_mode=True,
            )
            # Always aggregate token usage across both attempts so telemetry stays
            # honest, regardless of whether the retry recovered skills.
            response = replace(
                response,
                text=retry_response.text,
                prompt_tokens=response.prompt_tokens + retry_response.prompt_tokens,
                completion_tokens=response.completion_tokens + retry_response.completion_tokens,
                total_tokens=response.total_tokens + retry_response.total_tokens,
                cost_estimate=response.cost_estimate + retry_response.cost_estimate,
                generation_id=retry_response.generation_id or response.generation_id,
            )
            retry_data = _parse_json_object_from_llm_text(retry_response.text)
            retry_normalized = _fill_missing_required_fields(retry_data, raw_text)
            retry_jd = validate_jd_schema(retry_normalized)
            if retry_jd.skills:
                jd = retry_jd
        except Exception as retry_err:
            # Retry is a best-effort enhancement; do not fail the run if it errors.
            import logging as _logging

            _logging.getLogger(__name__).warning(
                "JD skills-empty retry failed (non-fatal): %s", retry_err
            )

    assert response is not None
    usage = {
        "prompt_tokens": response.prompt_tokens,
        "completion_tokens": response.completion_tokens,
        "total_tokens": response.total_tokens,
        "cost_estimate": response.cost_estimate,
        "generation_id": response.generation_id,
        "model": response.model,
    }
    return jd, usage
