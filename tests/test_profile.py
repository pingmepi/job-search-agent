"""Tests for agents/profile/agent.py — Profile Agent."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agents.profile.agent import (
    answer,
    check_response_grounding,
    load_bullet_bank,
    load_profile,
    run_profile_agent,
    select_narrative,
)


@pytest.fixture
def profile_path(tmp_path: Path) -> Path:
    """Create a test profile."""
    profile = {
        "identity": {
            "name": "Karan Mandalam",
            "roles": ["AI PM", "Growth PM", "Martech PM"],
        },
        "positioning": {
            "ai": "AI product leader",
            "growth": "Growth-focused PM",
            "martech": "Martech specialist",
        },
        "allowed_tools": ["Python", "SQL"],
    }
    path = tmp_path / "profile.json"
    path.write_text(json.dumps(profile), encoding="utf-8")
    return path


@pytest.fixture
def bullet_bank_path(tmp_path: Path) -> Path:
    """Create a test bullet bank."""
    bullets = [
        {
            "id": "ai-001",
            "role_family": "ai",
            "bullet": "Built ML pipeline at Acme Corp",
            "tags": ["ml"],
        },
        {
            "id": "growth-001",
            "role_family": "growth",
            "bullet": "Drove 3x MAU growth",
            "tags": ["growth"],
        },
    ]
    path = tmp_path / "bullet_bank.json"
    path.write_text(json.dumps(bullets), encoding="utf-8")
    return path


class TestProfileLoading:
    def test_load_profile(self, profile_path: Path):
        profile = load_profile(profile_path)
        assert profile["identity"]["name"] == "Karan Mandalam"

    def test_load_bullet_bank(self, bullet_bank_path: Path):
        bank = load_bullet_bank(bullet_bank_path)
        assert len(bank) == 2
        assert bank[0]["id"] == "ai-001"


class TestNarrativeSelection:
    def test_ai_keywords(self, profile_path: Path):
        profile = load_profile(profile_path)
        assert select_narrative("Tell me about AI experience", profile) == "ai"

    def test_growth_keywords(self, profile_path: Path):
        profile = load_profile(profile_path)
        assert select_narrative("What about growth and acquisition?", profile) == "growth"

    def test_martech_keywords(self, profile_path: Path):
        profile = load_profile(profile_path)
        assert select_narrative("Martech and CRM experience", profile) == "martech"

    def test_default_fallback(self, profile_path: Path):
        profile = load_profile(profile_path)
        result = select_narrative("Generic question", profile)
        assert result == "ai"  # first role is AI PM


class TestGroundingCheck:
    def test_grounded_response(self, profile_path: Path, bullet_bank_path: Path):
        profile = load_profile(profile_path)
        bank = load_bullet_bank(bullet_bank_path)
        # Response using only profile content
        response = "Karan has experience in Python and SQL."
        claims = check_response_grounding(response, profile, bank)
        assert len(claims) == 0

    def test_ungrounded_response(self, profile_path: Path, bullet_bank_path: Path):
        profile = load_profile(profile_path)
        bank = load_bullet_bank(bullet_bank_path)
        # Response mentioning a company not in profile
        response = "Karan led a team at Stripe Finance delivering key results."
        claims = check_response_grounding(response, profile, bank)
        assert len(claims) > 0  # "Stripe Finance" should be flagged

    def test_ungrounded_metric_claim_is_flagged(self, profile_path: Path, bullet_bank_path: Path):
        profile = load_profile(profile_path)
        bank = load_bullet_bank(bullet_bank_path)
        response = "Karan improved retention by 42% at Acme Corp."
        claims = check_response_grounding(response, profile, bank)
        assert any("42%" in c or "42" in c for c in claims)

    def test_grounded_metric_claim_is_not_flagged(self, profile_path: Path, bullet_bank_path: Path):
        profile = load_profile(profile_path)
        bank = load_bullet_bank(bullet_bank_path)
        response = "Karan drove 3x MAU growth in prior work."
        claims = check_response_grounding(response, profile, bank)
        assert len(claims) == 0


class TestAnswerGrounding:
    def test_answer_returns_ungrounded_claims(
        self, profile_path: Path, bullet_bank_path: Path, monkeypatch
    ):
        class _FakeResponse:
            text = "Karan scaled Stripe Finance conversion by 50%."

        monkeypatch.setattr(
            "agents.profile.agent.chat_text", lambda *_args, **_kwargs: _FakeResponse()
        )

        response_text, narrative, ungrounded = answer(
            "Share Karan's highlights",
            profile_path=profile_path,
            bullet_bank_path=bullet_bank_path,
        )

        assert "Stripe Finance" in " ".join(ungrounded)
        assert any("50%" in c or "50" in c for c in ungrounded)
        assert narrative in {"ai", "growth", "martech"}
        assert response_text


class TestRunProfileAgent:
    def test_logs_run_and_returns_results(self, profile_path, bullet_bank_path, monkeypatch):
        """run_profile_agent() should call insert_run + complete_run and return the same tuple as answer()."""
        from unittest.mock import MagicMock

        class _FakeResponse:
            text = "Karan has experience with Python."
            total_tokens = 150
            prompt_tokens = 100
            completion_tokens = 50
            model = "test-model"
            cost_estimate = 0.0
            generation_id = None

        monkeypatch.setattr(
            "agents.profile.agent.chat_text", lambda *_args, **_kwargs: _FakeResponse()
        )
        mock_insert = MagicMock()
        mock_complete = MagicMock()
        monkeypatch.setattr("agents.profile.agent.insert_run", mock_insert)
        monkeypatch.setattr("agents.profile.agent.complete_run", mock_complete)

        response_text, narrative, ungrounded = run_profile_agent(
            "Tell me about Karan",
            profile_path=profile_path,
            bullet_bank_path=bullet_bank_path,
        )

        assert response_text
        assert narrative in {"ai", "growth", "martech"}
        mock_insert.assert_called_once()
        mock_complete.assert_called_once()
        # Verify run_id format
        call_args = mock_insert.call_args
        assert call_args[0][0].startswith("profile-")
        assert call_args[0][1] == "profile_agent"
        # Verify complete_run got tokens
        complete_kwargs = mock_complete.call_args[1]
        assert complete_kwargs["tokens_used"] == 150
        assert complete_kwargs["status"] == "completed"

    def test_logs_failure_on_exception(self, profile_path, bullet_bank_path, monkeypatch):
        """run_profile_agent() should log a failed run if the LLM call raises."""
        from unittest.mock import MagicMock

        monkeypatch.setattr(
            "agents.profile.agent.chat_text",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("LLM down")),
        )
        mock_insert = MagicMock()
        mock_complete = MagicMock()
        monkeypatch.setattr("agents.profile.agent.insert_run", mock_insert)
        monkeypatch.setattr("agents.profile.agent.complete_run", mock_complete)

        with pytest.raises(RuntimeError, match="LLM down"):
            run_profile_agent(
                "Tell me about Karan",
                profile_path=profile_path,
                bullet_bank_path=bullet_bank_path,
            )

        mock_insert.assert_called_once()
        mock_complete.assert_called_once()
        complete_kwargs = mock_complete.call_args[1]
        assert complete_kwargs["status"] == "failed"
        assert "LLM down" in complete_kwargs["errors"][0]
