"""
Inbox Agent — main orchestrator for the job application pipeline.

Full pipeline:
1. Ingest (image / URL / text)
2. OCR (if image)
3. Extract & validate JD
4. Select resume base
5. Mutate resume
6. Compile LaTeX
7. Upload to Drive
8. Create Calendar events
9. Generate outreach drafts
10. Log evals & telemetry
"""

from __future__ import annotations

import hashlib
import logging
import re
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from core.config import get_settings
from core.db import init_db, insert_job
from agents.inbox.jd import JDSchema, extract_jd_with_usage, get_cached_jd
from agents.inbox.resume import (
    parse_editable_regions,
    select_base_resume_with_score,
    apply_mutations,
    compile_latex,
)
from evals.hard import (
    check_jd_schema,
    check_edit_scope,
    check_forbidden_claims,
    check_draft_length,
    check_cost,
)
from evals.logger import log_run

logger = logging.getLogger(__name__)


@dataclass
class ApplicationPack:
    """Result of a full pipeline run."""

    jd: JDSchema
    resume_base: str
    mutated_tex: Optional[str] = None
    pdf_path: Optional[Path] = None
    drive_link: Optional[str] = None
    email_draft: Optional[str] = None
    linkedin_draft: Optional[str] = None
    referral_draft: Optional[str] = None
    job_id: Optional[int] = None
    run_id: Optional[str] = None
    eval_results: dict = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


def _extract_bullets(text: str) -> list[str]:
    """Extract LaTeX item bullets for forbidden-claim checks."""
    bullets: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(r"\item "):
            bullets.append(stripped.replace(r"\item ", "", 1).strip())
    return bullets


def _outside_editable_content_changed(original_tex: str, mutated_tex: str) -> bool:
    """Detect whether content outside editable markers changed."""
    pattern = re.compile(r"(%%BEGIN_EDITABLE)(.*?)(%%END_EDITABLE)", re.DOTALL)
    original_masked = pattern.sub(r"\1\n__EDITABLE_REGION__\n\3", original_tex)
    mutated_masked = pattern.sub(r"\1\n__EDITABLE_REGION__\n\3", mutated_tex)
    return original_masked != mutated_masked


def _keyword_coverage(skills: list[str], text: str) -> float:
    """Compute simple keyword coverage ratio for JD skills in resume text."""
    normalized_skills = [s.strip().lower() for s in skills if isinstance(s, str) and s.strip()]
    if not normalized_skills:
        return 1.0
    haystack = text.lower()
    matched = sum(1 for s in normalized_skills if s in haystack)
    return matched / len(normalized_skills)


