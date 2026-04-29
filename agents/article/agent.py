"""
Article Agent — summarizes articles and extracts job-search signals.

Responsibilities:
- Summarize article content into 3-4 bullet points
- Extract job-search-relevant signals (hiring, funding, skill trends)
- Log runs with telemetry (tokens, latency)
- Persist extracted signals for later retrieval
"""

from __future__ import annotations

import json
import logging
import time
from uuid import uuid4

from core.feedback import TASK_OUTCOME_FAIL, TASK_OUTCOME_SUCCESS, TASK_TYPE_ARTICLE, classify_error_types
from core.db import complete_run, insert_article_signals, insert_run
from core.llm import LLMResponse, chat_text

logger = logging.getLogger(__name__)

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
    summary, signals, _resp = summarize_with_telemetry(text)
    return summary, signals


def summarize_with_telemetry(text: str) -> tuple[str, list[str], LLMResponse]:
    """
    Summarize article content and return the raw LLMResponse for telemetry.
    Returns: (formatted_summary, signals, llm_response)
    """
    response = chat_text(_SYSTEM_PROMPT, text, json_mode=True)
    try:
        data = json.loads(response.text)
    except (json.JSONDecodeError, TypeError):
        logger.warning("Article agent got malformed JSON: %s", response.text[:200])
        data = {}
    bullets = data.get("summary_bullets", [])
    signals = data.get("signals", [])
    summary = "\n".join(f"• {b}" for b in bullets)
    return summary, signals, response


# ── Logged runner ────────────────────────────────────────────────


def run_article_agent(text: str) -> tuple[str, list[str], str]:
    """
    Run the article agent with full telemetry logging.

    Logs a run to the ``runs`` table with token usage and latency.
    Persists extracted signals to the ``article_signals`` table.

    Returns
    -------
    (formatted_summary, signals, run_id)
    """
    run_id = f"article-{uuid4().hex[:12]}"
    insert_run(run_id, "article_agent")

    t0 = time.monotonic()
    try:
        summary, signals, llm_resp = summarize_with_telemetry(text)
        latency_ms = int((time.monotonic() - t0) * 1000)

        complete_run(
            run_id,
            status="completed",
            tokens_used=llm_resp.total_tokens,
            latency_ms=latency_ms,
            task_type=TASK_TYPE_ARTICLE,
            task_outcome=TASK_OUTCOME_SUCCESS,
            error_types=[],
            prompt_versions=["article_summary:inline_prompt:v1"],
            models_used=[llm_resp.model],
            eval_results={
                "signal_count": len(signals),
                "bullet_count": len(summary.split("\n")),
            },
            context={"signals": signals},
        )

        if signals:
            insert_article_signals(run_id, signals)

        return summary, signals, run_id

    except Exception as exc:
        latency_ms = int((time.monotonic() - t0) * 1000)
        logger.exception("Article agent failed run_id=%s", run_id)
        complete_run(
            run_id,
            status="failed",
            latency_ms=latency_ms,
            errors=[str(exc)],
            task_type=TASK_TYPE_ARTICLE,
            task_outcome=TASK_OUTCOME_FAIL,
            error_types=classify_error_types([str(exc)]),
            prompt_versions=["article_summary:inline_prompt:v1"],
        )
        raise
