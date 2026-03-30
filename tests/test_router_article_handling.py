"""Focused tests for deterministic article/ambiguous routing."""

from __future__ import annotations

from core.router import AgentTarget, route


def test_article_like_text_routes_to_article() -> None:
    result = route(
        "Published article by author with newsletter opinion. "
        "Read more and subscribe for updates on medium.com."
    )
    assert result.target == AgentTarget.ARTICLE


def test_ambiguous_non_job_text_routes_to_ambiguous_non_job() -> None:
    result = route("Can you summarize this thread for me?")
    assert result.target == AgentTarget.AMBIGUOUS_NON_JOB
