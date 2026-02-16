"""Integration tests for inbox pipeline + Telegram adapter with mocked dependencies."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace

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


def test_run_pipeline_persists_job_and_run_with_mocks(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "integration.db"
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
        db_path=db_path,
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
        "agents.inbox.agent.extract_jd_with_usage",
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
        "agents.inbox.agent.select_base_resume_with_score",
        lambda *_args, **_kwargs: (base_resume, 0.75),
    )

    def _fake_compile(_tex_path: Path, out_dir: Path) -> Path:
        pdf_path = out_dir / "out.pdf"
        pdf_path.write_bytes(b"%PDF-1.4\n%fake\n")
        return pdf_path

    monkeypatch.setattr("agents.inbox.agent.compile_latex", _fake_compile)

    monkeypatch.setattr("agents.inbox.drafts.generate_email_draft", lambda *_args, **_kwargs: _response("email"))
    monkeypatch.setattr("agents.inbox.drafts.generate_linkedin_dm", lambda *_args, **_kwargs: _response("linkedin"))
    monkeypatch.setattr("agents.inbox.drafts.generate_referral_template", lambda *_args, **_kwargs: _response("referral"))

    pack = run_pipeline("raw jd text", skip_upload=True, skip_calendar=True)

    assert pack.job_id is not None
    assert pack.run_id is not None
    assert pack.pdf_path is not None and pack.pdf_path.exists()
    assert pack.eval_results["compile_success"] is True
    assert pack.eval_results["llm_total_tokens"] > 0
    assert "llm_usage_breakdown" in pack.eval_results
    assert "keyword_coverage" in pack.eval_results

    with sqlite3.connect(str(db_path)) as conn:
        jobs_count = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        fit_score = conn.execute("SELECT fit_score FROM jobs LIMIT 1").fetchone()[0]
        run_row = conn.execute(
            "SELECT job_id, status, eval_results FROM runs WHERE run_id = ?",
            (pack.run_id,),
        ).fetchone()

    assert jobs_count == 1
    assert fit_score == 75
    assert run_row is not None
    assert run_row[0] == pack.job_id
    assert run_row[1] == "completed"
    assert json.loads(run_row[2])["compile_success"] is True


def test_run_pipeline_compile_fallback_rolls_back_to_base_resume(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db_path = tmp_path / "integration.db"
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
        db_path=db_path,
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
        "agents.inbox.agent.extract_jd_with_usage",
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
        "agents.inbox.agent.select_base_resume_with_score",
        lambda *_args, **_kwargs: (base_resume, 0.9),
    )

    call_counter = {"count": 0}

    def _compile_with_first_failure(_tex_path: Path, out_dir: Path) -> Path:
        call_counter["count"] += 1
        if call_counter["count"] == 1:
            raise RuntimeError("compile failed for mutated tex")
        pdf_path = out_dir / "fallback.pdf"
        pdf_path.write_bytes(b"%PDF-1.4\n%fallback\n")
        return pdf_path

    monkeypatch.setattr("agents.inbox.agent.compile_latex", _compile_with_first_failure)

    monkeypatch.setattr("agents.inbox.drafts.generate_email_draft", lambda *_args, **_kwargs: _response("email"))
    monkeypatch.setattr("agents.inbox.drafts.generate_linkedin_dm", lambda *_args, **_kwargs: _response("linkedin"))
    monkeypatch.setattr("agents.inbox.drafts.generate_referral_template", lambda *_args, **_kwargs: _response("referral"))

    pack = run_pipeline("raw jd text", skip_upload=True, skip_calendar=True)

    assert call_counter["count"] == 2
    assert pack.pdf_path is not None and pack.pdf_path.exists()
    assert pack.eval_results["compile_success"] is True
    assert pack.eval_results["compile_rollback_used"] is True


class _FakeMessage:
    def __init__(self, text: str) -> None:
        self.text = text
        self.replies: list[tuple[str, dict]] = []

    async def reply_text(self, text: str, **kwargs) -> None:
        self.replies.append((text, kwargs))


class _FakeUpdate:
    def __init__(self, text: str) -> None:
        self.message = _FakeMessage(text)


@pytest.mark.asyncio
async def test_text_handler_routes_to_inbox_and_invokes_pipeline(monkeypatch) -> None:
    from agents.inbox import adapter

    captured: dict[str, object] = {}

    monkeypatch.setattr(
        adapter,
        "route",
        lambda _text: RouteResult(AgentTarget.INBOX, "test route"),
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
    )

    def _fake_run_pipeline(raw_text: str, *, skip_upload: bool, skip_calendar: bool):
        captured["raw_text"] = raw_text
        captured["skip_upload"] = skip_upload
        captured["skip_calendar"] = skip_calendar
        return fake_pack

    monkeypatch.setattr("agents.inbox.agent.run_pipeline", _fake_run_pipeline)

    async def _fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(adapter.asyncio, "to_thread", _fake_to_thread)

    update = _FakeUpdate("here is a jd")
    context = SimpleNamespace()

    await adapter.text_handler(update, context)

    assert captured["raw_text"] == "here is a jd"
    assert captured["skip_upload"] is True
    assert captured["skip_calendar"] is True

    replies = update.message.replies
    assert len(replies) == 2
    assert "Routing to Inbox Agent" in replies[0][0]
    assert "JD Extracted" in replies[1][0]
    assert "run-test" in replies[1][0]


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
    )

    def _fake_run_pipeline(raw_text: str, *, skip_upload: bool, skip_calendar: bool):
        captured["raw_text"] = raw_text
        captured["skip_upload"] = skip_upload
        captured["skip_calendar"] = skip_calendar
        return fake_pack

    monkeypatch.setattr("agents.inbox.agent.run_pipeline", _fake_run_pipeline)

    async def _fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(adapter.asyncio, "to_thread", _fake_to_thread)

    update = _FakeUpdate("check this https://example.com/job")
    context = SimpleNamespace()

    await adapter.text_handler(update, context)

    assert captured["raw_text"] == "structured jd text"
    replies = update.message.replies
    assert len(replies) == 3
    assert "Routing to Inbox Agent" in replies[0][0]
    assert "Fetched job URL successfully" in replies[1][0]
    assert "run-url" in replies[2][0]


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
    context = SimpleNamespace()

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
    )

    def _fake_run_pipeline(raw_text: str, *, skip_upload: bool, skip_calendar: bool):
        captured["raw_text"] = raw_text
        captured["skip_upload"] = skip_upload
        captured["skip_calendar"] = skip_calendar
        return fake_pack

    monkeypatch.setattr("agents.inbox.agent.run_pipeline", _fake_run_pipeline)

    async def _fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(adapter.asyncio, "to_thread", _fake_to_thread)

    update = _FakeUpdate("plain jd text")
    context = SimpleNamespace()

    await adapter.text_handler(update, context)

    assert captured["raw_text"] == "plain jd text"
    assert captured["skip_upload"] is False
    assert captured["skip_calendar"] is False
