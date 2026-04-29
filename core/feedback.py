"""Helpers for normalized run feedback and reporting metadata."""

from __future__ import annotations

from collections import Counter
from typing import Any

ERROR_TYPE_TOOL_AUTH = "tool_auth"
ERROR_TYPE_TOOL_TIMEOUT = "tool_timeout"
ERROR_TYPE_PARSE_ERROR = "parse_error"
ERROR_TYPE_BAD_REASONING = "bad_reasoning"
ERROR_TYPE_MISSING_CONTEXT = "missing_context"
ERROR_TYPE_UNSAFE_ACTION_BLOCKED = "unsafe_action_blocked"
ERROR_TYPE_EXTERNAL_DEPENDENCY = "external_dependency"
ERROR_TYPE_UNKNOWN = "unknown"

TASK_OUTCOME_SUCCESS = "success"
TASK_OUTCOME_PARTIAL = "partial"
TASK_OUTCOME_FAIL = "fail"

TASK_TYPE_INBOX_APPLY = "inbox_apply"
TASK_TYPE_FOLLOWUP = "followup"
TASK_TYPE_ARTICLE = "article"
TASK_TYPE_PROFILE = "profile"

FEEDBACK_LABEL_HELPFUL = "helpful"
FEEDBACK_LABEL_NOT_HELPFUL = "not_helpful"

FEEDBACK_REASON_WRONG = "wrong"
FEEDBACK_REASON_INCOMPLETE = "incomplete"
FEEDBACK_REASON_RISKY = "risky"
FEEDBACK_REASON_OTHER = "other"

VALID_ERROR_TYPES = {
    ERROR_TYPE_TOOL_AUTH,
    ERROR_TYPE_TOOL_TIMEOUT,
    ERROR_TYPE_PARSE_ERROR,
    ERROR_TYPE_BAD_REASONING,
    ERROR_TYPE_MISSING_CONTEXT,
    ERROR_TYPE_UNSAFE_ACTION_BLOCKED,
    ERROR_TYPE_EXTERNAL_DEPENDENCY,
    ERROR_TYPE_UNKNOWN,
}

VALID_TASK_OUTCOMES = {
    TASK_OUTCOME_SUCCESS,
    TASK_OUTCOME_PARTIAL,
    TASK_OUTCOME_FAIL,
}

VALID_TASK_TYPES = {
    TASK_TYPE_INBOX_APPLY,
    TASK_TYPE_FOLLOWUP,
    TASK_TYPE_ARTICLE,
    TASK_TYPE_PROFILE,
}

VALID_FEEDBACK_LABELS = {
    FEEDBACK_LABEL_HELPFUL,
    FEEDBACK_LABEL_NOT_HELPFUL,
}

VALID_FEEDBACK_REASONS = {
    FEEDBACK_REASON_WRONG,
    FEEDBACK_REASON_INCOMPLETE,
    FEEDBACK_REASON_RISKY,
    FEEDBACK_REASON_OTHER,
}


def unique_in_order(values: list[str] | None) -> list[str]:
    """Return distinct non-empty strings, preserving first occurrence order."""
    seen: set[str] = set()
    result: list[str] = []
    for value in values or []:
        normalized = str(value or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def classify_error_type(error_text: str) -> str:
    """Map a raw error string into a normalized error type."""
    text = (error_text or "").strip().lower()
    if not text:
        return ERROR_TYPE_UNKNOWN
    if "unauthorized" in text or "forbidden" in text or "auth" in text or "oauth" in text:
        return ERROR_TYPE_TOOL_AUTH
    if "timeout" in text or "timed out" in text:
        return ERROR_TYPE_TOOL_TIMEOUT
    if "json" in text or "parse" in text or "schema" in text or "decode" in text:
        return ERROR_TYPE_PARSE_ERROR
    if "missing" in text or "not found" in text or "no editable regions" in text:
        return ERROR_TYPE_MISSING_CONTEXT
    if "unsafe" in text or "blocked" in text or "forbidden claim" in text:
        return ERROR_TYPE_UNSAFE_ACTION_BLOCKED
    if (
        "rate limit" in text
        or "too many requests" in text
        or "connection" in text
        or "dns" in text
        or "temporarily unavailable" in text
        or "server error" in text
        or "provider returned error" in text
        or "operation not permitted" in text
    ):
        return ERROR_TYPE_EXTERNAL_DEPENDENCY
    if "halluc" in text or "bad reasoning" in text or "invalid output" in text:
        return ERROR_TYPE_BAD_REASONING
    return ERROR_TYPE_UNKNOWN


def classify_error_types(errors: list[str] | None) -> list[str]:
    """Return one normalized error type per raw error string, preserving order."""
    return [classify_error_type(err) for err in (errors or [])]


def derive_task_outcome(
    *,
    status: str,
    eval_results: dict[str, Any] | None = None,
    errors: list[str] | None = None,
) -> str:
    """Derive success/partial/fail from existing pipeline signals."""
    normalized_status = (status or "").strip().lower()
    results = eval_results or {}
    has_errors = bool(errors)
    has_artifact = bool(results.get("compile_success"))
    used_fallback = bool(
        results.get("compile_rollback_used") or results.get("truthfulness_fallback_used")
    )

    if normalized_status == "failed":
        return TASK_OUTCOME_FAIL
    if has_artifact and not has_errors and not used_fallback:
        return TASK_OUTCOME_SUCCESS
    if has_artifact or used_fallback or (normalized_status == "completed" and has_errors):
        return TASK_OUTCOME_PARTIAL
    return TASK_OUTCOME_FAIL


def summarize_error_types(error_types: list[str] | None) -> Counter[str]:
    """Count normalized error types, ignoring invalid values."""
    counts: Counter[str] = Counter()
    for error_type in error_types or []:
        if error_type in VALID_ERROR_TYPES:
            counts[error_type] += 1
    return counts
