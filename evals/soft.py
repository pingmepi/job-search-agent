"""
Soft evaluation functions (PRD §7).

These are quality metrics evaluated by LLM judges.
They don't gate CI but provide quality signals.

Judge prompts live in core/prompts/eval_*_v1.txt (versioned, diffable).
Multi-run averaging reduces LLM judge variance.
"""

from __future__ import annotations

import json
import statistics

from core.llm import chat_text
from core.prompts import load_prompt

# Default number of repeat runs for averaging LLM judge scores.
# Higher values reduce variance but cost more tokens.
DEFAULT_REPEAT = 3


def _single_score(
    system: str,
    user_msg: str,
    *,
    model: str | None = None,
) -> float:
    """Run one LLM judge call and extract a 0–1 score."""
    response = chat_text(system, user_msg, model=model, json_mode=True)
    try:
        data = json.loads(response.text)
        score = float(data.get("score", 0))
        return min(max(score / 100.0, 0.0), 1.0)
    except (json.JSONDecodeError, ValueError):
        return 0.0


def score_resume_relevance(
    jd_text: str,
    resume_text: str,
    *,
    model: str | None = None,
    repeat: int = DEFAULT_REPEAT,
) -> float:
    """
    Use an LLM judge to score how relevant the resume is to the JD.

    Runs ``repeat`` times and returns the median to reduce judge variance.
    Returns a score from 0.0 to 1.0.
    """
    system = load_prompt("eval_resume_relevance", version=1)
    user_msg = f"JOB DESCRIPTION:\n{jd_text}\n\nRESUME:\n{resume_text}"

    scores = [
        _single_score(system, user_msg, model=model) for _ in range(repeat)
    ]
    return round(statistics.median(scores), 4)


def score_jd_accuracy(
    raw_text: str,
    extracted_jd: dict,
    *,
    model: str | None = None,
    repeat: int = DEFAULT_REPEAT,
) -> float:
    """
    Use an LLM judge to score how accurately the JD was extracted.

    Runs ``repeat`` times and returns the median to reduce judge variance.
    Returns a score from 0.0 to 1.0.
    """
    system = load_prompt("eval_jd_accuracy", version=1)
    user_msg = f"RAW TEXT:\n{raw_text}\n\nEXTRACTION:\n{json.dumps(extracted_jd, indent=2)}"

    scores = [
        _single_score(system, user_msg, model=model) for _ in range(repeat)
    ]
    return round(statistics.median(scores), 4)
