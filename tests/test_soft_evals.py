"""Tests for evals/soft.py — LLM-judged quality evaluations.

All tests mock the LLM response to avoid real API calls.
Tests cover: high/low relevance, perfect/partial/bad extraction,
edge cases (malformed JSON, missing fields, error handling).
"""

from __future__ import annotations

import json

import pytest

from core.llm import LLMResponse
from evals.soft import score_resume_relevance, score_jd_accuracy


def _llm_response(text: str) -> LLMResponse:
    """Create a fake LLMResponse with the given text."""
    return LLMResponse(
        text=text,
        model="test-model",
        prompt_tokens=10,
        completion_tokens=5,
        total_tokens=15,
        cost_estimate=0.00015,
    )


# ── Resume Relevance Tests ────────────────────────────────────────


class TestResumeRelevance:
    """Test score_resume_relevance with mocked LLM responses."""

    def test_high_relevance_score(self, monkeypatch):
        """Resume closely matching the JD should score high."""
        monkeypatch.setattr(
            "evals.soft.chat_text",
            lambda *_a, **_k: _llm_response(
                json.dumps({"score": 92, "reasoning": "Strong alignment on skills and experience"})
            ),
        )
        score = score_resume_relevance(
            "Senior ML Engineer with 5+ years Python, TensorFlow, PyTorch",
            "\\item Built TensorFlow inference pipeline\\n\\item 6 years Python ML engineering",
        )
        assert score == pytest.approx(0.92)

    def test_low_relevance_score(self, monkeypatch):
        """Resume with little JD overlap should score low."""
        monkeypatch.setattr(
            "evals.soft.chat_text",
            lambda *_a, **_k: _llm_response(
                json.dumps({"score": 15, "reasoning": "Resume is marketing-focused, JD is engineering"})
            ),
        )
        score = score_resume_relevance(
            "Backend Engineer: Go, Kubernetes, gRPC microservices",
            "\\item Managed social media campaigns\\n\\item Ran email marketing automation",
        )
        assert score == pytest.approx(0.15)

    def test_mid_range_relevance(self, monkeypatch):
        """Partial overlap should score mid-range."""
        monkeypatch.setattr(
            "evals.soft.chat_text",
            lambda *_a, **_k: _llm_response(
                json.dumps({"score": 55, "reasoning": "Some transferable skills"})
            ),
        )
        score = score_resume_relevance(
            "Product Manager with data analytics background",
            "\\item Led product roadmap\\n\\item Built SQL dashboards",
        )
        assert 0.4 <= score <= 0.7

    def test_perfect_score_clamped_to_one(self, monkeypatch):
        """Score of 100 should clamp to 1.0."""
        monkeypatch.setattr(
            "evals.soft.chat_text",
            lambda *_a, **_k: _llm_response(
                json.dumps({"score": 100, "reasoning": "Perfect match"})
            ),
        )
        score = score_resume_relevance("JD text", "Resume text")
        assert score == 1.0

    def test_score_above_100_clamped(self, monkeypatch):
        """Scores above 100 should still clamp to 1.0."""
        monkeypatch.setattr(
            "evals.soft.chat_text",
            lambda *_a, **_k: _llm_response(
                json.dumps({"score": 150, "reasoning": "overscored"})
            ),
        )
        score = score_resume_relevance("JD text", "Resume text")
        assert score == 1.0

    def test_negative_score_clamped_to_zero(self, monkeypatch):
        """Negative scores should clamp to 0.0."""
        monkeypatch.setattr(
            "evals.soft.chat_text",
            lambda *_a, **_k: _llm_response(
                json.dumps({"score": -10, "reasoning": "error"})
            ),
        )
        score = score_resume_relevance("JD text", "Resume text")
        assert score == 0.0

    def test_malformed_json_returns_zero(self, monkeypatch):
        """Malformed JSON response should return 0.0, not raise."""
        monkeypatch.setattr(
            "evals.soft.chat_text",
            lambda *_a, **_k: _llm_response("this is not valid json at all"),
        )
        score = score_resume_relevance("JD text", "Resume text")
        assert score == 0.0

    def test_missing_score_field_returns_zero(self, monkeypatch):
        """JSON without 'score' key should return 0.0."""
        monkeypatch.setattr(
            "evals.soft.chat_text",
            lambda *_a, **_k: _llm_response(
                json.dumps({"reasoning": "missing score field"})
            ),
        )
        score = score_resume_relevance("JD text", "Resume text")
        assert score == 0.0


