from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from core.report_markdown import render_application_report


def test_render_application_report_has_a_to_f_sections() -> None:
    pack = SimpleNamespace(
        jd=SimpleNamespace(
            company="Acme",
            role="AI PM",
            location="Remote",
            experience_required="5+ years",
            skills=["python", "sql"],
            jd_hash="abc123",
        ),
        run_id="run-1",
        resume_base="master_ai_pm.tex",
        generated_collateral=["email"],
        collateral_files={"email": "/tmp/email.txt", "linkedin": None, "referral": None},
        pdf_path=Path("/tmp/resume.pdf"),
        drive_uploads={},
        drive_link=None,
        errors=[],
    )
    ctx = SimpleNamespace(
        input_mode="text",
        fit_score=0.87,
        fit_score_details={"matched_tags": ["pm", "ai"], "missing_tags": ["mlops"]},
        compile_outcome="mutated_success",
        single_page_status="met",
        compile_rollback_used=False,
        mutation_summary={
            "mutations": [
                {
                    "type": "REWRITE",
                    "original": "Built roadmap",
                    "replacement": "Built AI roadmap",
                }
            ],
            "mutation_types": {"REWRITE": 1},
            "truthfulness": {"reverted_mutations": 0},
        },
    )

    report = render_application_report(pack=pack, ctx=ctx)

    assert "## A) Role Summary" in report
    assert "## B) Resume Base Selection" in report
    assert "## C) Resume Changes Made" in report
    assert "## D) Match Analysis" in report
    assert "## E) Generated Collateral" in report
    assert "## F) Execution Summary" in report
    assert "Selected base resume: master_ai_pm.tex" in report
    assert "REWRITE:" in report
