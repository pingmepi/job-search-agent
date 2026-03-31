"""Regression tests for strict one-page terminal enforcement."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

from agents.inbox.agent import run_pipeline
from agents.inbox.jd import JDSchema


def test_run_pipeline_fails_when_fallback_pdf_is_multi_page(tmp_path: Path, monkeypatch, db) -> None:
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

    llm_stub = ModuleType("core.llm")
    llm_stub.chat_text = lambda *_a, **_k: SimpleNamespace(
        text='{"mutations":[]}',
        prompt_tokens=1,
        completion_tokens=1,
        total_tokens=2,
        cost_estimate=0.0,
        generation_id=None,
    )
    llm_stub.resolve_costs_batch = lambda _ids: {}
    monkeypatch.setitem(sys.modules, "core.llm", llm_stub)

    prompts_stub = ModuleType("core.prompts")
    prompts_stub.load_prompt = lambda _name, version=1: "prompt"
    monkeypatch.setitem(sys.modules, "core.prompts", prompts_stub)

    # Avoid importing OpenAI-dependent soft eval module in this environment.
    soft_stub = ModuleType("evals.soft")
    soft_stub.score_resume_relevance = lambda *_a, **_k: 0.7
    soft_stub.score_jd_accuracy = lambda *_a, **_k: 0.8
    monkeypatch.setitem(sys.modules, "evals.soft", soft_stub)

    pack = run_pipeline(
        "raw jd text",
        selected_collateral=[],
        skip_upload=True,
        skip_calendar=True,
    )

    assert calls["count"] == 2
    assert pack.pdf_path is None
    assert pack.eval_results["compile_success"] is False
    assert pack.eval_results["single_page_status"] == "failed_multi_page_terminal"
    assert pack.eval_results["compile_outcome"] is None
    assert any("non-compliant" in err or "exceeds one page" in err for err in pack.errors)
    assert pack.output_dir is not None
    assert list(Path(pack.output_dir).glob("*.pdf")) == []
