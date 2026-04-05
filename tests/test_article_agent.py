"""Tests for agents.article.agent.summarize()."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from agents.article.agent import summarize


def _mock_response(payload: dict) -> MagicMock:
    r = MagicMock()
    r.text = json.dumps(payload)
    return r


class TestSummarize:
    def test_returns_formatted_summary_and_signals(self):
        payload = {
            "summary_bullets": ["AI adoption is accelerating.", "OpenAI raised $6.6B."],
            "signals": ["OpenAI is hiring ML engineers.", "Large funding round signals growth."],
        }
        with patch("agents.article.agent.chat_text", return_value=_mock_response(payload)):
            summary, signals = summarize("some article text")

        assert summary == "• AI adoption is accelerating.\n• OpenAI raised $6.6B."
        assert signals == ["OpenAI is hiring ML engineers.", "Large funding round signals growth."]

    def test_empty_signals(self):
        payload = {
            "summary_bullets": ["Generic tech article with no hiring news."],
            "signals": [],
        }
        with patch("agents.article.agent.chat_text", return_value=_mock_response(payload)):
            summary, signals = summarize("some article text")

        assert signals == []
        assert "Generic tech article" in summary

    def test_missing_keys_defaults_to_empty(self):
        payload = {}
        with patch("agents.article.agent.chat_text", return_value=_mock_response(payload)):
            summary, signals = summarize("some article text")

        assert summary == ""
        assert signals == []

    def test_malformed_json_raises(self):
        bad = MagicMock()
        bad.text = "not json at all"
        with patch("agents.article.agent.chat_text", return_value=bad):
            with pytest.raises(json.JSONDecodeError):
                summarize("some article text")
