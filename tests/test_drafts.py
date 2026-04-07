"""Tests for agents/inbox/drafts.py — draft generation."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from agents.inbox.drafts import (
    LINKEDIN_CHAR_LIMIT,
    generate_email_draft,
    generate_linkedin_dm,
    generate_referral_template,
)


def _fake_llm_response(text: str) -> SimpleNamespace:
    return SimpleNamespace(
        text=text,
        prompt_tokens=100,
        completion_tokens=50,
        total_tokens=150,
        cost_estimate=0.01,
        generation_id=None,
    )


class TestGenerateEmailDraft:
    def test_returns_draft_result(self):
        with patch(
            "agents.inbox.drafts.chat_text",
            return_value=_fake_llm_response("Dear Hiring Manager, ..."),
        ):
            with patch(
                "agents.inbox.drafts.load_prompt",
                return_value="You are a professional email writer.",
            ):
                result = generate_email_draft("Karan", "AI PM", "Acme", "AI Engineer")

        assert result.draft_type == "email"
        assert result.text == "Dear Hiring Manager, ..."
        assert result.within_limit is True
        assert result.total_tokens == 150

    def test_strips_whitespace(self):
        with patch("agents.inbox.drafts.chat_text", return_value=_fake_llm_response("  Hello  \n")):
            with patch("agents.inbox.drafts.load_prompt", return_value="prompt"):
                result = generate_email_draft("Karan", "PM", "Co", "Role")

        assert result.text == "Hello"


class TestGenerateLinkedinDm:
    def test_within_limit(self):
        short_msg = "Hi, I noticed you're hiring for AI Engineer. I'd love to connect!"
        with patch("agents.inbox.drafts.chat_text", return_value=_fake_llm_response(short_msg)):
            with patch("agents.inbox.drafts.load_prompt", return_value="prompt"):
                result = generate_linkedin_dm("Karan", "AI PM", "Acme", "AI Engineer")

        assert result.within_limit is True
        assert result.char_count <= LINKEDIN_CHAR_LIMIT

    def test_truncates_over_limit(self):
        long_msg = "A" * 500
        with patch("agents.inbox.drafts.chat_text", return_value=_fake_llm_response(long_msg)):
            with patch("agents.inbox.drafts.load_prompt", return_value="prompt"):
                result = generate_linkedin_dm("Karan", "AI PM", "Acme", "AI Engineer")

        assert result.char_count <= LINKEDIN_CHAR_LIMIT
        assert result.text.endswith("...")
        assert result.within_limit is False


class TestGenerateReferralTemplate:
    def test_returns_draft_result(self):
        with patch(
            "agents.inbox.drafts.chat_text",
            return_value=_fake_llm_response("Hi, could you refer me?"),
        ):
            with patch("agents.inbox.drafts.load_prompt", return_value="prompt"):
                result = generate_referral_template("Karan", "AI PM", "Acme", "AI Engineer")

        assert result.draft_type == "referral"
        assert result.text == "Hi, could you refer me?"
        assert result.within_limit is True
