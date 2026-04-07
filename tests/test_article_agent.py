"""Tests for agents.article.agent — summarize() and run_article_agent()."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from agents.article.agent import run_article_agent, summarize


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

    def test_malformed_json_returns_empty(self):
        bad = MagicMock()
        bad.text = "not json at all"
        with patch("agents.article.agent.chat_text", return_value=bad):
            summary, signals = summarize("some article text")
        assert summary == ""
        assert signals == []


def _mock_llm_response(payload: dict) -> MagicMock:
    """Create a mock LLMResponse with token fields."""
    r = MagicMock()
    r.text = json.dumps(payload)
    r.total_tokens = 200
    r.prompt_tokens = 150
    r.completion_tokens = 50
    r.model = "test-model"
    r.cost_estimate = 0.0
    r.generation_id = None
    return r


class TestRunArticleAgent:
    def test_logs_run_and_returns_results(self):
        payload = {
            "summary_bullets": ["AI adoption rising."],
            "signals": ["OpenAI hiring engineers."],
        }
        mock_insert = MagicMock()
        mock_complete = MagicMock()
        mock_signals = MagicMock()

        with (
            patch("agents.article.agent.chat_text", return_value=_mock_llm_response(payload)),
            patch("agents.article.agent.insert_run", mock_insert),
            patch("agents.article.agent.complete_run", mock_complete),
            patch("agents.article.agent.insert_article_signals", mock_signals),
        ):
            summary, signals, run_id = run_article_agent("some article")

        assert "AI adoption rising" in summary
        assert signals == ["OpenAI hiring engineers."]
        assert run_id.startswith("article-")

        mock_insert.assert_called_once()
        assert mock_insert.call_args[0][1] == "article_agent"

        mock_complete.assert_called_once()
        assert mock_complete.call_args[1]["status"] == "completed"
        assert mock_complete.call_args[1]["tokens_used"] == 200

        mock_signals.assert_called_once_with(run_id, ["OpenAI hiring engineers."])

    def test_skips_signal_persistence_when_empty(self):
        payload = {"summary_bullets": ["Generic article."], "signals": []}
        mock_signals = MagicMock()

        with (
            patch("agents.article.agent.chat_text", return_value=_mock_llm_response(payload)),
            patch("agents.article.agent.insert_run", MagicMock()),
            patch("agents.article.agent.complete_run", MagicMock()),
            patch("agents.article.agent.insert_article_signals", mock_signals),
        ):
            summary, signals, run_id = run_article_agent("some article")

        assert signals == []
        mock_signals.assert_not_called()

    def test_logs_failure_on_exception(self):
        mock_insert = MagicMock()
        mock_complete = MagicMock()

        def _boom(*args, **kwargs):
            raise RuntimeError("LLM down")

        with (
            patch("agents.article.agent.chat_text", side_effect=_boom),
            patch("agents.article.agent.insert_run", mock_insert),
            patch("agents.article.agent.complete_run", mock_complete),
            patch("agents.article.agent.insert_article_signals", MagicMock()),
        ):
            with pytest.raises(RuntimeError, match="LLM down"):
                run_article_agent("some article")

        mock_insert.assert_called_once()
        mock_complete.assert_called_once()
        assert mock_complete.call_args[1]["status"] == "failed"
        assert "LLM down" in mock_complete.call_args[1]["errors"][0]
