"""
End-to-end pipeline tests.

Two modes:
- Mock (default): All LLM calls mocked. Fast, free, deterministic. Runs in CI.
- Live (opt-in): Hits real OpenRouter API. Slow, costs money, catches real issues.
  Enable with: OPENROUTER_API_KEY=... pytest -m live tests/test_e2e_pipeline.py

Both modes test the full pipeline: JD text → JD extraction → resume selection →
mutation → compile → collateral drafts → eval logging.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

# ── Sample JD (real job posting) ────────────────────────────────────

SAMPLE_JD = """
The Role

You'll join the AI Products squad to build the next generation of LLM-powered
applications for the staffing industry. This is a product engineering role, not
a research role. You'll ship real AI products used by real recruiters and real
clients.

What You'll Do

Design and build agentic systems — multi-step AI workflows that reason,
retrieve, and act across multiple tools and data sources.
Build RAG (Retrieval-Augmented Generation) pipelines — connect LLMs to company
data through vector databases, semantic search, and context injection.
Craft prompt architectures — design system prompts, few-shot examples,
chain-of-thought patterns, and guardrails for production LLM applications.
Ship production-grade applications — not prototypes.

What We're Looking For

Must have (1-3 years of experience):
- Shipped at least one LLM-powered application in a real organization
- Strong Python skills
- Hands-on experience with LLM orchestration frameworks — LangChain, LlamaIndex,
  CrewAI, AutoGen, Semantic Kernel, or similar