def _slugify_filename_part(value: str, fallback: str) -> str:
    """Normalize free text into a filesystem-safe filename segment."""
    text = (value or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    text = text.strip("_")
    return text or fallback


def run_pipeline(
    raw_text: str,
    *,
    image_path: Optional[Path] = None,
    skip_upload: bool = False,
    skip_calendar: bool = False,
) -> ApplicationPack:
    """
    Execute the full job application pipeline.

    Parameters
    ----------
    raw_text : Raw JD text (or cleaned OCR output)
    image_path : If provided, run OCR first
    skip_upload : Skip Google Drive upload
    skip_calendar : Skip Google Calendar event creation
    """
    settings = get_settings()
    start_time = time.time()
    total_tokens = 0
    total_cost = 0.0
    is_url_input = bool(re.search(r"https?://", raw_text)) if raw_text else False
    input_mode = "image" if image_path else ("url" if is_url_input else "text")
    llm_usage_breakdown: dict[str, dict[str, float | int]] = {
        "ocr_cleanup": {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "cost_estimate": 0.0,
        },
        "jd_extract": {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "cost_estimate": 0.0,
        },
        "resume_mutation": {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "cost_estimate": 0.0,
        },
        "draft_email": {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "cost_estimate": 0.0,
        },
        "draft_linkedin": {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "cost_estimate": 0.0,
        },
        "draft_referral": {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "cost_estimate": 0.0,
        },
    }

    # Ensure DB exists
    init_db()

    # ── Step 1: OCR if needed ─────────────────────────────────
    if image_path:
        from agents.inbox.ocr import ocr_pipeline_with_usage

        raw_text, ocr_usage = ocr_pipeline_with_usage(image_path)
        llm_usage_breakdown["ocr_cleanup"] = ocr_usage
        total_tokens += int(ocr_usage.get("total_tokens", 0))
        total_cost += float(ocr_usage.get("cost_estimate", 0.0))

    # ── Step 2: Extract & validate JD ─────────────────────────
    jd, jd_usage = extract_jd_with_usage(raw_text)
    llm_usage_breakdown["jd_extract"] = jd_usage
    total_tokens += int(jd_usage.get("total_tokens", 0))
    total_cost += float(jd_usage.get("cost_estimate", 0.0))

    # Check cache
    cached = get_cached_jd(jd.jd_hash)
    if cached:
        logger.info(f"JD cache hit: {jd.jd_hash}")

    pack = ApplicationPack(jd=jd, resume_base="")
    fit_score_percent = 0
    compile_rollback_used = False

    # ── Step 3: Select resume base ────────────────────────────
    try:
        base_path, fit_score = select_base_resume_with_score(jd.skills, settings.resumes_dir)
        fit_score_percent = int(round(fit_score * 100))
        pack.resume_base = base_path.name
        logger.info(f"Selected resume: {base_path.name}")
    except FileNotFoundError as e:
        pack.errors.append(f"Resume selection failed: {e}")
        return pack

    # ── Step 4: Mutate resume ─────────────────────────────────
    try:
        import json
        from core.llm import chat_text
        from core.prompts import load_prompt

        original_tex = base_path.read_text(encoding="utf-8")
        regions = parse_editable_regions(original_tex)

        if regions:
            # Build bullets from editable regions
            editable_content = "\n".join(r.content for r in regions)

            # Load bullet bank
            bullet_bank = json.loads(
                settings.bullet_bank_path.read_text(encoding="utf-8")
            )
            bullet_bank_text = "\n".join(b["bullet"] for b in bullet_bank)

            system = load_prompt("resume_mutate", version=1)
            user_msg = (
                f"JD:\n{json.dumps({'company': jd.company, 'role': jd.role, 'skills': jd.skills, 'description': jd.description})}\n\n"
                f"Current editable bullets:\n{editable_content}\n\n"
                f"Bullet bank:\n{bullet_bank_text}"
            )

            response = chat_text(system, user_msg, json_mode=True)
            total_tokens += response.total_tokens
            total_cost += response.cost_estimate
            llm_usage_breakdown["resume_mutation"] = {
                "prompt_tokens": response.prompt_tokens,
                "completion_tokens": response.completion_tokens,
                "total_tokens": response.total_tokens,
                "cost_estimate": response.cost_estimate,
            }

            mutations_data = json.loads(response.text)
            mutations = mutations_data.get("mutations", [])

            pack.mutated_tex = apply_mutations(original_tex, mutations)
        else:
            pack.mutated_tex = original_tex

    except Exception as e:
        pack.errors.append(f"Resume mutation failed: {e}")
        pack.mutated_tex = original_tex if 'original_tex' in dir() else None

    # ── Step 5: Compile LaTeX ─────────────────────────────────
    if pack.mutated_tex:
        import tempfile

        def _compile_and_persist(tex_content: str, artifact_suffix: str = "") -> Path:
            with tempfile.TemporaryDirectory() as tmp_dir:
                tmp_tex = Path(tmp_dir) / base_path.name
                tmp_tex.write_text(tex_content, encoding="utf-8")
                compiled_pdf = compile_latex(tmp_tex, Path(tmp_dir))

                artifacts_dir = settings.runs_dir / "artifacts"
                artifacts_dir.mkdir(parents=True, exist_ok=True)
                company_slug = _slugify_filename_part(jd.company, "company")
                role_slug = _slugify_filename_part(jd.role, "role")
                short_hash = jd.jd_hash[:8]
                persisted_pdf = artifacts_dir / (
                    f"{company_slug}_{role_slug}_{base_path.stem}_{short_hash}{artifact_suffix}.pdf"
                )
                shutil.copy2(compiled_pdf, persisted_pdf)
                return persisted_pdf

        try:
            pack.pdf_path = _compile_and_persist(pack.mutated_tex)
        except Exception as e:
            pack.errors.append(f"LaTeX compile failed: {e}")
            try:
                # Roll back to base resume compile to avoid losing artifact generation entirely.
                original_tex_for_fallback = base_path.read_text(encoding="utf-8")
                pack.pdf_path = _compile_and_persist(original_tex_for_fallback, "_fallback")
                compile_rollback_used = True
                pack.errors.append("LaTeX compile rollback applied: used base resume artifact.")
            except Exception as fallback_error:
                pack.errors.append(f"LaTeX compile fallback failed: {fallback_error}")

        logger.info(
            "Compile result jd_hash=%s success=%s pdf_path=%s rollback_used=%s",
            jd.jd_hash,
            bool(pack.pdf_path),
            str(pack.pdf_path) if pack.pdf_path else None,
            compile_rollback_used,
        )

    # ── Step 6: Upload to Drive ───────────────────────────────
    if not skip_upload and pack.pdf_path:
        try:
            from integrations.drive import upload_to_drive
            pack.drive_link = upload_to_drive(
                pack.pdf_path, jd.company, jd.role
            )
        except Exception as e:
            pack.errors.append(f"Drive upload failed: {e}")

    # ── Step 7: Calendar events ───────────────────────────────
    if not skip_calendar:
        try:
            from integrations.calendar import create_application_events
            create_application_events(jd.company, jd.role)
        except Exception as e:
            pack.errors.append(f"Calendar events failed: {e}")

    # ── Step 8: Generate drafts ───────────────────────────────
    try:
        from agents.inbox.drafts import (
            generate_email_draft,
            generate_linkedin_dm,
            generate_referral_template,
        )
        import json as _json

        profile = _json.loads(settings.profile_path.read_text(encoding="utf-8"))
        identity = profile.get("identity", {})
        name = identity.get("name", "Karan")
        positioning = profile.get("positioning", {}).get("ai", "Product Manager")

        email = generate_email_draft(name, positioning, jd.company, jd.role)
        linkedin = generate_linkedin_dm(name, positioning, jd.company, jd.role)
        referral = generate_referral_template(name, positioning, jd.company, jd.role)

        pack.email_draft = email.text
        pack.linkedin_draft = linkedin.text
        pack.referral_draft = referral.text

        total_tokens += email.total_tokens + linkedin.total_tokens + referral.total_tokens
        total_cost += email.cost_estimate + linkedin.cost_estimate + referral.cost_estimate
        llm_usage_breakdown["draft_email"] = {
            "prompt_tokens": email.prompt_tokens,
            "completion_tokens": email.completion_tokens,
            "total_tokens": email.total_tokens,
            "cost_estimate": email.cost_estimate,
        }
        llm_usage_breakdown["draft_linkedin"] = {
            "prompt_tokens": linkedin.prompt_tokens,
            "completion_tokens": linkedin.completion_tokens,
            "total_tokens": linkedin.total_tokens,
            "cost_estimate": linkedin.cost_estimate,
        }
        llm_usage_breakdown["draft_referral"] = {
            "prompt_tokens": referral.prompt_tokens,
            "completion_tokens": referral.completion_tokens,
            "total_tokens": referral.total_tokens,
            "cost_estimate": referral.cost_estimate,
        }
    except Exception as e:
        pack.errors.append(f"Draft generation failed: {e}")

    # ── Step 9: Log to DB ─────────────────────────────────────
    try:
        job_id = insert_job(
            jd.company, jd.role, jd.jd_hash,
            fit_score=fit_score_percent,
            resume_used=pack.resume_base,
            drive_link=pack.drive_link,
        )
        pack.job_id = job_id
    except Exception as e:
        pack.errors.append(f"DB insert failed: {e}")

    # ── Step 10: Eval logging ─────────────────────────────────
    latency_ms = int((time.time() - start_time) * 1000)

    original_bullets: list[str] = []
    mutated_bullets: list[str] = []
    forbidden_claims_count = 0
    edit_scope_violations = 0

    if 'original_tex' in locals() and pack.mutated_tex:
        outside_changed = _outside_editable_content_changed(original_tex, pack.mutated_tex)
        edit_scope_ok = check_edit_scope(
            original_tex,
            pack.mutated_tex,
            outside_changed=outside_changed,
        )
        edit_scope_violations = 0 if edit_scope_ok else 1

        original_bullets = _extract_bullets(original_tex)
        mutated_bullets = _extract_bullets(pack.mutated_tex)
        try:
            import json as _json
            bullet_bank_data = _json.loads(settings.bullet_bank_path.read_text(encoding="utf-8"))
            bullet_bank = [b.get("bullet", "") for b in bullet_bank_data if isinstance(b, dict)]
        except Exception:
            bullet_bank = []
        forbidden_claims_count = check_forbidden_claims(
            original_bullets,
            mutated_bullets,
            bullet_bank,
        )

    eval_results = {
        "compile_success": bool(pack.pdf_path and pack.pdf_path.exists()),
        "forbidden_claims_count": forbidden_claims_count,
        "edit_scope_violations": edit_scope_violations,
        "draft_length_ok": check_draft_length(pack.linkedin_draft or "", max_chars=300),
        "cost_ok": check_cost(total_cost, threshold=settings.max_cost_per_job),
        "keyword_coverage": _keyword_coverage(jd.skills, pack.mutated_tex or ""),
        "compile_rollback_used": compile_rollback_used,
        "llm_total_tokens": total_tokens,
        "llm_total_cost": total_cost,
        "llm_usage_breakdown": llm_usage_breakdown,
        "jd_schema_valid": check_jd_schema(
            {"company": jd.company, "role": jd.role, "location": jd.location,
             "experience_required": jd.experience_required, "skills": jd.skills,
             "description": jd.description}
        ),
    }
    pack.eval_results = eval_results

    try:
        run_context = {
            "company": jd.company,
            "role": jd.role,
            "jd_hash": jd.jd_hash,
            "resume_base": pack.resume_base,
            "fit_score": fit_score_percent,
            "pdf_path": str(pack.pdf_path) if pack.pdf_path else None,
            "drive_link": pack.drive_link,
            "skip_upload": skip_upload,
            "skip_calendar": skip_calendar,
            "input_mode": input_mode,
            "error_count": len(pack.errors),
        }
        pack.run_id = log_run(
            "inbox",
            eval_results,
            job_id=pack.job_id,
            tokens_used=total_tokens,
            cost_estimate=total_cost,
            latency_ms=latency_ms,
            input_mode=input_mode,
            skip_upload=skip_upload,
            skip_calendar=skip_calendar,
            errors=pack.errors,
            context=run_context,
        )
        logger.info(
            "Run logged run_id=%s jd_hash=%s pdf_path=%s errors=%s",
            pack.run_id,
            jd.jd_hash,
            str(pack.pdf_path) if pack.pdf_path else None,
            len(pack.errors),
        )
    except Exception as e:
        pack.errors.append(f"Eval logging failed: {e}")

    return pack
