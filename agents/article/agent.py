from __future__ import annotations

import json

from core.llm import chat_text

_SYSTEM_PROMPT = """You are a job search assistant. The user has sent article content.

1. Summarize the article in 3-4 concise bullet points.
2. List any job-search-relevant signals you detect — companies hiring, industry trends,
   skills in demand, notable people/roles, or funding events. If none, return an empty list.

Respond in JSON:
{
  "summary_bullets": ["...", "..."],
  "signals": ["...", "..."]
}"""


def summarize(text: str) -> tuple[str, list[str]]:
    """
    Summarize article content and extract job-search-relevant signals.
    Returns: (formatted_summary, signals)
    """
    response = chat_text(_SYSTEM_PROMPT, text, json_mode=True)
    data = json.loads(response.text)
    bullets = data.get("summary_bullets", [])
    signals = data.get("signals", [])
    summary = "\n".join(f"• {b}" for b in bullets)
    return summary, signals