# ── JD Extraction Accuracy Tests ──────────────────────────────────


class TestJDAccuracy:
    """Test score_jd_accuracy with mocked LLM responses."""

    def test_perfect_extraction(self, monkeypatch):
        """All fields correctly extracted should score high."""
        monkeypatch.setattr(
            "evals.soft.chat_text",
            lambda *_a, **_k: _llm_response(
                json.dumps({"score": 95, "reasoning": "All fields correctly extracted"})
            ),
        )
        score = score_jd_accuracy(
            "Google is hiring a Senior PM in Mountain View. Requirements: 5+ years PM, SQL, Python.",
            {
                "company": "Google",
                "role": "Senior PM",
                "location": "Mountain View",
                "experience_required": "5+ years",
                "skills": ["PM", "SQL", "Python"],
                "description": "Senior PM role at Google.",
            },
        )
        assert score >= 0.9

    def test_partial_extraction(self, monkeypatch):
        """Missing or wrong fields should score lower."""
        monkeypatch.setattr(
            "evals.soft.chat_text",
            lambda *_a, **_k: _llm_response(
                json.dumps({"score": 50, "reasoning": "Location wrong, skills incomplete"})
            ),
        )
        score = score_jd_accuracy(
            "Stripe is hiring an ML Engineer in SF. Python, PyTorch, Kubernetes required.",
            {
                "company": "Stripe",
                "role": "ML Engineer",
                "location": "New York",  # wrong
                "experience_required": "3 years",
                "skills": ["Python"],  # incomplete
                "description": "ML role.",
            },
        )
        assert 0.4 <= score <= 0.6

    def test_bad_extraction(self, monkeypatch):
        """Completely wrong extraction should score very low."""
        monkeypatch.setattr(
            "evals.soft.chat_text",
            lambda *_a, **_k: _llm_response(
                json.dumps({"score": 10, "reasoning": "Everything is wrong"})
            ),
        )
        score = score_jd_accuracy(
            "Netflix Senior Data Scientist in LA",
            {
                "company": "Amazon",
                "role": "Intern",
                "location": "Seattle",
                "experience_required": "0 years",
                "skills": [],
                "description": "Wrong.",
            },
        )
        assert score <= 0.2

    def test_malformed_json_returns_zero(self, monkeypatch):
        """Malformed LLM response should return 0.0."""
        monkeypatch.setattr(
            "evals.soft.chat_text",
            lambda *_a, **_k: _llm_response("not json"),
        )
        score = score_jd_accuracy("raw text", {"company": "Test"})
        assert score == 0.0

    def test_score_string_value_handled(self, monkeypatch):
        """Score returned as string should be cast correctly."""
        monkeypatch.setattr(
            "evals.soft.chat_text",
            lambda *_a, **_k: _llm_response(
                json.dumps({"score": "75", "reasoning": "string score"})
            ),
        )
        score = score_jd_accuracy("raw text", {"company": "Test"})
        assert score == pytest.approx(0.75)

    def test_non_numeric_score_returns_zero(self, monkeypatch):
        """Score that can't be cast to float should return 0.0."""
        monkeypatch.setattr(
            "evals.soft.chat_text",
            lambda *_a, **_k: _llm_response(
                json.dumps({"score": "excellent", "reasoning": "qualitative"})
            ),
        )
        score = score_jd_accuracy("raw text", {"company": "Test"})
        assert score == 0.0
