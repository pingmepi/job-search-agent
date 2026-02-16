"""
Soft evaluation functions (PRD §7).

These are quality metrics evaluated by LLM judges.
They don't gate CI but provide quality signals.
"""

from __future__ import annotations

from core.llm import chat_text


def score_resume_relevance(
    jd_text: str,
    resume_text: str,
    *,
    model: str | None = None,
) -> float:
    """
    Use an LLM judge to score how relevant the resume is to the JD.

    Returns a score from 0.0 to 1.0.
    """
    system = """\
You are a resume relevance evaluator. Given a job description and a resume, \
score how well the resume aligns with the role on a scale of 0 to 100.

Return ONLY a JSON object: {"score": <number>, "reasoning": "<brief explanation>"}
"""
    user_msg = f"JOB DESCRIPTION:\n{jd_text}\n\nRESUME:\n{resume_text}"

    response = chat_text(system, user_msg, model=model, json_mode=True)

    import json
    try:
        data = json.loads(response.text)
        score = float(data.get("score", 0))
        return min(max(score / 100.0, 0.0), 1.0)
    except (json.JSONDecodeError, ValueError):
        return 0.0


def score_jd_accuracy(
    raw_text: str,
    extracted_jd: dict,
    *,
    model: str | None = None,
) -> float:
    """
    Use an LLM judge to score how accurately the JD was extracted.

    Returns a score from 0.0 to 1.0.
    """
    import json

    system = """\
You are a data extraction accuracy evaluator. Given raw job description text \
and the structured extraction result, score the extraction accuracy from 0 to 100.

Check:
1. Company name correct?
2. Role title correct?
3. Location correct?
4. Skills comprehensive?
5. Description accurate summary?

Return ONLY a JSON object: {"score": <number>, "reasoning": "<brief explanation>"}
"""
    user_msg = (
        f"RAW TEXT:\n{raw_text}\n\n"
        f"EXTRACTION:\n{json.dumps(extracted_jd, indent=2)}"
    )

    response = chat_text(system, user_msg, model=model, json_mode=True)

    try:
        data = json.loads(response.text)
        score = float(data.get("score", 0))
        return min(max(score / 100.0, 0.0), 1.0)
    except (json.JSONDecodeError, ValueError):
        return 0.0
