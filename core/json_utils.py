"""Shared JSON parsing utilities for LLM response handling."""

from __future__ import annotations


def extract_first_json_object(text: str) -> str | None:
    """
    Extract the first balanced JSON object from mixed text.

    Handles prefixes/suffixes and ignores braces within quoted strings.
    """
    start = text.find("{")
    if start < 0:
        return None

    depth = 0
    in_string = False
    escaped = False
    for idx in range(start, len(text)):
        ch = text[idx]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
            continue
        if ch == "{":
            depth += 1
            continue
        if ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : idx + 1]
    return None
