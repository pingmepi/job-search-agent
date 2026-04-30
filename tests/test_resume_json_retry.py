"""Regression test: mutation/condense JSON parsing should recover with retries."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

from agents.inbox.agent import run_pipeline
from agents.inbox.jd import JDSchema
from agents.inbox.resume import find_blank_bullets


def test_run_pipeline_recovers_from_non_json_mutation_and_condense_responses(
    tmp_path: Path,
    monkeypatch,
    db,
) -> None:
    runs_dir = tmp_path / "runs"
    profile_path = tmp_path / "profile.json"
    bullet_bank_path = tmp_path / "bullet_bank.json"
    base_resume = tmp_path / "master_ai.tex"

    profile_path.write_text(json.dumps({"identity": {"name": "Karan"}}), encoding="utf-8")
    bullet_bank_path.write_text(json.dumps([{"bullet": "Base bullet"}]), encoding="utf-8")
    base_resume.write_text(
        "\\documentclass{article}\n\\begin{document}\n\\item Base bullet\n\\end{document}\n",
        encoding="utf-8",
    )

    fake_settings = SimpleNamespace(
        database_url=db,
        runs_dir=runs_dir,
        resumes_dir=tmp_path,
        profile_path=profile_path,
        bullet_bank_path=bullet_bank_path,
        max_cost_per_job=1.0,
        skill_index_path=None,
    )
    monkeypatch.setattr("agents.inbox.agent.get_settings", lambda: fake_settings)
    monkeypatch.setattr("core.db.get_settings", lambda: fake_settings)
    monkeypatch.setattr("evals.logger.get_settings", lambda: fake_settings)

    jd = JDSchema(
        company="RetryCo",
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

    monkeypatch.setattr(
        "agents.inbox.executor.parse_editable_regions",
        lambda _text: [SimpleNamespace(content="\\item Base bullet")],
    )

    compile_calls = {"count": 0}

    def _compile_ok(_tex_path: Path, out_dir: Path) -> Path:
        compile_calls["count"] += 1
        pdf = out_dir / f"resume_{compile_calls['count']}.pdf"
        pdf.write_bytes(b"%PDF-1.4\n")
        return pdf

    monkeypatch.setattr("agents.inbox.executor.compile_latex", _compile_ok)

    page_counts = [2, 1]
    monkeypatch.setattr("agents.inbox.executor.get_pdf_page_count", lambda _pdf: page_counts.pop(0))

    llm_calls = {"count": 0}

    def _chat_text(_system: str, _user: str, *, json_mode: bool = False):
        assert json_mode is True
        llm_calls["count"] += 1
        responses = {
            1: "I cannot do JSON right now",  # mutation attempt 1 -> retry
            2: '{"mutations":[{"original":"\\\\item Base bullet","replacement":"\\\\item Base bullet"}]}',
            3: "not valid json",  # condense attempt 1 -> retry
            4: '{"mutations":[],"bullets_removed":[]}',
        }
        return SimpleNamespace(
            text=responses[llm_calls["count"]],
            prompt_tokens=1,
            completion_tokens=1,
            total_tokens=2,
            cost_estimate=0.0,
            generation_id=None,
        )

    llm_stub = ModuleType("core.llm")
    llm_stub.chat_text = _chat_text
    llm_stub.resolve_costs_batch = lambda _ids: {}
    monkeypatch.setitem(sys.modules, "core.llm", llm_stub)

    prompts_stub = ModuleType("core.prompts")
    prompts_stub.load_prompt = lambda _name, version=1: "prompt"
    monkeypatch.setitem(sys.modules, "core.prompts", prompts_stub)

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

    assert llm_calls["count"] == 4
    assert compile_calls["count"] >= 1
    assert pack.pdf_path is not None
    assert pack.eval_results["compile_success"] is True
    assert pack.eval_results["single_page_status"] == "met"
    assert not any("Expecting value" in err for err in pack.errors)


def test_run_pipeline_repairs_blank_bullets_from_condense_removals(
    tmp_path: Path,
    monkeypatch,
    db,
) -> None:
    runs_dir = tmp_path / "runs"
    profile_path = tmp_path / "profile.json"
    bullet_bank_path = tmp_path / "bullet_bank.json"
    base_resume = tmp_path / "master_ai.tex"

    profile_path.write_text(json.dumps({"identity": {"name": "Karan"}}), encoding="utf-8")
    bullet_bank_path.write_text(
        json.dumps(
            [
                {"bullet": "Built resilient roadmap and execution processes"},
                {"bullet": "Improved reporting reliability across teams"},
            ]
        ),
        encoding="utf-8",
    )
    base_resume.write_text(
        "\\documentclass{article}\n"
        "%%BEGIN_EDITABLE\n"
        "\\begin{itemize}\n"
        "  \\item Base bullet one\n"
        "  \\item Base bullet two\n"
        "\\end{itemize}\n"
        "%%END_EDITABLE\n",
        encoding="utf-8",
    )

    fake_settings = SimpleNamespace(
        database_url=db,
        runs_dir=runs_dir,
        resumes_dir=tmp_path,
        profile_path=profile_path,
        bullet_bank_path=bullet_bank_path,
        max_cost_per_job=1.0,
        skill_index_path=None,
    )
    monkeypatch.setattr("agents.inbox.agent.get_settings", lambda: fake_settings)
    monkeypatch.setattr("core.db.get_settings", lambda: fake_settings)
    monkeypatch.setattr("evals.logger.get_settings", lambda: fake_settings)

    jd = JDSchema(
        company="RetryCo",
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

    compile_calls = {"count": 0}

    def _compile_ok(_tex_path: Path, out_dir: Path) -> Path:
        compile_calls["count"] += 1
        pdf = out_dir / f"resume_{compile_calls['count']}.pdf"
        pdf.write_bytes(b"%PDF-1.4\n")
        return pdf

    monkeypatch.setattr("agents.inbox.executor.compile_latex", _compile_ok)

    page_counts = [2, 1]
    monkeypatch.setattr("agents.inbox.executor.get_pdf_page_count", lambda _pdf: page_counts.pop(0))

    llm_calls = {"count": 0}

    def _chat_text(_system: str, user: str, *, json_mode: bool = False):
        assert json_mode is True
        llm_calls["count"] += 1
        if "Current page count" in user:
            text = '{"mutations":[],"bullets_removed":[{"original":"Base bullet two","reason":"remove"}]}'
        elif "Original bullet:" in user:
            text = '{"replacement":"Recovered bullet two grounded in original context"}'
        else:
            text = '{"mutations":[{"original":"Base bullet one","replacement":"Base bullet one"}]}'
        return SimpleNamespace(
            text=text,
            prompt_tokens=1,
            completion_tokens=1,
            total_tokens=2,
            cost_estimate=0.0,
            generation_id=None,
            model="test-model",
        )

    llm_stub = ModuleType("core.llm")
    llm_stub.chat_text = _chat_text
    llm_stub.resolve_costs_batch = lambda _ids: {}
    monkeypatch.setitem(sys.modules, "core.llm", llm_stub)

    prompts_stub = ModuleType("core.prompts")
    prompts_stub.load_prompt = lambda _name, version=1: "prompt"
    monkeypatch.setitem(sys.modules, "core.prompts", prompts_stub)

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

    assert compile_calls["count"] >= 2
    assert llm_calls["count"] >= 3
    assert pack.mutated_tex is not None
    assert not find_blank_bullets(pack.mutated_tex)
    assert "Recovered bullet two grounded in original context" in pack.mutated_tex
