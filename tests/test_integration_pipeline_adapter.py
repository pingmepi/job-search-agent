"""Integration tests for inbox pipeline + Telegram adapter with mocked dependencies."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import psycopg2
import psycopg2.extras
import pytest

from agents.inbox.agent import run_pipeline
from agents.inbox.jd import JDSchema
from core.router import AgentTarget, RouteResult


def _response(text: str) -> SimpleNamespace:
    return SimpleNamespace(
        text=text,
        prompt_tokens=0,
        completion_tokens=0,
        total_tokens=0,
        cost_estimate=0.0,
    )


def test_run_pipeline_persists_job_and_run_with_mocks(db, tmp_path: Path, monkeypatch) -> None:
    runs_dir = tmp_path / "runs"
    profile_path = tmp_path / "profile.json"
    bullet_bank_path = tmp_path / "bullet_bank.json"
    base_resume = tmp_path / "base.tex"

    profile_path.write_text(
        json.dumps(
            {
                "identity": {"name": "Karan"},
                "positioning": {"ai": "Product Manager"},
            }
        ),
        encoding="utf-8",
    )
    bullet_bank_path.write_text("[]", encoding="utf-8")
    base_resume.write_text(
        "\\documentclass{article}\n\\begin{document}\nHello\n\\end{document}\n",
        encoding="utf-8",
    )

    fake_settings = SimpleNamespace(
        database_url=db,
        runs_dir=runs_dir,
        resumes_dir=tmp_path,
        profile_path=profile_path,
        bullet_bank_path=bullet_bank_path,
        max_cost_per_job=1.0,
    )

    monkeypatch.setattr("agents.inbox.agent.get_settings", lambda: fake_settings)
    monkeypatch.setattr("core.db.get_settings", lambda: fake_settings)
    monkeypatch.setattr("evals.logger.get_settings", lambda: fake_settings)

    jd = JDSchema(
        company="Acme Corp",
        role="AI PM",
        location="Remote",
        experience_required="5 years",
        skills=["python"],
        description="Own AI product roadmap.",
    )
    monkeypatch.setattr(
        "agents.inbox.executor.extract_jd_with_usage",
        lambda _text: (
            jd,
            {
                "prompt_tokens": 5,
                "completion_tokens": 7,
                "total_tokens": 12,
                "cost_estimate": 0.00012,
            },
        ),
    )
    monkeypatch.setattr(
        "agents.inbox.executor.select_base_resume_with_details",
        lambda *_args, **_kwargs: (
            base_resume,
            0.75,
            {"selected_resume": base_resume.name, "normalized_score": 0.75},
        ),
    )

    def _fake_compile(_tex_path: Path, out_dir: Path) -> Path:
        pdf_path = out_dir / "out.pdf"
        pdf_path.write_bytes(b"%PDF-1.4\n%fake\n")
        return pdf_path

    monkeypatch.setattr("agents.inbox.executor.compile_latex", _fake_compile)

    monkeypatch.setattr(
        "agents.inbox.drafts.generate_email_draft", lambda *_args, **_kwargs: _response("email")
    )
    monkeypatch.setattr(
        "agents.inbox.drafts.generate_linkedin_dm", lambda *_args, **_kwargs: _response("linkedin")
    )
    monkeypatch.setattr(
        "agents.inbox.drafts.generate_referral_template",
        lambda *_args, **_kwargs: _response("referral"),
    )

    monkeypatch.setattr("evals.soft.score_resume_relevance", lambda *_a, **_k: 0.8)
    monkeypatch.setattr("evals.soft.score_jd_accuracy", lambda *_a, **_k: 0.9)

    pack = run_pipeline(
        "raw jd text",
        selected_collateral=["email", "linkedin", "referral"],
        skip_upload=True,
        skip_calendar=True,
    )

    assert pack.job_id is not None
    assert pack.run_id is not None
    assert pack.pdf_path is not None and pack.pdf_path.exists()
    assert pack.eval_results["compile_success"] is True
    assert pack.eval_results["selected_collateral"] == ["email", "linkedin", "referral"]
    assert set(pack.eval_results["generated_collateral"]) == {"email", "linkedin", "referral"}
    assert pack.eval_results["llm_total_tokens"] > 0
    assert "llm_usage_breakdown" in pack.eval_results
    assert "keyword_coverage" in pack.eval_results
    assert pack.eval_results["telegram_draft_length_all_ok"] is True
    assert pack.eval_results["telegram_draft_length_ok"] == {
        "email": True,
        "linkedin": True,
        "referral": True,
    }
    assert "telegram_draft_audit" in pack.eval_results
    assert (runs_dir / "artifacts" / pack.run_id / "job_extraction.json").exists()
    assert (runs_dir / "artifacts" / pack.run_id / "resume_output.json").exists()
    assert (runs_dir / "artifacts" / pack.run_id / "eval_output.json").exists()

    conn = psycopg2.connect(db, cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) AS cnt FROM jobs")
        jobs_count = cur.fetchone()["cnt"]
        cur.execute("SELECT fit_score, user_vetted FROM jobs LIMIT 1")
        job_row = cur.fetchone()
        cur.execute(
            "SELECT job_id, status, eval_results, context_json FROM runs WHERE run_id = %s",
            (pack.run_id,),
        )
        run_row = cur.fetchone()
    finally:
        conn.close()

    assert jobs_count == 1
    assert job_row["fit_score"] == 75
    assert job_row["user_vetted"] == 0
    assert run_row is not None
    assert run_row["job_id"] == pack.job_id
    assert run_row["status"] == "completed"
    assert json.loads(run_row["eval_results"])["compile_success"] is True
    context = json.loads(run_row["context_json"])
    assert "artifact_paths" in context
    assert "job_extraction" in context["artifact_paths"]
    assert context["final_collateral_drafts"]["email"] == "email"
    assert context["final_collateral_drafts"]["linkedin"] == "linkedin"
    assert context["final_collateral_drafts"]["referral"] == "referral"
    assert "telegram_draft_audit" in context


def test_run_pipeline_logs_and_evals_condensed_final_draft_text(
    db, tmp_path: Path, monkeypatch
) -> None:
    runs_dir = tmp_path / "runs"
    profile_path = tmp_path / "profile.json"
    bullet_bank_path = tmp_path / "bullet_bank.json"
    base_resume = tmp_path / "base.tex"

    profile_path.write_text(
        json.dumps(
            {
                "identity": {"name": "Karan"},
                "positioning": {"ai": "Product Manager"},
            }
        ),
        encoding="utf-8",
    )
    bullet_bank_path.write_text("[]", encoding="utf-8")
    base_resume.write_text(
        "\\documentclass{article}\n\\begin{document}\nHello\n\\end{document}\n",
        encoding="utf-8",
    )

    fake_settings = SimpleNamespace(
        database_url=db,
        runs_dir=runs_dir,
        resumes_dir=tmp_path,
        profile_path=profile_path,
        bullet_bank_path=bullet_bank_path,
        max_cost_per_job=1.0,
    )

    monkeypatch.setattr("agents.inbox.agent.get_settings", lambda: fake_settings)
    monkeypatch.setattr("core.db.get_settings", lambda: fake_settings)
    monkeypatch.setattr("evals.logger.get_settings", lambda: fake_settings)

    jd = JDSchema(
        company="Acme Corp",
        role="AI PM",
        location="Remote",
        experience_required="5 years",
        skills=["python"],
        description="Own AI product roadmap.",
    )
    monkeypatch.setattr(
        "agents.inbox.executor.extract_jd_with_usage",
        lambda _text: (
            jd,
            {
                "prompt_tokens": 5,
                "completion_tokens": 7,
                "total_tokens": 12,
                "cost_estimate": 0.00012,
            },
        ),
    )
    monkeypatch.setattr(
        "agents.inbox.executor.select_base_resume_with_details",
        lambda *_args, **_kwargs: (
            base_resume,
            0.75,
            {"selected_resume": base_resume.name, "normalized_score": 0.75},
        ),
    )

    def _fake_compile(_tex_path: Path, out_dir: Path) -> Path:
        pdf_path = out_dir / "out.pdf"
        pdf_path.write_bytes(b"%PDF-1.4\n%fake\n")
        return pdf_path

    monkeypatch.setattr("agents.inbox.executor.compile_latex", _fake_compile)

    very_long_email = "E" * 5200
    monkeypatch.setattr(
        "agents.inbox.drafts.generate_email_draft",
        lambda *_args, **_kwargs: _response(very_long_email),
    )
    monkeypatch.setattr(
        "agents.inbox.drafts.generate_linkedin_dm", lambda *_args, **_kwargs: _response("linkedin")
    )
    monkeypatch.setattr(
        "agents.inbox.drafts.generate_referral_template",
        lambda *_args, **_kwargs: _response("referral"),
    )
    monkeypatch.setattr(
        "core.llm.chat_text",
        lambda *_args, **_kwargs: SimpleNamespace(
            text="condensed email",
            prompt_tokens=3,
            completion_tokens=2,
            total_tokens=5,
            cost_estimate=0.0,
            generation_id=None,
            model="test-model",
        ),
    )

    monkeypatch.setattr("evals.soft.score_resume_relevance", lambda *_a, **_k: 0.8)
    monkeypatch.setattr("evals.soft.score_jd_accuracy", lambda *_a, **_k: 0.9)

    pack = run_pipeline(
        "raw jd text",
        selected_collateral=["email", "linkedin", "referral"],
        skip_upload=True,
        skip_calendar=True,
    )

    assert pack.email_draft == "condensed email"
    assert pack.eval_results["telegram_draft_length_all_ok"] is True
    assert pack.eval_results["telegram_draft_length_ok"]["email"] is True
    assert pack.eval_results["telegram_draft_audit"]["email"]["transformed"] is True

    conn = psycopg2.connect(db, cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT eval_results, context_json FROM runs WHERE run_id = %s",
            (pack.run_id,),
        )
        run_row = cur.fetchone()
    finally:
        conn.close()

    assert run_row is not None
    eval_results = json.loads(run_row["eval_results"])
    assert eval_results["telegram_draft_audit"]["email"]["transformed"] is True
    context = json.loads(run_row["context_json"])
    assert context["final_collateral_drafts"]["email"] == "condensed email"


def test_run_pipeline_persists_user_vetted_when_requested(db, tmp_path: Path, monkeypatch) -> None:
    runs_dir = tmp_path / "runs"
    profile_path = tmp_path / "profile.json"
    bullet_bank_path = tmp_path / "bullet_bank.json"
    base_resume = tmp_path / "base.tex"

    profile_path.write_text(
        json.dumps(
            {
                "identity": {"name": "Karan"},
                "positioning": {"ai": "Product Manager"},
            }
        ),
        encoding="utf-8",
    )
    bullet_bank_path.write_text("[]", encoding="utf-8")
    base_resume.write_text(
        "\\documentclass{article}\n\\begin{document}\nHello\n\\end{document}\n",
        encoding="utf-8",
    )

    fake_settings = SimpleNamespace(
        database_url=db,
        runs_dir=runs_dir,
        resumes_dir=tmp_path,
        profile_path=profile_path,
        bullet_bank_path=bullet_bank_path,
        max_cost_per_job=1.0,
    )

    monkeypatch.setattr("agents.inbox.agent.get_settings", lambda: fake_settings)
    monkeypatch.setattr("core.db.get_settings", lambda: fake_settings)
    monkeypatch.setattr("evals.logger.get_settings", lambda: fake_settings)

    jd = JDSchema(
        company="VettedCo",
        role="Product Manager",
        location="Remote",
        experience_required="5 years",
        skills=["python"],
        description="Own AI product roadmap.",
    )
    monkeypatch.setattr(
        "agents.inbox.executor.extract_jd_with_usage",
        lambda _text: (
            jd,
            {
                "prompt_tokens": 5,
                "completion_tokens": 7,
                "total_tokens": 12,
                "cost_estimate": 0.00012,
            },
        ),
    )
    monkeypatch.setattr(
        "agents.inbox.executor.select_base_resume_with_details",
        lambda *_args, **_kwargs: (
            base_resume,
            0.75,
            {"selected_resume": base_resume.name, "normalized_score": 0.75},
        ),
    )

    def _fake_compile(_tex_path: Path, out_dir: Path) -> Path:
        pdf_path = out_dir / "out.pdf"
        pdf_path.write_bytes(b"%PDF-1.4\n%fake\n")
        return pdf_path

    monkeypatch.setattr("agents.inbox.executor.compile_latex", _fake_compile)
    monkeypatch.setattr(
        "agents.inbox.drafts.generate_email_draft", lambda *_args, **_kwargs: _response("email")
    )
    monkeypatch.setattr("evals.soft.score_resume_relevance", lambda *_a, **_k: 0.8)
    monkeypatch.setattr("evals.soft.score_jd_accuracy", lambda *_a, **_k: 0.9)

    pack = run_pipeline(
        "raw jd text",
        selected_collateral=["email"],
        skip_upload=True,
        skip_calendar=True,
        user_vetted=True,
    )

    conn = psycopg2.connect(db, cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur = conn.cursor()
        cur.execute("SELECT user_vetted FROM jobs WHERE id = %s", (pack.job_id,))
        job_row = cur.fetchone()
    finally:
        conn.close()

    assert job_row is not None
    assert job_row["user_vetted"] == 1


def test_run_pipeline_compile_fallback_rolls_back_to_base_resume(
    db,
    tmp_path: Path,
    monkeypatch,
) -> None:
    runs_dir = tmp_path / "runs"
    profile_path = tmp_path / "profile.json"
    bullet_bank_path = tmp_path / "bullet_bank.json"
    base_resume = tmp_path / "master_ai.tex"

    profile_path.write_text(
        json.dumps(
            {
                "identity": {"name": "Karan"},
                "positioning": {"ai": "Product Manager"},
            }
        ),
        encoding="utf-8",
    )
    bullet_bank_path.write_text("[]", encoding="utf-8")
    base_resume.write_text(
        "\\documentclass{article}\n\\begin{document}\nBase resume\n\\end{document}\n",
        encoding="utf-8",
    )

    fake_settings = SimpleNamespace(
        database_url=db,
        runs_dir=runs_dir,
        resumes_dir=tmp_path,
        profile_path=profile_path,
        bullet_bank_path=bullet_bank_path,
        max_cost_per_job=1.0,
    )

    monkeypatch.setattr("agents.inbox.agent.get_settings", lambda: fake_settings)
    monkeypatch.setattr("core.db.get_settings", lambda: fake_settings)
    monkeypatch.setattr("evals.logger.get_settings", lambda: fake_settings)

    jd = JDSchema(
        company="RollbackCo",
        role="AI PM",
        location="Remote",
        experience_required="5 years",
        skills=["python"],
        description="Own AI product roadmap.",
    )
    monkeypatch.setattr(
        "agents.inbox.executor.extract_jd_with_usage",
        lambda _text: (
            jd,
            {
                "prompt_tokens": 1,
                "completion_tokens": 1,
                "total_tokens": 2,
                "cost_estimate": 0.00002,
            },
        ),
    )
    monkeypatch.setattr(
        "agents.inbox.executor.select_base_resume_with_details",
        lambda *_args, **_kwargs: (
            base_resume,
            0.9,
            {"selected_resume": base_resume.name, "normalized_score": 0.9},
        ),
    )

    call_counter = {"count": 0}

    def _compile_with_first_failure(_tex_path: Path, out_dir: Path) -> Path:
        call_counter["count"] += 1
        if call_counter["count"] == 1:
            raise RuntimeError("compile failed for mutated tex")
        pdf_path = out_dir / "fallback.pdf"
        pdf_path.write_bytes(b"%PDF-1.4\n%fallback\n")
        return pdf_path

    monkeypatch.setattr("agents.inbox.executor.compile_latex", _compile_with_first_failure)

    monkeypatch.setattr(
        "agents.inbox.drafts.generate_email_draft", lambda *_args, **_kwargs: _response("email")
    )
    monkeypatch.setattr(
        "agents.inbox.drafts.generate_linkedin_dm", lambda *_args, **_kwargs: _response("linkedin")
    )
    monkeypatch.setattr(
        "agents.inbox.drafts.generate_referral_template",
        lambda *_args, **_kwargs: _response("referral"),
    )

    monkeypatch.setattr("evals.soft.score_resume_relevance", lambda *_a, **_k: 0.8)
    monkeypatch.setattr("evals.soft.score_jd_accuracy", lambda *_a, **_k: 0.9)

    pack = run_pipeline(
        "raw jd text",
        selected_collateral=["email", "linkedin", "referral"],
        skip_upload=True,
        skip_calendar=True,
    )

    assert call_counter["count"] == 2
    assert pack.pdf_path is not None and pack.pdf_path.exists()
    assert pack.eval_results["compile_success"] is True
    assert pack.eval_results["compile_rollback_used"] is True
    assert pack.eval_results["compile_outcome"] == "fallback_success"
    assert pack.eval_results["single_page_status"] == "fallback_base_used"


def test_run_pipeline_fails_when_terminal_fallback_is_still_multi_page(
    db,
    tmp_path: Path,
    monkeypatch,
) -> None:
    runs_dir = tmp_path / "runs"
    profile_path = tmp_path / "profile.json"
    bullet_bank_path = tmp_path / "bullet_bank.json"
    base_resume = tmp_path / "master_ai.tex"

    profile_path.write_text(
        json.dumps({"identity": {"name": "Karan"}, "positioning": {"ai": "Product Manager"}}),
        encoding="utf-8",
    )
    bullet_bank_path.write_text("[]", encoding="utf-8")
    base_resume.write_text(
        "\\documentclass{article}\n\\begin{document}\nBase resume\n\\end{document}\n",
        encoding="utf-8",
    )

    fake_settings = SimpleNamespace(
        database_url=db,
        runs_dir=runs_dir,
        resumes_dir=tmp_path,
        profile_path=profile_path,
        bullet_bank_path=bullet_bank_path,
        max_cost_per_job=1.0,
    )

    monkeypatch.setattr("agents.inbox.agent.get_settings", lambda: fake_settings)
    monkeypatch.setattr("core.db.get_settings", lambda: fake_settings)
    monkeypatch.setattr("evals.logger.get_settings", lambda: fake_settings)

    jd = JDSchema(
        company="TwoPageCo",
        role="AI PM",
        location="Remote",
        experience_required="5 years",
        skills=["python"],
        description="Own AI product roadmap.",
    )
    monkeypatch.setattr(
        "agents.inbox.executor.extract_jd_with_usage",
        lambda _text: (
            jd,
            {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2, "cost_estimate": 0.0},
        ),
    )
    monkeypatch.setattr(
        "agents.inbox.executor.select_base_resume_with_details",
        lambda *_args, **_kwargs: (
            base_resume,
            0.8,
            {"selected_resume": base_resume.name, "normalized_score": 0.8},
        ),
    )

    calls = {"count": 0}

    def _compile_first_fails_then_fallback(_tex_path: Path, out_dir: Path) -> Path:
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("mutated compile failed")
        pdf_path = out_dir / "fallback.pdf"
        pdf_path.write_bytes(b"%PDF-1.4\n%fallback\n")
        return pdf_path

    monkeypatch.setattr("agents.inbox.executor.compile_latex", _compile_first_fails_then_fallback)
    monkeypatch.setattr("agents.inbox.executor.get_pdf_page_count", lambda _pdf: 2)
    monkeypatch.setattr("evals.soft.score_resume_relevance", lambda *_a, **_k: 0.7)
    monkeypatch.setattr("evals.soft.score_jd_accuracy", lambda *_a, **_k: 0.8)

    pack = run_pipeline(
        "raw jd text",
        selected_collateral=["email"],
        skip_upload=True,
        skip_calendar=True,
    )

    assert calls["count"] == 2
    assert pack.pdf_path is None
    assert pack.eval_results["compile_success"] is False
    assert pack.eval_results["single_page_status"] == "failed_multi_page_terminal"
    assert pack.eval_results["compile_outcome"] is None
    assert any("non-compliant" in err or "exceeds one page" in err for err in pack.errors)


def test_run_pipeline_skips_collateral_when_selection_missing(
    db,
    tmp_path: Path,
    monkeypatch,
) -> None:
    runs_dir = tmp_path / "runs"
    profile_path = tmp_path / "profile.json"
    bullet_bank_path = tmp_path / "bullet_bank.json"
    base_resume = tmp_path / "master_ai.tex"

    profile_path.write_text(json.dumps({"identity": {"name": "Karan"}}), encoding="utf-8")
    bullet_bank_path.write_text("[]", encoding="utf-8")
    base_resume.write_text(
        "\\documentclass{article}\n\\begin{document}\nBase resume\n\\end{document}\n",
        encoding="utf-8",
    )

    fake_settings = SimpleNamespace(
        database_url=db,
        runs_dir=runs_dir,
        resumes_dir=tmp_path,
        profile_path=profile_path,
        bullet_bank_path=bullet_bank_path,
        max_cost_per_job=1.0,
    )

    monkeypatch.setattr("agents.inbox.agent.get_settings", lambda: fake_settings)
    monkeypatch.setattr("core.db.get_settings", lambda: fake_settings)
    monkeypatch.setattr("evals.logger.get_settings", lambda: fake_settings)
    monkeypatch.setattr("evals.soft.score_resume_relevance", lambda *_a, **_k: 0.8)
    monkeypatch.setattr("evals.soft.score_jd_accuracy", lambda *_a, **_k: 0.9)

    jd = JDSchema(
        company="NoDraft Inc",
        role="PM",
        location="Remote",
        experience_required="3 years",
        skills=["python"],
        description="Ship products.",
    )
    monkeypatch.setattr(
        "agents.inbox.executor.extract_jd_with_usage",
        lambda _text: (
            jd,
            {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2, "cost_estimate": 0.0},
        ),
    )
    monkeypatch.setattr(
        "agents.inbox.executor.select_base_resume_with_details",
        lambda *_args, **_kwargs: (base_resume, 0.7, {"selected_resume": base_resume.name}),
    )

    def _compile(_tex_path: Path, out_dir: Path) -> Path:
        pdf = out_dir / "resume.pdf"
        pdf.write_bytes(b"%PDF-1.4\n")
        return pdf

    monkeypatch.setattr("agents.inbox.executor.compile_latex", _compile)

    called = {"email": 0, "linkedin": 0, "referral": 0}
    monkeypatch.setattr(
        "agents.inbox.drafts.generate_email_draft",
        lambda *_a, **_k: called.__setitem__("email", called["email"] + 1),
    )
    monkeypatch.setattr(
        "agents.inbox.drafts.generate_linkedin_dm",
        lambda *_a, **_k: called.__setitem__("linkedin", called["linkedin"] + 1),
    )
    monkeypatch.setattr(
        "agents.inbox.drafts.generate_referral_template",
        lambda *_a, **_k: called.__setitem__("referral", called["referral"] + 1),
    )

    pack = run_pipeline("raw jd text", skip_upload=True, skip_calendar=True)

    assert called == {"email": 0, "linkedin": 0, "referral": 0}
    assert pack.eval_results["collateral_generation_status"] == "blocked_missing_selection"
    assert pack.email_draft is None
    assert pack.linkedin_draft is None
    assert pack.referral_draft is None


def test_run_pipeline_uploads_only_selected_artifacts_to_drive(
    db,
    tmp_path: Path,
    monkeypatch,
) -> None:
    runs_dir = tmp_path / "runs"
    profile_path = tmp_path / "profile.json"
    bullet_bank_path = tmp_path / "bullet_bank.json"
    base_resume = tmp_path / "master_ai.tex"

    profile_path.write_text(
        json.dumps({"identity": {"name": "Karan"}, "positioning": {"ai": "PM"}}),
        encoding="utf-8",
    )
    bullet_bank_path.write_text("[]", encoding="utf-8")
    base_resume.write_text(
        "\\documentclass{article}\n\\begin{document}\nBase resume\n\\end{document}\n",
        encoding="utf-8",
    )

    fake_settings = SimpleNamespace(
        database_url=db,
        runs_dir=runs_dir,
        resumes_dir=tmp_path,
        profile_path=profile_path,
        bullet_bank_path=bullet_bank_path,
        max_cost_per_job=1.0,
    )

    monkeypatch.setattr("agents.inbox.agent.get_settings", lambda: fake_settings)
    monkeypatch.setattr("core.db.get_settings", lambda: fake_settings)
    monkeypatch.setattr("evals.logger.get_settings", lambda: fake_settings)
    monkeypatch.setattr("evals.soft.score_resume_relevance", lambda *_a, **_k: 0.8)
    monkeypatch.setattr("evals.soft.score_jd_accuracy", lambda *_a, **_k: 0.9)

    jd = JDSchema(
        company="DriveCo",
        role="PM",
        location="Remote",
        experience_required="3 years",
        skills=["python"],
        description="Ship products.",
    )
    monkeypatch.setattr(
        "agents.inbox.executor.extract_jd_with_usage",
        lambda _text: (
            jd,
            {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2, "cost_estimate": 0.0},
        ),
    )
    monkeypatch.setattr(
        "agents.inbox.executor.select_base_resume_with_details",
        lambda *_args, **_kwargs: (base_resume, 0.7, {"selected_resume": base_resume.name}),
    )

    def _compile(_tex_path: Path, out_dir: Path) -> Path:
        pdf = out_dir / "resume.pdf"
        pdf.write_bytes(b"%PDF-1.4\n")
        return pdf

    monkeypatch.setattr("agents.inbox.executor.compile_latex", _compile)
    monkeypatch.setattr(
        "agents.inbox.drafts.generate_email_draft", lambda *_a, **_k: _response("email")
    )
    monkeypatch.setattr(
        "agents.inbox.drafts.generate_linkedin_dm", lambda *_a, **_k: _response("linkedin")
    )
    monkeypatch.setattr(
        "agents.inbox.drafts.generate_referral_template", lambda *_a, **_k: _response("referral")
    )

    captured: dict[str, object] = {}

    def _upload_artifacts(
        *, files, company, role, application_context_id, run_id=None, candidate_name=None
    ):
        captured["files"] = {k: str(v) for k, v in files.items()}
        captured["company"] = company
        captured["role"] = role
        captured["application_context_id"] = application_context_id
        captured["run_id"] = run_id
        captured["candidate_name"] = candidate_name
        return {
            "folder": {"id": "folder-1", "path": "Job search agent/driveco_pm_run-x"},
            "files": {
                "resume_pdf": {"status": "uploaded", "webViewLink": "https://drive/resume"},
                "email": {"status": "uploaded", "webViewLink": "https://drive/email"},
            },
        }

    monkeypatch.setattr("integrations.drive.upload_application_artifacts", _upload_artifacts)

    pack = run_pipeline(
        "raw jd text",
        selected_collateral=["email"],
        skip_upload=False,
        skip_calendar=True,
    )

    assert set(captured["files"]) == {"resume_pdf", "report_md", "email"}
    assert "linkedin" not in captured["files"]
    assert "referral" not in captured["files"]
    assert pack.drive_link == "https://drive/resume"
    assert pack.eval_results["drive_uploads"]["files"]["email"]["status"] == "uploaded"


class _FakeMessage:
    def __init__(self, text: str, *, fail_on_too_long: bool = False) -> None:
        self.text = text
        self.replies: list[tuple[str, dict]] = []
        self.fail_on_too_long = fail_on_too_long
        self.reply_attempts = 0

    async def reply_text(self, text: str, **kwargs) -> None:
        self.reply_attempts += 1
        if self.fail_on_too_long and len(text) > 4096:
            raise Exception("Bad Request: message is too long")
        self.replies.append((text, kwargs))


class _FakeUpdate:
    def __init__(self, text: str, *, fail_on_too_long: bool = False) -> None:
        self.message = _FakeMessage(text, fail_on_too_long=fail_on_too_long)


def test_is_chat_allowed_bypasses_allowlist_in_demo_mode(monkeypatch) -> None:
    from agents.inbox import adapter

    monkeypatch.setattr(
        adapter,
        "get_settings",
        lambda: SimpleNamespace(telegram_demo_mode=True, telegram_allowed_chat_ids="123"),
    )
    update = SimpleNamespace(effective_chat=SimpleNamespace(id=999), message=None)

    assert adapter._is_chat_allowed(update) is True


def test_is_chat_allowed_enforces_allowlist_when_demo_mode_disabled(monkeypatch) -> None:
    from agents.inbox import adapter

    monkeypatch.setattr(
        adapter,
        "get_settings",
        lambda: SimpleNamespace(telegram_demo_mode=False, telegram_allowed_chat_ids="123,456"),
    )
    blocked = SimpleNamespace(effective_chat=SimpleNamespace(id=999), message=None)
    allowed = SimpleNamespace(effective_chat=SimpleNamespace(id=456), message=None)

    assert adapter._is_chat_allowed(blocked) is False
    assert adapter._is_chat_allowed(allowed) is True


@pytest.mark.asyncio
async def test_start_handler_shares_public_demo_intro(monkeypatch) -> None:
    from agents.inbox import adapter

    monkeypatch.setattr(
        adapter,
        "get_settings",
        lambda: SimpleNamespace(telegram_demo_mode=True),
    )

    update = _FakeUpdate("/start")
    context = SimpleNamespace(user_data={})

    await adapter.start_handler(update, context)

    assert len(update.message.replies) == 1
    payload = update.message.replies[0][0]
    assert "public demo" in payload.lower()
    assert "Send a job description" in payload
    assert "/status" in payload


@pytest.mark.asyncio
async def test_start_handler_uses_standard_intro_when_demo_mode_disabled(monkeypatch) -> None:
    from agents.inbox import adapter

    monkeypatch.setattr(
        adapter,
        "get_settings",
        lambda: SimpleNamespace(telegram_demo_mode=False),
    )

    update = _FakeUpdate("/start")
    context = SimpleNamespace(user_data={})

    await adapter.start_handler(update, context)

    assert len(update.message.replies) == 1
    payload = update.message.replies[0][0]
    assert "public demo" not in payload.lower()
    assert "I'm your Job Application Agent" in payload


@pytest.mark.asyncio
async def test_text_handler_greeting_shows_intro_without_start(monkeypatch) -> None:
    from agents.inbox import adapter

    monkeypatch.setattr(
        adapter,
        "get_settings",
        lambda: SimpleNamespace(
            telegram_enable_drive_upload=False,
            telegram_enable_calendar_events=False,
            telegram_allowed_chat_ids="",
            telegram_demo_mode=True,
        ),
    )

    update = _FakeUpdate("hi")
    context = SimpleNamespace(user_data={})

    await adapter.text_handler(update, context)

    assert len(update.message.replies) == 1
    assert "public demo" in update.message.replies[0][0].lower()
    assert context.user_data.get("demo_intro_sent") is True


@pytest.mark.asyncio
async def test_text_handler_greeting_intro_shows_once_then_routes(monkeypatch) -> None:
    from agents.inbox import adapter

    monkeypatch.setattr(
        adapter,
        "get_settings",
        lambda: SimpleNamespace(
            telegram_enable_drive_upload=False,
            telegram_enable_calendar_events=False,
            telegram_allowed_chat_ids="",
            telegram_demo_mode=True,
        ),
    )
    monkeypatch.setattr(
        adapter,
        "route",
        lambda _text: RouteResult(
            AgentTarget.AMBIGUOUS_NON_JOB,
            "ambiguous route",
            "ambiguous_non_job",
        ),
    )

    context = SimpleNamespace(user_data={})
    first = _FakeUpdate("hello")
    await adapter.text_handler(first, context)
    second = _FakeUpdate("hello")
    await adapter.text_handler(second, context)

    assert len(first.message.replies) == 1
    assert "public demo" in first.message.replies[0][0].lower()
    assert len(second.message.replies) == 1
    assert "need a job description input" in second.message.replies[0][0]


@pytest.mark.asyncio
async def test_reply_text_summarizes_oversized_payload_before_sending(monkeypatch) -> None:
    from agents.inbox import adapter

    long_text = "x" * 5000

    def _fake_chat_text(_system: str, _user: str):
        return SimpleNamespace(text="s" * 3500)

    monkeypatch.setattr(adapter, "chat_text", _fake_chat_text)
    update = _FakeUpdate("hi", fail_on_too_long=True)

    await adapter._reply_text(update, long_text, label="long-test")

    assert len(update.message.replies) == 1
    sent_text = update.message.replies[0][0]
    assert len(sent_text) <= adapter.TELEGRAM_SAFE_MESSAGE_CHARS
    assert update.message.reply_attempts == 1


@pytest.mark.asyncio
async def test_run_and_respond_summarizes_very_long_exception_message(monkeypatch) -> None:
    from agents.inbox import adapter

    def _raise_pipeline(*_args, **_kwargs):
        raise RuntimeError("boom-" + ("e" * 7000))

    def _fake_chat_text(_system: str, _user: str):
        return SimpleNamespace(text="summarized failure")

    async def _direct_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr("agents.inbox.agent.run_pipeline", _raise_pipeline)
    monkeypatch.setattr(adapter, "chat_text", _fake_chat_text)
    monkeypatch.setattr(adapter.asyncio, "to_thread", _direct_to_thread)

    update = _FakeUpdate("trigger", fail_on_too_long=True)
    await adapter._run_and_respond(
        update,
        raw_text="jd text",
        image_path=None,
        selected_collateral=[],
        skip_upload=True,
        skip_calendar=True,
        user_vetted=True,
    )

    assert len(update.message.replies) == 1
    sent_text = update.message.replies[0][0]
    assert sent_text
    assert len(sent_text) <= adapter.TELEGRAM_SAFE_MESSAGE_CHARS


@pytest.mark.asyncio
async def test_text_handler_routes_to_inbox_and_invokes_pipeline(monkeypatch) -> None:
    from agents.inbox import adapter

    captured: dict[str, object] = {}

    monkeypatch.setattr(
        adapter,
        "route",
        lambda _text: RouteResult(AgentTarget.INBOX, "test route"),
    )

    monkeypatch.setattr(
        adapter,
        "get_settings",
        lambda: SimpleNamespace(
            telegram_enable_drive_upload=False,
            telegram_enable_calendar_events=False,
            telegram_allowed_chat_ids="",
        ),
    )

    fake_pack = SimpleNamespace(
        jd=SimpleNamespace(
            company="Acme Corp",
            role="AI PM",
            location="Remote",
            skills=["python", "sql"],
        ),
        resume_base="base.tex",
        pdf_path=Path("/tmp/fake.pdf"),
        run_id="run-test",
        errors=[],
        selected_collateral=["email", "linkedin"],
        generated_collateral=["email", "linkedin"],
        email_draft=None,
        linkedin_draft=None,
        referral_draft=None,
    )

    def _fake_run_pipeline(
        raw_text: str,
        *,
        image_path=None,
        selected_collateral: list[str],
        skip_upload: bool,
        skip_calendar: bool,
        user_vetted: bool,
    ):
        captured["raw_text"] = raw_text
        captured["selected_collateral"] = selected_collateral
        captured["skip_upload"] = skip_upload
        captured["skip_calendar"] = skip_calendar
        captured["user_vetted"] = user_vetted
        return fake_pack

    monkeypatch.setattr("agents.inbox.agent.run_pipeline", _fake_run_pipeline)

    async def _fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(adapter.asyncio, "to_thread", _fake_to_thread)

    update = _FakeUpdate("here is a jd")
    context = SimpleNamespace(user_data={})

    await adapter.text_handler(update, context)
    assert "raw_text" not in captured
    assert "Which collateral should I generate" in update.message.replies[1][0]

    update2 = _FakeUpdate("Email, LinkedIn")
    await adapter.text_handler(update2, context)

    assert captured["raw_text"] == "here is a jd"
    assert captured["selected_collateral"] == ["email", "linkedin"]
    assert captured["skip_upload"] is True
    assert captured["skip_calendar"] is True
    assert captured["user_vetted"] is True

    replies = update.message.replies + update2.message.replies
    assert len(replies) == 4
    assert "Routing to Inbox Agent" in replies[0][0]
    assert "Which collateral should I generate" in replies[1][0]
    assert "Process started" in replies[2][0]
    assert "JD Extracted" in replies[3][0]
    assert "run-test" in replies[3][0]


@pytest.mark.asyncio
async def test_text_handler_reports_failure_when_no_valid_pdf(monkeypatch) -> None:
    from agents.inbox import adapter

    monkeypatch.setattr(
        adapter,
        "route",
        lambda _text: RouteResult(AgentTarget.INBOX, "test route"),
    )
    monkeypatch.setattr(
        adapter,
        "get_settings",
        lambda: SimpleNamespace(
            telegram_enable_drive_upload=False,
            telegram_enable_calendar_events=False,
            telegram_allowed_chat_ids="",
        ),
    )

    fake_pack = SimpleNamespace(
        jd=SimpleNamespace(company="Acme Corp", role="AI PM", location="Remote", skills=["python"]),
        resume_base="base.tex",
        pdf_path=None,
        run_id="run-fail",
        errors=["Terminal fallback resume exceeds one page (2 pages)."],
        selected_collateral=["email"],
        generated_collateral=["email"],
        email_draft=None,
        linkedin_draft=None,
        referral_draft=None,
    )

    monkeypatch.setattr("agents.inbox.agent.run_pipeline", lambda *_a, **_k: fake_pack)

    async def _fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(adapter.asyncio, "to_thread", _fake_to_thread)

    update = _FakeUpdate("here is a jd")
    context = SimpleNamespace(user_data={})

    await adapter.text_handler(update, context)
    assert "Which collateral should I generate" in update.message.replies[1][0]

    update2 = _FakeUpdate("email")
    await adapter.text_handler(update2, context)
    final_text = update2.message.replies[-1][0]
    assert "Process failed" in final_text
    assert "run-fail" in final_text


@pytest.mark.asyncio
async def test_text_handler_url_fetch_success_uses_extracted_text(monkeypatch) -> None:
    from agents.inbox import adapter

    captured: dict[str, object] = {}

    monkeypatch.setattr(
        adapter,
        "route",
        lambda _text: RouteResult(AgentTarget.INBOX, "url route"),
    )
    monkeypatch.setattr(adapter, "extract_first_url", lambda _text: "https://example.com/job")
    monkeypatch.setattr(
        adapter,
        "fetch_url_text",
        lambda _url: SimpleNamespace(ok=True, extracted_text="structured jd text", error=None),
    )

    fake_pack = SimpleNamespace(
        jd=SimpleNamespace(
            company="Acme Corp",
            role="AI PM",
            location="Remote",
            skills=["python"],
        ),
        resume_base="base.tex",
        pdf_path=Path("/tmp/fake.pdf"),
        run_id="run-url",
        errors=[],
        selected_collateral=["referral"],
        generated_collateral=["referral"],
        email_draft=None,
        linkedin_draft=None,
        referral_draft=None,
    )

    def _fake_run_pipeline(
        raw_text: str,
        *,
        image_path=None,
        selected_collateral: list[str],
        skip_upload: bool,
        skip_calendar: bool,
        user_vetted: bool,
    ):
        captured["raw_text"] = raw_text
        captured["selected_collateral"] = selected_collateral
        captured["skip_upload"] = skip_upload
        captured["skip_calendar"] = skip_calendar
        captured["user_vetted"] = user_vetted
        return fake_pack

    monkeypatch.setattr("agents.inbox.agent.run_pipeline", _fake_run_pipeline)

    async def _fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(adapter.asyncio, "to_thread", _fake_to_thread)

    update = _FakeUpdate("check this https://example.com/job")
    context = SimpleNamespace(user_data={})

    await adapter.text_handler(update, context)
    assert "raw_text" not in captured

    update2 = _FakeUpdate("ref")
    await adapter.text_handler(update2, context)

    assert captured["raw_text"] == "structured jd text"
    assert captured["selected_collateral"] == ["referral"]
    assert captured["user_vetted"] is True
    replies = update.message.replies + update2.message.replies
    assert len(replies) == 5
    assert "Routing to Inbox Agent" in replies[0][0]
    assert "Fetched job URL successfully" in replies[1][0]
    assert "Which collateral should I generate" in replies[2][0]
    assert "run-url" in replies[4][0]


@pytest.mark.asyncio
async def test_text_handler_url_fetch_failure_requests_screenshot(monkeypatch) -> None:
    from agents.inbox import adapter

    called = {"run_pipeline": False}

    monkeypatch.setattr(
        adapter,
        "route",
        lambda _text: RouteResult(AgentTarget.INBOX, "url route"),
    )
    monkeypatch.setattr(adapter, "extract_first_url", lambda _text: "https://example.com/job")
    monkeypatch.setattr(
        adapter,
        "fetch_url_text",
        lambda _url: SimpleNamespace(ok=False, extracted_text="", error="blocked"),
    )

    def _fake_run_pipeline(*_args, **_kwargs):
        called["run_pipeline"] = True
        raise AssertionError("run_pipeline should not be called on URL fetch failure")

    monkeypatch.setattr("agents.inbox.agent.run_pipeline", _fake_run_pipeline)

    async def _fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(adapter.asyncio, "to_thread", _fake_to_thread)

    update = _FakeUpdate("check this https://example.com/job")
    context = SimpleNamespace(user_data={})

    await adapter.text_handler(update, context)

    assert called["run_pipeline"] is False
    replies = update.message.replies
    assert len(replies) == 2
    assert "Routing to Inbox Agent" in replies[0][0]
    assert "couldn't reliably extract" in replies[1][0]


@pytest.mark.asyncio
async def test_text_handler_respects_drive_calendar_toggles(monkeypatch) -> None:
    from agents.inbox import adapter

    captured: dict[str, object] = {}

    monkeypatch.setattr(
        adapter,
        "route",
        lambda _text: RouteResult(AgentTarget.INBOX, "toggle route"),
    )
    monkeypatch.setattr(adapter, "extract_first_url", lambda _text: None)
    monkeypatch.setattr(
        adapter,
        "get_settings",
        lambda: SimpleNamespace(
            telegram_enable_drive_upload=True,
            telegram_enable_calendar_events=True,
            telegram_allowed_chat_ids="",
        ),
    )

    fake_pack = SimpleNamespace(
        jd=SimpleNamespace(
            company="Acme Corp",
            role="AI PM",
            location="Remote",
            skills=["python"],
        ),
        resume_base="base.tex",
        pdf_path=Path("/tmp/fake.pdf"),
        run_id="run-flags",
        errors=[],
        selected_collateral=[],
        generated_collateral=[],
        email_draft=None,
        linkedin_draft=None,
        referral_draft=None,
    )

    def _fake_run_pipeline(
        raw_text: str,
        *,
        image_path=None,
        selected_collateral: list[str],
        skip_upload: bool,
        skip_calendar: bool,
        user_vetted: bool,
    ):
        captured["raw_text"] = raw_text
        captured["selected_collateral"] = selected_collateral
        captured["skip_upload"] = skip_upload
        captured["skip_calendar"] = skip_calendar
        captured["user_vetted"] = user_vetted
        return fake_pack

    monkeypatch.setattr("agents.inbox.agent.run_pipeline", _fake_run_pipeline)

    async def _fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(adapter.asyncio, "to_thread", _fake_to_thread)

    update = _FakeUpdate("plain jd text")
    context = SimpleNamespace(user_data={})

    await adapter.text_handler(update, context)
    update2 = _FakeUpdate("none")
    await adapter.text_handler(update2, context)

    assert captured["raw_text"] == "plain jd text"
    assert captured["selected_collateral"] == []
    assert captured["skip_upload"] is False
    assert captured["skip_calendar"] is False
    assert captured["user_vetted"] is True


@pytest.mark.asyncio
async def test_text_handler_article_route_summarizes_and_logs(monkeypatch) -> None:
    from agents.inbox import adapter

    monkeypatch.setattr(
        adapter,
        "route",
        lambda _text: RouteResult(AgentTarget.ARTICLE, "article route", "article_signal"),
    )
    monkeypatch.setattr(
        "agents.article.agent.run_article_agent",
        lambda text: ("• AI is growing fast.", ["OpenAI hiring"], "article-abc123"),
    )
    update = _FakeUpdate("long article text")
    context = SimpleNamespace(user_data={})

    await adapter.text_handler(update, context)

    assert len(update.message.replies) == 2
    assert "Summarizing article" in update.message.replies[0][0]
    assert "AI is growing fast" in update.message.replies[1][0]
    assert "OpenAI hiring" in update.message.replies[1][0]
    assert "article-abc123" in update.message.replies[1][0]


@pytest.mark.asyncio
async def test_text_handler_ambiguous_non_job_route_returns_guidance(monkeypatch) -> None:
    from agents.inbox import adapter

    monkeypatch.setattr(
        adapter,
        "route",
        lambda _text: RouteResult(
            AgentTarget.AMBIGUOUS_NON_JOB,
            "ambiguous route",
            "ambiguous_non_job",
        ),
    )
    update = _FakeUpdate("random note")
    context = SimpleNamespace(user_data={})

    await adapter.text_handler(update, context)

    assert len(update.message.replies) == 1
    assert "need a job description input" in update.message.replies[0][0]


@pytest.mark.asyncio
async def test_text_handler_reprompts_on_invalid_collateral_selection(monkeypatch) -> None:
    from agents.inbox import adapter

    called = {"run_pipeline": 0}

    monkeypatch.setattr(
        adapter,
        "route",
        lambda _text: RouteResult(AgentTarget.INBOX, "test route"),
    )
    monkeypatch.setattr(
        adapter,
        "get_settings",
        lambda: SimpleNamespace(
            telegram_enable_drive_upload=False,
            telegram_enable_calendar_events=False,
            telegram_allowed_chat_ids="",
        ),
    )
    monkeypatch.setattr(adapter, "extract_first_url", lambda _text: None)

    def _fake_run_pipeline(*_args, **_kwargs):
        called["run_pipeline"] += 1
        return SimpleNamespace(
            jd=SimpleNamespace(company="C", role="R", location="L", skills=[]),
            resume_base="base.tex",
            pdf_path=Path("/tmp/fake.pdf"),
            run_id="run-x",
            errors=[],
            selected_collateral=[],
            generated_collateral=[],
        )

    monkeypatch.setattr("agents.inbox.agent.run_pipeline", _fake_run_pipeline)

    async def _fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(adapter.asyncio, "to_thread", _fake_to_thread)

    context = SimpleNamespace(user_data={})
    await adapter.text_handler(_FakeUpdate("new jd"), context)
    invalid = _FakeUpdate("please decide")
    await adapter.text_handler(invalid, context)

    assert called["run_pipeline"] == 0
    assert "couldn't parse" in invalid.message.replies[0][0]
