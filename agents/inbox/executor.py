"""
Executor for the Inbox Agent (KAR-61, PRD Phase 2).

Receives a ToolPlan from the planner and executes each step in order.
Each step has an associated handler function.  Transient failures are
retried according to step.retry_on_transient / step.max_attempts.
Non-fatal errors are appended to pack.errors and execution continues
(matching existing graceful-degradation behaviour).

Public API:
    result = execute_plan(plan, pack, settings)
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from agents.inbox.planner import (
    ToolPlan,
    ToolStep,
    TOOL_CALENDAR,
    TOOL_COMPILE,
    TOOL_DB_LOG,
    TOOL_DRAFT_EMAIL,
    TOOL_DRAFT_LINKEDIN,
    TOOL_DRAFT_REFERRAL,
    TOOL_DRIVE_UPLOAD,
    TOOL_EVAL_LOG,
    TOOL_JD_EXTRACT,
    TOOL_OCR,
    TOOL_RESUME_MUTATE,
    TOOL_RESUME_SELECT,
)

# Module-level imports for patchability (integration tests monkeypatch these)
from agents.inbox.jd import extract_jd_with_usage, get_cached_jd
from agents.inbox.resume import (
    select_base_resume_with_details,
    parse_editable_regions,
    apply_mutations,
    compile_latex,
    get_pdf_page_count,
)
from core.prompts import load_prompt

if TYPE_CHECKING:
    from agents.inbox.agent import ApplicationPack
    from core.config import Settings

logger = logging.getLogger(__name__)


# ── Step result ───────────────────────────────────────────────────────────────


@dataclass
class StepResult:
    """Outcome of executing a single ToolStep."""

    step_name: str
    success: bool
    attempts: int = 1
    error: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)


# ── Execution context (shared mutable state passed through handlers) ──────────


@dataclass
class ExecutionContext:
    """Runtime context accumulated across steps."""

    run_id: str
    start_time: float
    plan: ToolPlan
    settings: Any  # core.config.Settings

    # Accumulated telemetry
    total_tokens: int = 0
    total_cost: float = 0.0
    generation_ids: list[tuple[str, str]] = field(default_factory=list)
    llm_usage_breakdown: dict[str, dict[str, Any]] = field(default_factory=dict)

    # Step outputs carried forward
    original_tex: Optional[str] = None
    base_path: Optional[Path] = None
    fit_score: float = 0.0
    fit_score_details: dict[str, Any] = field(default_factory=dict)
    fit_score_percent: int = 0
    compile_rollback_used: bool = False
    truthfulness_fallback_used: bool = False
    single_page_target_met: bool = False
    single_page_status: str = "not_checked"
    compile_outcome: Optional[str] = None
    condense_retries: int = 0
    input_mode: str = "text"
    step_results: list[StepResult] = field(default_factory=list)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _is_transient_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    markers = (
        "rate limit", "too many requests", "429", "timeout", "timed out",
        "connection", "temporarily unavailable", "server error", "503", "502", "504",
    )
    return any(m in msg for m in markers)


def _extract_bullets(text: str) -> list[str]:
    bullets: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(r"\item "):
            bullets.append(stripped.replace(r"\item ", "", 1).strip())
    return bullets


def _outside_editable_content_changed(original_tex: str, mutated_tex: str) -> bool:
    pattern = re.compile(r"(%%BEGIN_EDITABLE)(.*?)(%%END_EDITABLE)", re.DOTALL)
    original_masked = pattern.sub(r"\1\n__EDITABLE_REGION__\n\3", original_tex)
    mutated_masked = pattern.sub(r"\1\n__EDITABLE_REGION__\n\3", mutated_tex)
    return original_masked != mutated_masked


def _keyword_coverage(skills: list[str], text: str) -> float:
    normalised = [s.strip().lower() for s in skills if isinstance(s, str) and s.strip()]
    if not normalised:
        return 1.0
    haystack = text.lower()
    matched = sum(1 for s in normalised if s in haystack)
    return matched / len(normalised)


def _slugify(value: str, fallback: str) -> str:
    text = re.sub(r"[^a-z0-9]+", "_", (value or "").strip().lower()).strip("_")
    return text or fallback


def _extract_first_json_object(text: str) -> Optional[str]:
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    in_string = False
    escaped = False
    for idx in range(start, len(text)):
        ch = text[idx]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start:idx + 1]
    return None


def _parse_json_object(text: str) -> dict:
    candidate = (text or "").strip()
    if not candidate:
        raise ValueError("LLM returned empty response.")
    try:
        parsed = json.loads(candidate)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", candidate, flags=re.IGNORECASE)
    if fenced:
        try:
            parsed = json.loads(fenced.group(1).strip())
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
    extracted = _extract_first_json_object(candidate)
    if extracted:
        parsed = json.loads(extracted)
        if isinstance(parsed, dict):
            return parsed
    raise ValueError(f"No parseable JSON object. Preview: {candidate[:180]!r}")


def _chat_json_with_retry(
    *,
    system: str,
    user_msg: str,
    step_name: str,
    max_attempts: int = 3,
) -> tuple[dict, Any]:
    from core.llm import chat_text

    last_error: Optional[Exception] = None
    for attempt in range(1, max_attempts + 1):
        try:
            response = chat_text(system, user_msg, json_mode=True)
            parsed = _parse_json_object(response.text)
            return parsed, response
        except Exception as exc:
            last_error = exc
            if attempt < max_attempts and (isinstance(exc, ValueError) or _is_transient_error(exc)):
                time.sleep(0.2 * attempt)
                continue
            raise RuntimeError(f"{step_name} failed after {attempt} attempts: {exc}") from exc
    raise RuntimeError(f"{step_name} failed: {last_error}") from last_error


# ── Handler registry ──────────────────────────────────────────────────────────
# Each handler signature: (step, pack, ctx) -> pack
# Handlers mutate pack and ctx in place and return pack.

Handler = Any  # Callable[[ToolStep, ApplicationPack, ExecutionContext], ApplicationPack]


def _handle_ocr(
    step: ToolStep,
    pack: "ApplicationPack",
    ctx: ExecutionContext,
) -> "ApplicationPack":
    from agents.inbox.ocr import ocr_pipeline_with_usage
    image_path = Path(step.params["image_path"])
    raw_text, usage = ocr_pipeline_with_usage(image_path)
    ctx.plan.raw_text = raw_text  # update shared text for subsequent steps
    ctx.total_tokens += int(usage.get("total_tokens", 0))
    ctx.llm_usage_breakdown["ocr_cleanup"] = usage
    if usage.get("generation_id"):
        ctx.generation_ids.append(("ocr_cleanup", usage["generation_id"]))
    return pack


def _handle_jd_extract(
    step: ToolStep,
    pack: "ApplicationPack",
    ctx: ExecutionContext,
) -> "ApplicationPack":
    jd, usage = extract_jd_with_usage(ctx.plan.raw_text)
    ctx.total_tokens += int(usage.get("total_tokens", 0))
    ctx.llm_usage_breakdown["jd_extract"] = usage
    if usage.get("generation_id"):
        ctx.generation_ids.append(("jd_extract", usage["generation_id"]))

    cached = get_cached_jd(jd.jd_hash)
    if cached:
        logger.info("JD cache hit: %s", jd.jd_hash)

    pack.jd = jd
    return pack


def _handle_resume_select(
    step: ToolStep,
    pack: "ApplicationPack",
    ctx: ExecutionContext,
) -> "ApplicationPack":
    base_path, fit_score, details = select_base_resume_with_details(
        pack.jd.skills, ctx.settings.resumes_dir,
    )
    ctx.base_path = base_path
    ctx.fit_score = fit_score
    ctx.fit_score_details = details
    ctx.fit_score_percent = int(round(fit_score * 100))
    pack.resume_base = base_path.name
    logger.info("Selected resume: %s", base_path.name)
    return pack


def _handle_resume_mutate(
    step: ToolStep,
    pack: "ApplicationPack",
    ctx: ExecutionContext,
) -> "ApplicationPack":
    from evals.hard import check_forbidden_claims

    assert ctx.base_path is not None
    original_tex = ctx.base_path.read_text(encoding="utf-8")
    ctx.original_tex = original_tex
    jd = pack.jd

    regions = parse_editable_regions(original_tex)
    if not regions:
        pack.mutated_tex = original_tex
        return pack

    editable_content = "\n".join(r.content for r in regions)
    bullet_bank_raw = json.loads(
        ctx.settings.bullet_bank_path.read_text(encoding="utf-8")
    )
    bullet_bank_values = [b["bullet"] for b in bullet_bank_raw if isinstance(b, dict) and "bullet" in b]
    bullet_bank_text = "\n".join(bullet_bank_values)

    system = load_prompt("resume_mutate", version=1)
    user_msg = (
        f"JD:\n{json.dumps({'company': jd.company, 'role': jd.role, 'skills': jd.skills, 'description': jd.description})}\n\n"
        f"Current editable bullets:\n{editable_content}\n\n"
        f"Bullet bank:\n{bullet_bank_text}"
    )

    mutations_data, response = _chat_json_with_retry(
        system=system,
        user_msg=user_msg,
        step_name="Resume mutation",
        max_attempts=step.max_attempts,
    )
    ctx.total_tokens += response.total_tokens
    if response.generation_id:
        ctx.generation_ids.append(("resume_mutation", response.generation_id))
    ctx.llm_usage_breakdown["resume_mutation"] = {
        "prompt_tokens": response.prompt_tokens,
        "completion_tokens": response.completion_tokens,
        "total_tokens": response.total_tokens,
        "cost_estimate": response.cost_estimate,
    }

    mutations = mutations_data.get("mutations", [])
    mutated_tex = apply_mutations(original_tex, mutations)

    # Truthfulness safeguard
    original_bullets = _extract_bullets(original_tex)
    mutated_bullets = _extract_bullets(mutated_tex)
    forbidden_pre = check_forbidden_claims(original_bullets, mutated_bullets, bullet_bank_values)
    if forbidden_pre > 0:
        ctx.truthfulness_fallback_used = True
        pack.errors.append(
            f"Truthfulness safeguard triggered ({forbidden_pre} suspected fabricated claims); "
            "using safe base resume content."
        )
        mutated_tex = original_tex

    pack.mutated_tex = mutated_tex
    return pack


def _handle_compile(
    step: ToolStep,
    pack: "ApplicationPack",
    ctx: ExecutionContext,
) -> "ApplicationPack":
    assert ctx.base_path is not None
    if not pack.mutated_tex:
        return pack

    jd = pack.jd
    company_slug = _slugify(jd.company, "company")
    role_slug = _slugify(jd.role, "role")
    short_hash = jd.jd_hash[:8]
    application_context_id = f"{company_slug}_{role_slug}_{short_hash}"
    app_output_dir = ctx.settings.runs_dir / "artifacts" / application_context_id
    app_output_dir.mkdir(parents=True, exist_ok=True)
    pack.application_context_id = application_context_id
    pack.output_dir = app_output_dir

    base_path = ctx.base_path

    def _compile_and_persist(tex_content: str, suffix: str = "") -> Path:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_tex = Path(tmp_dir) / base_path.name
            tmp_tex.write_text(tex_content, encoding="utf-8")
            compiled = compile_latex(tmp_tex, Path(tmp_dir))
            dest = app_output_dir / f"{base_path.stem}{suffix}.pdf"
            shutil.copy2(compiled, dest)
            return dest

    def _safe_page_count(pdf_path: Path) -> Optional[int]:
        try:
            return get_pdf_page_count(pdf_path)
        except Exception as err:
            pack.errors.append(f"Page count check failed: {err}")
            return None

    def _cleanup_pdfs(out_dir: Path) -> list[str]:
        removed = []
        for pdf in out_dir.glob("*.pdf"):
            pdf.unlink(missing_ok=True)
            removed.append(pdf.name)
        return removed

    try:
        pack.pdf_path = _compile_and_persist(pack.mutated_tex)

        # Page count check (informational only — no condense/reject loop)
        if pack.pdf_path and pack.pdf_path.exists():
            pages = _safe_page_count(pack.pdf_path)
            if pages is not None:
                ctx.single_page_target_met = (pages <= 1)
                ctx.single_page_status = "met" if pages <= 1 else f"accepted_{pages}_pages"
            else:
                ctx.single_page_status = "unknown"
            ctx.compile_outcome = "mutated_success"

    except Exception as e:
        pack.errors.append(f"LaTeX compile failed: {e}")
        try:
            base_tex = base_path.read_text(encoding="utf-8")
            pack.pdf_path = _compile_and_persist(base_tex, "_fallback")
            ctx.compile_rollback_used = True
            ctx.compile_outcome = "fallback_success"
            ctx.single_page_status = "fallback_base_used"
            pack.errors.append("LaTeX compile rollback applied: used base resume artifact.")
        except Exception as fe:
            pack.errors.append(f"LaTeX compile fallback failed: {fe}")
            ctx.single_page_status = "fallback_failed"

    logger.info(
        "Compile result jd_hash=%s success=%s rollback=%s condense=%d",
        jd.jd_hash, bool(pack.pdf_path), ctx.compile_rollback_used, ctx.condense_retries,
    )
    return pack


def _handle_calendar(
    step: ToolStep,
    pack: "ApplicationPack",
    ctx: ExecutionContext,
) -> "ApplicationPack":
    from integrations.calendar import create_application_events
    create_application_events(pack.jd.company, pack.jd.role)
    return pack


def _handle_draft(
    step: ToolStep,
    pack: "ApplicationPack",
    ctx: ExecutionContext,
) -> "ApplicationPack":
    from agents.inbox.drafts import (
        generate_email_draft,
        generate_linkedin_dm,
        generate_referral_template,
    )

    profile = json.loads(ctx.settings.profile_path.read_text(encoding="utf-8"))
    identity = profile.get("identity", {})
    name = identity.get("name", "Karan")
    positioning = profile.get("positioning", {}).get("ai", "Product Manager")
    collateral_type = step.params.get("collateral_type", "")
    tool = step.tool
    jd = pack.jd

    if tool == TOOL_DRAFT_EMAIL:
        resp = generate_email_draft(name, positioning, jd.company, jd.role)
        pack.email_draft = resp.text
        ctx.total_tokens += getattr(resp, "total_tokens", 0)
        pack.generated_collateral.append("email")
        gen_id = getattr(resp, "generation_id", None)
        if gen_id:
            ctx.generation_ids.append(("draft_email", gen_id))
        ctx.llm_usage_breakdown["draft_email"] = {
            "prompt_tokens": getattr(resp, "prompt_tokens", 0),
            "completion_tokens": getattr(resp, "completion_tokens", 0),
            "total_tokens": getattr(resp, "total_tokens", 0),
            "cost_estimate": getattr(resp, "cost_estimate", 0.0),
        }

    elif tool == TOOL_DRAFT_LINKEDIN:
        resp = generate_linkedin_dm(name, positioning, jd.company, jd.role)
        pack.linkedin_draft = resp.text
        ctx.total_tokens += getattr(resp, "total_tokens", 0)
        pack.generated_collateral.append("linkedin")
        gen_id = getattr(resp, "generation_id", None)
        if gen_id:
            ctx.generation_ids.append(("draft_linkedin", gen_id))
        ctx.llm_usage_breakdown["draft_linkedin"] = {
            "prompt_tokens": getattr(resp, "prompt_tokens", 0),
            "completion_tokens": getattr(resp, "completion_tokens", 0),
            "total_tokens": getattr(resp, "total_tokens", 0),
            "cost_estimate": getattr(resp, "cost_estimate", 0.0),
        }

    elif tool == TOOL_DRAFT_REFERRAL:
        resp = generate_referral_template(name, positioning, jd.company, jd.role)
        pack.referral_draft = resp.text
        ctx.total_tokens += getattr(resp, "total_tokens", 0)
        pack.generated_collateral.append("referral")
        gen_id = getattr(resp, "generation_id", None)
        if gen_id:
            ctx.generation_ids.append(("draft_referral", gen_id))
        ctx.llm_usage_breakdown["draft_referral"] = {
            "prompt_tokens": getattr(resp, "prompt_tokens", 0),
            "completion_tokens": getattr(resp, "completion_tokens", 0),
            "total_tokens": getattr(resp, "total_tokens", 0),
            "cost_estimate": getattr(resp, "cost_estimate", 0.0),
        }

    # Persist draft to output dir if available
    _persist_draft(pack, ctx)
    return pack


def _persist_draft(pack: "ApplicationPack", ctx: ExecutionContext) -> None:
    if not (pack.output_dir and pack.output_dir.exists()):
        return
    try:
        if pack.email_draft and not (pack.output_dir / "email_draft.txt").exists():
            p = pack.output_dir / "email_draft.txt"
            p.write_text(pack.email_draft, encoding="utf-8")
            pack.collateral_files["email"] = str(p)
        if pack.linkedin_draft and not (pack.output_dir / "linkedin_dm.txt").exists():
            p = pack.output_dir / "linkedin_dm.txt"
            p.write_text(pack.linkedin_draft, encoding="utf-8")
            pack.collateral_files["linkedin"] = str(p)
        if pack.referral_draft and not (pack.output_dir / "referral.txt").exists():
            p = pack.output_dir / "referral.txt"
            p.write_text(pack.referral_draft, encoding="utf-8")
            pack.collateral_files["referral"] = str(p)
    except Exception as e:
        pack.errors.append(f"Draft file persistence failed: {e}")


def _handle_drive_upload(
    step: ToolStep,
    pack: "ApplicationPack",
    ctx: ExecutionContext,
) -> "ApplicationPack":
    from integrations.drive import upload_application_artifacts
    if not pack.pdf_path:
        return pack
    drive_files: dict[str, Path] = {"resume_pdf": pack.pdf_path}
    for key, file_path in pack.collateral_files.items():
        if file_path:
            drive_files[key] = Path(file_path)
    pack.drive_uploads = upload_application_artifacts(
        files=drive_files,
        company=pack.jd.company,
        role=pack.jd.role,
        application_context_id=pack.application_context_id or ctx.run_id,
    )
    resume_upload = pack.drive_uploads.get("files", {}).get("resume_pdf", {})
    if isinstance(resume_upload, dict):
        pack.drive_link = resume_upload.get("webViewLink")
    return pack


def _handle_db_log(
    step: ToolStep,
    pack: "ApplicationPack",
    ctx: ExecutionContext,
) -> "ApplicationPack":
    from core.db import insert_job
    job_id = insert_job(
        pack.jd.company, pack.jd.role, pack.jd.jd_hash,
        fit_score=ctx.fit_score_percent,
        resume_used=pack.resume_base,
        drive_link=pack.drive_link,
    )
    pack.job_id = job_id
    return pack


def _handle_eval_log(
    step: ToolStep,
    pack: "ApplicationPack",
    ctx: ExecutionContext,
) -> "ApplicationPack":
    from evals.hard import (
        check_jd_schema, check_edit_scope, check_forbidden_claims,
        check_draft_length, check_cost,
    )
    from evals.logger import log_run
    from core.artifacts import write_json_artifact
    from core.contracts import (
        build_eval_output_artifact,
        build_job_extraction_artifact,
        build_resume_output_artifact,
    )

    jd = pack.jd
    latency_ms = int((time.time() - ctx.start_time) * 1000)

    # ── Resolve real costs ────────────────────────────────────────
    try:
        from core.llm import resolve_costs_batch
        gen_id_list = [gid for _, gid in ctx.generation_ids]
        resolved = resolve_costs_batch(gen_id_list)
        for sname, gen_id in ctx.generation_ids:
            cost = resolved.get(gen_id, 0.0)
            ctx.total_cost += cost
            if sname in ctx.llm_usage_breakdown:
                ctx.llm_usage_breakdown[sname]["cost_estimate"] = cost
    except Exception as cost_err:
        pack.errors.append(f"Cost resolution failed: {cost_err}")

    # ── Hard evals ────────────────────────────────────────────────
    original_bullets: list[str] = []
    mutated_bullets: list[str] = []
    forbidden_claims_count = 0
    edit_scope_violations = 0

    if ctx.original_tex and pack.mutated_tex:
        outside_changed = _outside_editable_content_changed(ctx.original_tex, pack.mutated_tex)
        edit_scope_ok = check_edit_scope(ctx.original_tex, pack.mutated_tex, outside_changed=outside_changed)
        edit_scope_violations = 0 if edit_scope_ok else 1

        original_bullets = _extract_bullets(ctx.original_tex)
        mutated_bullets = _extract_bullets(pack.mutated_tex)
        try:
            bb_raw = json.loads(ctx.settings.bullet_bank_path.read_text(encoding="utf-8"))
            bullet_bank = [b.get("bullet", "") for b in bb_raw if isinstance(b, dict)]
        except Exception:
            bullet_bank = []
        forbidden_claims_count = check_forbidden_claims(original_bullets, mutated_bullets, bullet_bank)

    if ctx.truthfulness_fallback_used and forbidden_claims_count == 0:
        forbidden_claims_count = 1

    # ── Soft evals ────────────────────────────────────────────────
    soft_resume_relevance: Optional[float] = None
    soft_jd_accuracy: Optional[float] = None
    try:
        from evals.soft import score_resume_relevance, score_jd_accuracy
        if pack.mutated_tex:
            soft_resume_relevance = score_resume_relevance(jd.description, pack.mutated_tex)
        soft_jd_accuracy = score_jd_accuracy(
            ctx.plan.raw_text,
            {
                "company": jd.company, "role": jd.role, "location": jd.location,
                "experience_required": jd.experience_required, "skills": jd.skills,
                "description": jd.description,
            },
        )
    except Exception as soft_err:
        pack.errors.append(f"Soft eval failed: {soft_err}")

    eval_results = {
        "compile_success": bool(pack.pdf_path and pack.pdf_path.exists()),
        "forbidden_claims_count": forbidden_claims_count,
        "edit_scope_violations": edit_scope_violations,
        "draft_length_ok": check_draft_length(pack.linkedin_draft or "", max_chars=300),
        "cost_ok": check_cost(ctx.total_cost, threshold=ctx.settings.max_cost_per_job),
        "keyword_coverage": _keyword_coverage(jd.skills, pack.mutated_tex or ""),
        "compile_rollback_used": ctx.compile_rollback_used,
        "truthfulness_fallback_used": ctx.truthfulness_fallback_used,
        "condense_retries": ctx.condense_retries,
        "single_page_target_met": ctx.single_page_target_met,
        "single_page_status": ctx.single_page_status,
        "compile_outcome": ctx.compile_outcome,
        "selected_collateral": pack.selected_collateral,
        "generated_collateral": pack.generated_collateral,
        "collateral_generation_status": pack.collateral_generation_status,
        "collateral_generation_reason": pack.collateral_generation_reason,
        "collateral_files": pack.collateral_files,
        "application_context_id": pack.application_context_id,
        "drive_uploads": pack.drive_uploads,
        "llm_total_tokens": ctx.total_tokens,
        "llm_total_cost": ctx.total_cost,
        "llm_usage_breakdown": ctx.llm_usage_breakdown,
        "jd_schema_valid": check_jd_schema({
            "company": jd.company, "role": jd.role, "location": jd.location,
            "experience_required": jd.experience_required, "skills": jd.skills,
            "description": jd.description,
        }),
        "soft_resume_relevance": soft_resume_relevance,
        "soft_jd_accuracy": soft_jd_accuracy,
    }
    pack.eval_results = eval_results

    # ── Artifact persistence ──────────────────────────────────────
    artifact_paths: dict[str, str] = {}
    try:
        job_artifact = build_job_extraction_artifact(
            run_id=ctx.run_id, input_mode=ctx.input_mode, jd_hash=jd.jd_hash,
            jd={"company": jd.company, "role": jd.role, "location": jd.location,
                "experience_required": jd.experience_required, "skills": jd.skills,
                "description": jd.description},
        )
        resume_artifact = build_resume_output_artifact(
            run_id=ctx.run_id, jd_hash=jd.jd_hash, resume_base=pack.resume_base,
            fit_score=ctx.fit_score_percent,
            compile_success=bool(pack.pdf_path and pack.pdf_path.exists()),
            compile_rollback_used=ctx.compile_rollback_used,
            condense_retries=ctx.condense_retries,
            pdf_path=str(pack.pdf_path) if pack.pdf_path else None,
            output_dir=str(pack.output_dir) if pack.output_dir else None,
            application_context_id=pack.application_context_id,
            application_output_dir=str(pack.output_dir) if pack.output_dir else None,
            selected_collateral=pack.selected_collateral,
            generated_collateral=pack.generated_collateral,
            collateral_generation_status=pack.collateral_generation_status,
            collateral_generation_reason=pack.collateral_generation_reason,
            collateral_files=pack.collateral_files,
            drive_uploads=pack.drive_uploads,
            single_page_target_met=ctx.single_page_target_met,
            single_page_status=ctx.single_page_status,
            compile_outcome=ctx.compile_outcome,
            fit_score_details=ctx.fit_score_details,
        )
        eval_artifact = build_eval_output_artifact(
            run_id=ctx.run_id, jd_hash=jd.jd_hash, eval_results=eval_results,
        )
        base_dir = ctx.settings.runs_dir / "artifacts"
        artifact_paths["job_extraction"] = str(write_json_artifact(ctx.run_id, "job_extraction.json", job_artifact.to_dict(), base_dir=base_dir))
        artifact_paths["resume_output"] = str(write_json_artifact(ctx.run_id, "resume_output.json", resume_artifact.to_dict(), base_dir=base_dir))
        artifact_paths["eval_output"] = str(write_json_artifact(ctx.run_id, "eval_output.json", eval_artifact.to_dict(), base_dir=base_dir))
    except Exception as ae:
        pack.errors.append(f"Artifact persistence failed: {ae}")

    # ── DB run log ────────────────────────────────────────────────
    run_context = {
        "company": jd.company, "role": jd.role, "jd_hash": jd.jd_hash,
        "resume_base": pack.resume_base, "fit_score": ctx.fit_score_percent,
        "fit_score_details": ctx.fit_score_details,
        "pdf_path": str(pack.pdf_path) if pack.pdf_path else None,
        "drive_link": pack.drive_link, "drive_uploads": pack.drive_uploads,
        "application_context_id": pack.application_context_id,
        "skip_upload": ctx.plan.skip_upload, "skip_calendar": ctx.plan.skip_calendar,
        "input_mode": ctx.input_mode,
        "selected_collateral": pack.selected_collateral,
        "generated_collateral": pack.generated_collateral,
        "collateral_generation_status": pack.collateral_generation_status,
        "collateral_generation_reason": pack.collateral_generation_reason,
        "collateral_files": pack.collateral_files,
        "error_count": len(pack.errors),
        "artifact_paths": artifact_paths,
        "single_page_status": ctx.single_page_status,
        "compile_outcome": ctx.compile_outcome,
    }
    pack.run_id = log_run(
        "inbox", eval_results, run_id=ctx.run_id, job_id=pack.job_id,
        tokens_used=ctx.total_tokens, cost_estimate=ctx.total_cost,
        latency_ms=latency_ms, input_mode=ctx.input_mode,
        skip_upload=ctx.plan.skip_upload, skip_calendar=ctx.plan.skip_calendar,
        errors=pack.errors, context=run_context,
    )
    logger.info("Run logged run_id=%s jd_hash=%s pdf_path=%s errors=%d",
                pack.run_id, jd.jd_hash,
                str(pack.pdf_path) if pack.pdf_path else None, len(pack.errors))
    return pack


# ── Dispatch table ────────────────────────────────────────────────────────────

_DRAFT_TOOLS = {TOOL_DRAFT_EMAIL, TOOL_DRAFT_LINKEDIN, TOOL_DRAFT_REFERRAL}

_HANDLERS: dict[str, Handler] = {
    TOOL_OCR: _handle_ocr,
    TOOL_JD_EXTRACT: _handle_jd_extract,
    TOOL_RESUME_SELECT: _handle_resume_select,
    TOOL_RESUME_MUTATE: _handle_resume_mutate,
    TOOL_COMPILE: _handle_compile,
    TOOL_CALENDAR: _handle_calendar,
    TOOL_DRAFT_EMAIL: _handle_draft,
    TOOL_DRAFT_LINKEDIN: _handle_draft,
    TOOL_DRAFT_REFERRAL: _handle_draft,
    TOOL_DRIVE_UPLOAD: _handle_drive_upload,
    TOOL_DB_LOG: _handle_db_log,
    TOOL_EVAL_LOG: _handle_eval_log,
}


# ── Executor ──────────────────────────────────────────────────────────────────


def _run_step_with_retry(
    step: ToolStep,
    pack: "ApplicationPack",
    ctx: ExecutionContext,
) -> StepResult:
    """Execute a single step, retrying transient errors as configured."""
    handler = _HANDLERS.get(step.tool)
    if handler is None:
        return StepResult(
            step_name=step.name,
            success=False,
            error=f"Unknown tool: {step.tool!r}",
        )

    last_error: Optional[Exception] = None
    for attempt in range(1, step.max_attempts + 1):
        try:
            pack = handler(step, pack, ctx)
            return StepResult(step_name=step.name, success=True, attempts=attempt)
        except Exception as exc:
            last_error = exc
            if step.retry_on_transient and attempt < step.max_attempts and _is_transient_error(exc):
                logger.warning("Step %s transient error (attempt %d/%d): %s",
                               step.name, attempt, step.max_attempts, exc)
                time.sleep(0.3 * attempt)
                continue
            break

    err_msg = f"{step.name} failed: {last_error}"
    return StepResult(
        step_name=step.name,
        success=False,
        attempts=step.max_attempts,
        error=err_msg,
    )


def execute_plan(
    plan: ToolPlan,
    pack: "ApplicationPack",
    settings: Any,
) -> "ApplicationPack":
    """
    Execute all steps in a ToolPlan in order.

    Parameters
    ----------
    plan : ToolPlan produced by build_tool_plan().
    pack : Pre-initialised ApplicationPack (jd may be placeholder).
    settings : core.config.Settings instance.

    Returns
    -------
    The mutated ApplicationPack after all steps complete.
    """
    from evals.logger import generate_run_id

    run_id = generate_run_id()
    pack.run_id = run_id

    ctx = ExecutionContext(
        run_id=run_id,
        start_time=time.time(),
        plan=plan,
        settings=settings,
        input_mode=plan.input_mode,
        llm_usage_breakdown={
            "ocr_cleanup": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "cost_estimate": 0.0},
            "jd_extract":  {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "cost_estimate": 0.0},
            "resume_mutation": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "cost_estimate": 0.0},
            "draft_email":     {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "cost_estimate": 0.0},
            "draft_linkedin":  {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "cost_estimate": 0.0},
            "draft_referral":  {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "cost_estimate": 0.0},
        },
    )

    from core.db import init_db
    init_db()

    for step in plan.steps:
        logger.info("Executor: running step %s (tool=%s)", step.name, step.tool)
        result = _run_step_with_retry(step, pack, ctx)
        ctx.step_results.append(result)

        if not result.success:
            error_msg = result.error or f"Step {step.name} failed"
            pack.errors.append(error_msg)
            logger.warning("Step %s failed: %s", step.name, error_msg)

            # Fatal steps: abort pipeline if resume selection or JD extraction fails
            if step.tool in {TOOL_RESUME_SELECT, TOOL_JD_EXTRACT}:
                logger.error("Fatal step %s failed — aborting pipeline", step.name)
                break

    return pack