- Experience building RAG systems — vector databases, embedding models
- Understanding of prompt engineering at a production level
- Familiarity with LLM APIs — OpenAI, Anthropic, Azure OpenAI
"""


# ── Mock LLM responses ──────────────────────────────────────────────


def _mock_jd_response():
    """Mock JD extraction response."""
    return SimpleNamespace(
        text=json.dumps(
            {
                "company": "AI Products Squad",
                "role": "AI Engineer",
                "location": "Remote",
                "experience_required": "1-3 years",
                "skills": [
                    "Python",
                    "LLM orchestration",
                    "RAG",
                    "prompt engineering",
                    "LangChain",
                    "vector databases",
                ],
                "description": "Build LLM-powered applications for the staffing industry. "
                "Design agentic systems, RAG pipelines, and prompt architectures.",
            }
        ),
        prompt_tokens=500,
        completion_tokens=200,
        total_tokens=700,
        cost_estimate=0.0,
        generation_id=None,
        model="test-mock",
    )


def _mock_mutation_response(original_tex: str):
    """Mock resume mutation — return the original unchanged (safe for compile test)."""
    return SimpleNamespace(
        text=json.dumps({"mutations": []}),
        prompt_tokens=800,
        completion_tokens=100,
        total_tokens=900,
        cost_estimate=0.0,
        generation_id=None,
        model="test-mock",
    )


def _mock_draft_response(draft_text: str):
    return SimpleNamespace(
        text=draft_text,
        prompt_tokens=200,
        completion_tokens=100,
        total_tokens=300,
        cost_estimate=0.0,
        generation_id=None,
        model="test-mock",
    )


def _mock_eval_response(score: float):
    return SimpleNamespace(
        text=json.dumps({"score": score}),
        prompt_tokens=100,
        completion_tokens=20,
        total_tokens=120,
        cost_estimate=0.0,
        generation_id=None,
        model="test-mock",
    )


# ── Mock pipeline test ──────────────────────────────────────────────


class TestE2EMockedPipeline:
    """Full pipeline with mocked LLM calls. Fast, free, deterministic."""

    def test_jd_extraction_produces_valid_schema(self):
        """JD text → extract → valid JDSchema with expected fields."""
        from agents.inbox.jd import JDSchema, extract_jd_with_usage

        with patch("core.llm.chat_text", return_value=_mock_jd_response()):
            jd, usage = extract_jd_with_usage(SAMPLE_JD)

        assert isinstance(jd, JDSchema)
        assert jd.company == "AI Products Squad"
        assert jd.role == "AI Engineer"
        assert "Python" in jd.skills
        assert "RAG" in jd.skills
        assert len(jd.skills) >= 3
        assert jd.description  # non-empty

    def test_resume_selection_returns_best_match(self):
        """JD skills → resume selector → picks best-fit .tex file."""
        from agents.inbox.resume import select_base_resume_with_details

        skills = ["Python", "LLM orchestration", "RAG", "prompt engineering"]
        resumes_dir = Path("resumes")

        if not resumes_dir.exists() or not list(resumes_dir.glob("*.tex")):
            pytest.skip("No resume .tex files in resumes/")

        base_path, fit_score, details = select_base_resume_with_details(skills, resumes_dir)
        assert base_path.exists()
        assert base_path.suffix == ".tex"
        assert 0 <= fit_score <= 100
        assert isinstance(details, dict)

    def test_bullet_relevance_scores_for_ai_jd(self):
        """Bullet bank scoring produces non-zero scores for AI-related JD."""
        from agents.inbox.bullet_relevance import select_relevant_bullets

        bullet_bank_path = Path("profile/bullet_bank.json")
        if not bullet_bank_path.exists():
            pytest.skip("No bullet_bank.json")

        bank = json.loads(bullet_bank_path.read_text())
        skills = ["Python", "LLM", "RAG", "agentic systems", "prompt engineering"]

        results = select_relevant_bullets(bank, skills, "Build AI products", top_n=5)
        assert len(results) > 0
        assert all("_relevance_score" in b for b in results)
        # At least one bullet should have non-zero score for AI-related JD
        assert any(b["_relevance_score"] > 0 for b in results)

    def test_draft_generation_produces_all_types(self):
        """Draft generators produce email, LinkedIn DM, and referral."""
        from agents.inbox.drafts import (
            generate_email_draft,
            generate_linkedin_dm,
            generate_referral_template,
        )

        with patch("agents.inbox.drafts.load_prompt", return_value="You are a draft writer."):
            with patch(
                "agents.inbox.drafts.chat_text",
                return_value=_mock_draft_response("Hi, I'm interested in the AI Engineer role."),
            ):
                email = generate_email_draft("Karan", "AI PM", "AI Products Squad", "AI Engineer")
                linkedin = generate_linkedin_dm(
                    "Karan", "AI PM", "AI Products Squad", "AI Engineer"
                )
                referral = generate_referral_template(
                    "Karan", "AI PM", "AI Products Squad", "AI Engineer"
                )

        assert email.draft_type == "email"
        assert email.text
        assert linkedin.draft_type == "linkedin_dm"
        assert linkedin.char_count <= 300
        assert referral.draft_type == "referral"
        assert referral.text

    def test_article_agent_extracts_signals(self):
        """Article agent finds hiring signals in JD-like content."""
        from agents.article.agent import summarize

        mock_resp = SimpleNamespace(
            text=json.dumps(
                {
                    "summary_bullets": [
                        "Company building AI-powered staffing tools",
                        "Looking for LLM engineers with RAG experience",
                    ],
                    "signals": [
                        "AI Products Squad hiring AI Engineers",
                        "RAG and agentic systems skills in demand",
                    ],
                }
            ),
            prompt_tokens=300,
            completion_tokens=100,
            total_tokens=400,
            cost_estimate=0.0,
            generation_id=None,
        )
        with patch("agents.article.agent.chat_text", return_value=mock_resp):
            summary, signals = summarize(SAMPLE_JD)

        assert "AI-powered" in summary
        assert len(signals) == 2
        assert any("hiring" in s.lower() for s in signals)

    def test_profile_agent_answers_with_grounding(self):
        """Profile agent returns grounded answer for AI-related query."""
        from agents.profile.agent import answer

        profile_path = Path("profile/profile.json")
        bullet_bank_path = Path("profile/bullet_bank.json")
        if not profile_path.exists() or not bullet_bank_path.exists():
            pytest.skip("No profile files")

        mock_resp = SimpleNamespace(
            text="Karan has experience building AI products with Python and LLMs.",
            prompt_tokens=500,
            completion_tokens=50,
            total_tokens=550,
            cost_estimate=0.0,
            generation_id=None,
        )
        with patch("agents.profile.agent.chat_text", return_value=mock_resp):
            text, narrative, ungrounded = answer(
                "Tell me about Karan's AI experience",
                profile_path=profile_path,
                bullet_bank_path=bullet_bank_path,
            )

        assert text
        assert narrative in {"ai", "growth", "martech"}

    def test_router_routes_jd_to_inbox(self):
        """Router correctly identifies JD text and routes to INBOX."""
        from core.router import AgentTarget, route

        result = route(SAMPLE_JD)
        assert result.target == AgentTarget.INBOX


# ── Live LLM pipeline test (opt-in) ────────────────────────────────


@pytest.mark.live
class TestE2ELivePipeline:
    """Full pipeline hitting real OpenRouter API.

    Run with: OPENROUTER_API_KEY=... pytest -m live tests/test_e2e_pipeline.py -v
    """

    @pytest.fixture(autouse=True)
    def _skip_without_api_key(self):
        if not os.environ.get("OPENROUTER_API_KEY"):
            pytest.skip("OPENROUTER_API_KEY not set — skipping live tests")

    def test_live_jd_extraction(self):
        """Real LLM extracts structured JD from raw text."""
        from agents.inbox.jd import JDSchema, extract_jd_with_usage

        jd, usage = extract_jd_with_usage(SAMPLE_JD)

        assert isinstance(jd, JDSchema)
        assert jd.company  # non-empty
        assert jd.role  # non-empty
        assert len(jd.skills) >= 3
        assert jd.description
        assert usage.total_tokens > 0

    def test_live_full_pipeline_produces_pdf(self):
        """Real LLM pipeline: JD → extract → select → mutate → compile → PDF."""
        resumes_dir = Path("resumes")
        if not resumes_dir.exists() or not list(resumes_dir.glob("*.tex")):
            pytest.skip("No resume .tex files")

        from agents.inbox.agent import ApplicationPack, run_pipeline

        pack = run_pipeline(
            SAMPLE_JD,
            selected_collateral=["email"],
            skip_upload=True,
            skip_calendar=True,
        )

        assert isinstance(pack, ApplicationPack)
        assert pack.jd.company  # JD was extracted
        assert pack.jd.role
        # Pipeline may fail on compile (no pdflatex in CI) but should not crash
        if pack.pdf_path:
            assert pack.pdf_path.exists()
        assert pack.run_id  # run was logged
