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
from agents.inbox.jd import JDSchema, extract_jd_from_text, get_cached_jd
from agents.inbox.resume import (
    parse_editable_regions,
    select_base_resume,
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

    # Ensure DB exists
    init_db()

    # ── Step 1: OCR if needed ─────────────────────────────────
    if image_path:
        from agents.inbox.ocr import ocr_pipeline
        raw_text = ocr_pipeline(image_path)

    # ── Step 2: Extract & validate JD ─────────────────────────
    jd = extract_jd_from_text(raw_text)

    # Check cache
    cached = get_cached_jd(jd.jd_hash)
    if cached:
        logger.info(f"JD cache hit: {jd.jd_hash}")

    pack = ApplicationPack(jd=jd, resume_base="")

    # ── Step 3: Select resume base ────────────────────────────
    try:
        base_path = select_base_resume(jd.skills, settings.resumes_dir)
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
        try:
            import tempfile
            with tempfile.TemporaryDirectory() as tmp_dir:
                tmp_tex = Path(tmp_dir) / base_path.name
                tmp_tex.write_text(pack.mutated_tex, encoding="utf-8")
                compiled_pdf = compile_latex(tmp_tex, Path(tmp_dir))

                artifacts_dir = settings.runs_dir / "artifacts"
                artifacts_dir.mkdir(parents=True, exist_ok=True)
                persisted_pdf = artifacts_dir / f"{jd.jd_hash}_{base_path.stem}.pdf"
                shutil.copy2(compiled_pdf, persisted_pdf)
                pack.pdf_path = persisted_pdf
        except Exception as e:
            pack.errors.append(f"LaTeX compile failed: {e}")

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

        total_tokens += 0  # token tracking from drafts (simplified)
    except Exception as e:
        pack.errors.append(f"Draft generation failed: {e}")

    # ── Step 9: Log to DB ─────────────────────────────────────
    try:
        job_id = insert_job(
            jd.company, jd.role, jd.jd_hash,
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
        "jd_schema_valid": check_jd_schema(
            {"company": jd.company, "role": jd.role, "location": jd.location,
             "experience_required": jd.experience_required, "skills": jd.skills,
             "description": jd.description}
        ),
    }
    pack.eval_results = eval_results

    try:
        pack.run_id = log_run(
            "inbox",
            eval_results,
            job_id=pack.job_id,
            tokens_used=total_tokens,
            cost_estimate=total_cost,
            latency_ms=latency_ms,
        )
    except Exception as e:
        pack.errors.append(f"Eval logging failed: {e}")

    return pack
