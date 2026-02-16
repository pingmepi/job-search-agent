"""Tests for core/router.py — deterministic routing."""

from __future__ import annotations

import pytest

from core.router import AgentTarget, route


class TestImageRouting:
    def test_image_routes_to_inbox(self):
        result = route(text=None, has_image=True)
        assert result.target == AgentTarget.INBOX

    def test_image_with_text_still_routes_to_inbox(self):
        result = route(text="Here's a JD", has_image=True)
        assert result.target == AgentTarget.INBOX


class TestURLRouting:
    def test_url_routes_to_inbox(self):
        result = route("Check this out https://jobs.lever.co/company/12345")
        assert result.target == AgentTarget.INBOX

    def test_http_url(self):
        result = route("http://example.com/job")
        assert result.target == AgentTarget.INBOX


class TestProfileRouting:
    @pytest.mark.parametrize("msg", [
        "Tell me about Karan",
        "What is Karan's background?",
        "Who is Karan?",
        "Can you share a bio?",
        "Karan's experience in AI",
        "Karan's skills",
    ])
    def test_profile_keywords(self, msg: str):
        result = route(msg)
        assert result.target == AgentTarget.PROFILE


class TestFollowUpRouting:
    @pytest.mark.parametrize("msg", [
        "Any follow up needed?",
        "Check follow-up status",
        "Show me pending applications for nudge",
    ])
    def test_followup_keywords(self, msg: str):
        result = route(msg)
        assert result.target == AgentTarget.FOLLOWUP


class TestJDRouting:
    def test_jd_like_content(self):
        jd_text = """
        About the role: We are looking for a Product Manager.
        Responsibilities include leading product strategy.
        Requirements: 3+ years of experience required.
        """
        result = route(jd_text)
        assert result.target == AgentTarget.INBOX

    def test_minimal_jd_indicators(self):
        result = route("Responsibilities: manage team. Requirements: 5 years")
        assert result.target == AgentTarget.INBOX

    def test_curly_apostrophe_jd_headers(self):
        msg = """
        About the job
        What you’ll do?
        Own outcomes and product roadmap.

        What we’re looking for:
        3+ years of experience in product management.
        """
        result = route(msg)
        assert result.target == AgentTarget.INBOX


class TestAmbiguousRouting:
    def test_random_text(self):
        result = route("Hello, how are you?")
        assert result.target == AgentTarget.CLARIFY

    def test_empty_text(self):
        result = route("")
        assert result.target == AgentTarget.CLARIFY

    def test_no_input(self):
        result = route(text=None, has_image=False)
        assert result.target == AgentTarget.CLARIFY
