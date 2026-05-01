"""Shared Telegram message-length constants and utilities."""

from __future__ import annotations

TELEGRAM_MAX_MESSAGE_CHARS = 4096
TELEGRAM_SAFE_MESSAGE_CHARS = 3900
TELEGRAM_SUMMARY_RETRIES = 2
TELEGRAM_MIN_SUMMARY_CHARS = 600


def hard_truncate(text: str, limit: int) -> str:
    """Hard-truncate *text* to a strict character limit."""
    if len(text) <= limit:
        return text
    if limit <= 32:
        return text[:limit]
    suffix = f"\n\n...[truncated {len(text) - limit} chars]"
    head_limit = max(0, limit - len(suffix))
    if head_limit <= 0:
        return text[:limit]
    return text[:head_limit].rstrip() + suffix
