"""Tests for agents/profile/agent.py — Profile Agent."""

from __future__ import annotations

import json
import pytest
from pathlib import Path

from agents.profile.agent import (
    load_profile,
    load_bullet_bank,
    select_narrative,
    check_response_grounding,
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
        {"id": "ai-001", "role_family": "ai", "bullet": "Built ML pipeline at Acme Corp", "tags": ["ml"]},
        {"id": "growth-001", "role_family": "growth", "bullet": "Drove 3x MAU growth", "tags": ["growth"]},
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
