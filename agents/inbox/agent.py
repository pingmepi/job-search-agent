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
import json
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
    select_base_resume_with_details,
    apply_mutations,
    compile_latex,
    get_pdf_page_count,
)
from evals.hard import (
    check_jd_schema,
    check_edit_scope,
    check_forbidden_claims,
    check_draft_length,
    check_cost,
)
from evals.logger import generate_run_id, log_run

logger = logging.getLogger(__name__)

SUPPORTED_COLLATERAL_TYPES = ("email", "linkedin", "referral")


@dataclass
class ApplicationPack:
    """Result of a full pipeline run."""

    jd: JDSchema
    resume_base: str
    mutated_tex: Optional[str] = None
    pdf_path: Optional[Path] = None
    output_dir: Optional[Path] = None
    drive_link: Optional[str] = None
    drive_uploads: dict = field(default_factory=dict)
    application_context_id: Optional[str] = None
    selected_collateral: list[str] = field(default_factory=list)
    generated_collateral: list[str] = field(default_factory=list)
    collateral_generation_status: str = "not_requested"
    collateral_generation_reason: Optional[str] = None
    collateral_files: dict[str, Optional[str]] = field(default_factory=dict)
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


def _is_transient_llm_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    transient_markers = (
        "rate limit",
        "too many requests",
        "429",
        "timeout",
        "timed out",
        "connection",
        "temporarily unavailable",
        "server error",
        "503",
        "502",
        "504",
    )
    return any(marker in msg for marker in transient_markers)


def _extract_first_json_object(text: str) -> str | None:
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
            continue
        if ch == "{":
            depth += 1
            continue
        if ch == "}":
            depth -= 1
            if depth == 0:
                return text[start:idx + 1]
    return None


def _parse_json_object_from_llm_text(text: str) -> dict:
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
        block = fenced.group(1).strip()
        try:
            parsed = json.loads(block)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

    extracted = _extract_first_json_object(candidate)
    if extracted:
        parsed = json.loads(extracted)
        if isinstance(parsed, dict):
            return parsed

    preview = candidate[:180].replace("\n", " ")
    raise ValueError(f"LLM response did not contain parseable JSON object. Preview: {preview!r}")


def _chat_json_with_retry(
    *,
    system: str,
    user_msg: str,
    step_name: str,
    max_attempts: int = 3,
) -> tuple[dict, object]:
    from core.llm import chat_text

    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            response = chat_text(system, user_msg, json_mode=True)
            parsed = _parse_json_object_from_llm_text(response.text)
            return parsed, response
        except Exception as exc:
            last_error = exc
            retryable = isinstance(exc, ValueError) or _is_transient_llm_error(exc)
            if attempt < max_attempts and retryable:
                time.sleep(0.2 * attempt)
                continue
            raise RuntimeError(f"{step_name} failed after {attempt} attempts: {exc}") from exc

    if last_error:
        raise RuntimeError(f"{step_name} failed: {last_error}") from last_error
    raise RuntimeError(f"{step_name} failed without a concrete error")


def _normalize_collateral_selection(
    selected_collateral: Optional[list[str] | tuple[str, ...] | set[str]],
) -> tuple[list[str], list[str]]:
    """Normalize selected collateral values into canonical order."""
    if not selected_collateral:
        return [], []
    normalized: list[str] = []
    invalid: list[str] = []
    seen: set[str] = set()
    for raw in selected_collateral:
        value = str(raw or "").strip().lower()
        if not value:
            continue
        if value not in SUPPORTED_COLLATERAL_TYPES:
            invalid.append(value)
            continue
        if value in seen:
            continue
        seen.add(value)
        normalized.append(value)
    ordered = [item for item in SUPPORTED_COLLATERAL_TYPES if item in seen]
    return ordered, invalid


def _cleanup_terminal_failure_pdfs(output_dir: Path | None) -> list[str]:
    if output_dir is None or not output_dir.exists():
        return []
    removed: list[str] = []
    for pdf in output_dir.glob("*.pdf"):
        pdf.unlink(missing_ok=True)
        removed.append(pdf.name)
    return removed


def run_pipeline(
    raw_text: str,
    *,
    image_path: Optional[Path] = None,
    selected_collateral: Optional[list[str] | tuple[str, ...] | set[str]] = None,
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
    run_id = generate_run_id()
    start_time = time.time()
    total_tokens = 0
    total_cost = 0.0
    generation_ids: list[tuple[str, str]] = []  # (step_name, gen_id)
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
        if ocr_usage.get("generation_id"):
            generation_ids.append(("ocr_cleanup", ocr_usage["generation_id"]))

    # ── Step 2: Extract & validate JD ─────────────────────────
    jd, jd_usage = extract_jd_with_usage(raw_text)
    llm_usage_breakdown["jd_extract"] = jd_usage
    total_tokens += int(jd_usage.get("total_tokens", 0))
    if jd_usage.get("generation_id"):
        generation_ids.append(("jd_extract", jd_usage["generation_id"]))

    # Check cache
    cached = get_cached_jd(jd.jd_hash)
    if cached:
        logger.info(f"JD cache hit: {jd.jd_hash}")

    pack = ApplicationPack(jd=jd, resume_base="")
    pack.run_id = run_id
    normalized_collateral, invalid_collateral = _normalize_collateral_selection(selected_collateral)
    pack.selected_collateral = normalized_collateral
    pack.collateral_files = {key: None for key in SUPPORTED_COLLATERAL_TYPES}
    if invalid_collateral:
        pack.collateral_generation_status = "blocked_invalid_selection"
        pack.collateral_generation_reason = (
            "Invalid collateral type(s): " + ", ".join(sorted(set(invalid_collateral)))
        )
        pack.errors.append(
            f"Collateral generation skipped: {pack.collateral_generation_reason}"
        )
    elif selected_collateral is None:
        pack.collateral_generation_status = "blocked_missing_selection"
        pack.collateral_generation_reason = "Selection was not provided."
        pack.errors.append(
            "Collateral generation skipped: explicit selection not provided."
        )
    elif not normalized_collateral:
        pack.collateral_generation_status = "skipped_no_selection"
        pack.collateral_generation_reason = "User explicitly chose no collateral."
    else:
        pack.collateral_generation_status = "selected"
    fit_score_percent = 0
    fit_score_details: dict = {}
    compile_rollback_used = False
    truthfulness_fallback_used = False
    single_page_target_met = False
    single_page_status = "not_checked"
    compile_outcome: str | None = None

    # ── Step 3: Select resume base ────────────────────────────
    try:
        base_path, fit_score, fit_score_details = select_base_resume_with_details(
            jd.skills,
            settings.resumes_dir,
        )
        fit_score_percent = int(round(fit_score * 100))
        pack.resume_base = base_path.name
        logger.info(f"Selected resume: {base_path.name}")
    except FileNotFoundError as e:
        pack.errors.append(f"Resume selection failed: {e}")
        return pack

    # ── Step 4: Mutate resume ─────────────────────────────────
    try:
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
            bullet_bank_values = [b["bullet"] for b in bullet_bank if isinstance(b, dict) and "bullet" in b]
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
            )
            total_tokens += response.total_tokens
            if response.generation_id:
                generation_ids.append(("resume_mutation", response.generation_id))
            llm_usage_breakdown["resume_mutation"] = {
                "prompt_tokens": response.prompt_tokens,
                "completion_tokens": response.completion_tokens,
                "total_tokens": response.total_tokens,
                "cost_estimate": response.cost_estimate,
            }

            mutations = mutations_data.get("mutations", [])

            pack.mutated_tex = apply_mutations(original_tex, mutations)

            # Enforce safe behavior if fabricated claims appear in mutated bullets.
            original_bullets_pre = _extract_bullets(original_tex)
            mutated_bullets_pre = _extract_bullets(pack.mutated_tex)
            forbidden_claims_pre = check_forbidden_claims(
                original_bullets_pre,
                mutated_bullets_pre,
                bullet_bank_values,
            )
            if forbidden_claims_pre > 0:
                truthfulness_fallback_used = True
                pack.errors.append(
                    f"Truthfulness safeguard triggered ({forbidden_claims_pre} suspected fabricated claims); "
                    "using safe base resume content."
                )
                pack.mutated_tex = original_tex
        else:
            pack.mutated_tex = original_tex

    except Exception as e:
        pack.errors.append(f"Resume mutation failed: {e}")
        pack.mutated_tex = original_tex if 'original_tex' in dir() else None

    # ── Step 5: Compile LaTeX + single-page enforcement ────────
    condense_retries = 0
    if pack.mutated_tex:
        import tempfile

        # Create per-application output folder
        company_slug = _slugify_filename_part(jd.company, "company")
        role_slug = _slugify_filename_part(jd.role, "role")
        short_hash = jd.jd_hash[:8]
        application_context_id = f"{company_slug}_{role_slug}_{short_hash}"
        app_output_dir = settings.runs_dir / "artifacts" / application_context_id
        app_output_dir.mkdir(parents=True, exist_ok=True)
        pack.application_context_id = application_context_id
        pack.output_dir = app_output_dir

        def _compile_and_persist(tex_content: str, artifact_suffix: str = "") -> Path:
            with tempfile.TemporaryDirectory() as tmp_dir:
                tmp_tex = Path(tmp_dir) / base_path.name
                tmp_tex.write_text(tex_content, encoding="utf-8")
                compiled_pdf = compile_latex(tmp_tex, Path(tmp_dir))

                persisted_pdf = app_output_dir / (
                    f"{base_path.stem}{artifact_suffix}.pdf"
                )
                shutil.copy2(compiled_pdf, persisted_pdf)
                return persisted_pdf

        def _safe_page_count(pdf_path: Path) -> int | None:
            try:
                return get_pdf_page_count(pdf_path)
            except Exception as page_err:
                pack.errors.append(f"Page count check failed: {page_err}")
                return None

        try:
            pack.pdf_path = _compile_and_persist(pack.mutated_tex)

            # ── Single-page enforcement loop ──────────────────
            MAX_CONDENSE_RETRIES = 2
            current_tex = pack.mutated_tex
            while pack.pdf_path and pack.pdf_path.exists():
                page_count = _safe_page_count(pack.pdf_path)
                if page_count is None:
                    single_page_status = "unknown"
                    compile_outcome = "mutated_success"
                    break
                if page_count <= 1:
                    single_page_target_met = True
                    single_page_status = "met"
                    compile_outcome = "mutated_success"
                    break
                if condense_retries >= MAX_CONDENSE_RETRIES:
                    pack.errors.append(
                        f"Resume is {page_count} pages after {condense_retries} condense retries. "
                        "Falling back to safe base resume PDF."
                    )
                    try:
                        original_tex_for_fallback = base_path.read_text(encoding="utf-8")
                        pack.pdf_path = _compile_and_persist(original_tex_for_fallback, "_fallback")
                        compile_rollback_used = True
                        fallback_pages = _safe_page_count(pack.pdf_path)
                        if fallback_pages is not None and fallback_pages <= 1:
                            compile_outcome = "fallback_success"
                            single_page_target_met = True
                            single_page_status = "fallback_base_used"
                        else:
                            compile_outcome = None
                            single_page_target_met = False
                            single_page_status = "failed_multi_page_terminal"
                            pack.errors.append(
                                "Terminal fallback resume exceeds one page "
                                f"({fallback_pages if fallback_pages is not None else 'unknown'} pages). "
                                "Run marked failed; please tighten resume content and retry."
                            )
                            removed = _cleanup_terminal_failure_pdfs(app_output_dir)
                            if removed:
                                pack.errors.append(
                                    "Removed non-compliant terminal PDF artifacts: " + ", ".join(sorted(removed))
                                )
                            pack.pdf_path = None
                    except Exception as fallback_error:
                        pack.errors.append(f"LaTeX compile fallback failed: {fallback_error}")
                        single_page_status = "fallback_failed"
                    break

                logger.info(
                    "PDF is %d pages, running condense pass %d/%d",
                    page_count, condense_retries + 1, MAX_CONDENSE_RETRIES,
                )
                try:
                    from core.prompts import load_prompt as _condense_load

                    condense_system = _condense_load("resume_condense", version=1)
                    editable_content = "\n".join(
                        r.content for r in parse_editable_regions(current_tex)
                    )
                    condense_user = (
                        f"Page count: {page_count} (must be 1)\n\n"
                        f"JD context:\n{json.dumps({'company': jd.company, 'role': jd.role, 'skills': jd.skills})}\n\n"
                        f"Current editable content:\n{editable_content}"
                    )
                    condense_data, condense_resp = _chat_json_with_retry(
                        system=condense_system,
                        user_msg=condense_user,
                        step_name=f"Condense pass {condense_retries + 1}",
                    )
                    total_tokens += condense_resp.total_tokens
                    if condense_resp.generation_id:
                        generation_ids.append((f"condense_pass_{condense_retries + 1}", condense_resp.generation_id))

                    condense_mutations = condense_data.get("mutations", [])

                    # Handle bullet removals as mutations to empty string
                    for removed in condense_data.get("bullets_removed", []):
                        original = removed.get("original", "")
                        if original:
                            condense_mutations.append(
                                {"original": original, "replacement": ""}
                            )

                    if condense_mutations:
                        current_tex = apply_mutations(current_tex, condense_mutations)
                        pack.mutated_tex = current_tex
                        pack.pdf_path = _compile_and_persist(current_tex, f"_v{condense_retries + 2}")

                    condense_retries += 1
                except Exception as ce:
                    pack.errors.append(f"Condense pass {condense_retries + 1} failed: {ce}")
                    condense_retries += 1

        except Exception as e:
            pack.errors.append(f"LaTeX compile failed: {e}")
            try:
                original_tex_for_fallback = base_path.read_text(encoding="utf-8")
                pack.pdf_path = _compile_and_persist(original_tex_for_fallback, "_fallback")
                compile_rollback_used = True
                fallback_pages = _safe_page_count(pack.pdf_path)
                if fallback_pages is not None and fallback_pages <= 1:
                    compile_outcome = "fallback_success"
                    single_page_target_met = True
                    single_page_status = "fallback_base_used"
                    pack.errors.append("LaTeX compile rollback applied: used base resume artifact.")
                else:
                    compile_outcome = None
                    single_page_target_met = False
                    single_page_status = "failed_multi_page_terminal"
                    pack.errors.append(
                        "LaTeX compile rollback produced a non-compliant resume "
                        f"({fallback_pages if fallback_pages is not None else 'unknown'} pages). "
                        "Run marked failed; please tighten resume content and retry."
                    )
                    removed = _cleanup_terminal_failure_pdfs(app_output_dir)
                    if removed:
                        pack.errors.append(
                            "Removed non-compliant terminal PDF artifacts: " + ", ".join(sorted(removed))
                        )
                    pack.pdf_path = None
            except Exception as fallback_error:
                pack.errors.append(f"LaTeX compile fallback failed: {fallback_error}")
                single_page_status = "fallback_failed"

        logger.info(
            "Compile result jd_hash=%s success=%s pdf_path=%s rollback_used=%s condense_retries=%d",
            jd.jd_hash,
            bool(pack.pdf_path),
            str(pack.pdf_path) if pack.pdf_path else None,
            compile_rollback_used,
            condense_retries,
        )

    # ── Step 6: Calendar events ───────────────────────────────
    if not skip_calendar:
        try:
            from integrations.calendar import create_application_events
            create_application_events(jd.company, jd.role)
        except Exception as e:
            pack.errors.append(f"Calendar events failed: {e}")

    # ── Step 7: Generate drafts ───────────────────────────────
    if pack.selected_collateral:
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

            if "email" in pack.selected_collateral:
                email = generate_email_draft(name, positioning, jd.company, jd.role)
                pack.email_draft = email.text
                total_tokens += email.total_tokens
                pack.generated_collateral.append("email")
                generation_id = getattr(email, "generation_id", None)
                if generation_id:
                    generation_ids.append(("draft_email", generation_id))
                llm_usage_breakdown["draft_email"] = {
                    "prompt_tokens": email.prompt_tokens,
                    "completion_tokens": email.completion_tokens,
                    "total_tokens": email.total_tokens,
                    "cost_estimate": email.cost_estimate,
                }

            if "linkedin" in pack.selected_collateral:
                linkedin = generate_linkedin_dm(name, positioning, jd.company, jd.role)
                pack.linkedin_draft = linkedin.text
                total_tokens += linkedin.total_tokens
                pack.generated_collateral.append("linkedin")
                generation_id = getattr(linkedin, "generation_id", None)
                if generation_id:
                    generation_ids.append(("draft_linkedin", generation_id))
                llm_usage_breakdown["draft_linkedin"] = {
                    "prompt_tokens": linkedin.prompt_tokens,
                    "completion_tokens": linkedin.completion_tokens,
                    "total_tokens": linkedin.total_tokens,
                    "cost_estimate": linkedin.cost_estimate,
                }

            if "referral" in pack.selected_collateral:
                referral = generate_referral_template(name, positioning, jd.company, jd.role)
                pack.referral_draft = referral.text
                total_tokens += referral.total_tokens
                pack.generated_collateral.append("referral")
                generation_id = getattr(referral, "generation_id", None)
                if generation_id:
                    generation_ids.append(("draft_referral", generation_id))
                llm_usage_breakdown["draft_referral"] = {
                    "prompt_tokens": referral.prompt_tokens,
                    "completion_tokens": referral.completion_tokens,
                    "total_tokens": referral.total_tokens,
                    "cost_estimate": referral.cost_estimate,
                }
            pack.collateral_generation_status = "generated"
        except Exception as e:
            pack.collateral_generation_status = "generation_failed"
            pack.errors.append(f"Draft generation failed: {e}")

    # ── Step 7b: Persist drafts to output folder ──────────────
    if pack.output_dir and pack.output_dir.exists():
        try:
            if pack.email_draft:
                email_path = pack.output_dir / "email_draft.txt"
                email_path.write_text(
                    pack.email_draft, encoding="utf-8"
                )
                pack.collateral_files["email"] = str(email_path)
            if pack.linkedin_draft:
                linkedin_path = pack.output_dir / "linkedin_dm.txt"
                linkedin_path.write_text(
                    pack.linkedin_draft, encoding="utf-8"
                )
                pack.collateral_files["linkedin"] = str(linkedin_path)
            if pack.referral_draft:
                referral_path = pack.output_dir / "referral.txt"
                referral_path.write_text(
                    pack.referral_draft, encoding="utf-8"
                )
                pack.collateral_files["referral"] = str(referral_path)
            logger.info("Drafts saved to %s", pack.output_dir)
        except Exception as e:
            pack.errors.append(f"Draft file persistence failed: {e}")

    # ── Step 8: Upload to Drive ───────────────────────────────
    if not skip_upload and pack.pdf_path:
        try:
            from integrations.drive import upload_application_artifacts
            drive_files: dict[str, Path] = {"resume_pdf": pack.pdf_path}
            for collateral_key, file_path in pack.collateral_files.items():
                if file_path:
                    drive_files[collateral_key] = Path(file_path)
            pack.drive_uploads = upload_application_artifacts(
                files=drive_files,
                company=jd.company,
                role=jd.role,
                application_context_id=pack.application_context_id or run_id,
            )
            resume_upload = pack.drive_uploads.get("files", {}).get("resume_pdf", {})
            if isinstance(resume_upload, dict):
                pack.drive_link = resume_upload.get("webViewLink")
        except Exception as e:
            pack.errors.append(f"Drive upload failed: {e}")

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
    if truthfulness_fallback_used and forbidden_claims_count == 0:
        forbidden_claims_count = 1

    # ── Resolve real costs from OpenRouter ─────────────────────
    try:
        from core.llm import resolve_costs_batch

        gen_id_list = [gid for _, gid in generation_ids]
        resolved = resolve_costs_batch(gen_id_list)

        # Backfill per-step costs and compute total
        for step_name, gen_id in generation_ids:
            cost = resolved.get(gen_id, 0.0)
            total_cost += cost
            if step_name in llm_usage_breakdown:
                llm_usage_breakdown[step_name]["cost_estimate"] = cost
    except Exception as cost_err:
        pack.errors.append(f"Cost resolution failed: {cost_err}")

    # ── Soft evals (LLM-judged quality signals) ────────────────
    soft_resume_relevance: float | None = None
    soft_jd_accuracy: float | None = None

    try:
        from evals.soft import score_resume_relevance, score_jd_accuracy

        if pack.mutated_tex:
            soft_resume_relevance = score_resume_relevance(
                jd.description, pack.mutated_tex,
            )

        soft_jd_accuracy = score_jd_accuracy(
            raw_text,
            {
                "company": jd.company,
                "role": jd.role,
                "location": jd.location,
                "experience_required": jd.experience_required,
                "skills": jd.skills,
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
        "cost_ok": check_cost(total_cost, threshold=settings.max_cost_per_job),
        "keyword_coverage": _keyword_coverage(jd.skills, pack.mutated_tex or ""),
        "compile_rollback_used": compile_rollback_used,
        "truthfulness_fallback_used": truthfulness_fallback_used,
        "condense_retries": condense_retries,
        "single_page_target_met": single_page_target_met,
        "single_page_status": single_page_status,
        "compile_outcome": compile_outcome,
        "selected_collateral": pack.selected_collateral,
        "generated_collateral": pack.generated_collateral,
        "collateral_generation_status": pack.collateral_generation_status,
        "collateral_generation_reason": pack.collateral_generation_reason,
        "collateral_files": pack.collateral_files,
        "application_context_id": pack.application_context_id,
        "drive_uploads": pack.drive_uploads,
        "llm_total_tokens": total_tokens,
        "llm_total_cost": total_cost,
        "llm_usage_breakdown": llm_usage_breakdown,
        "jd_schema_valid": check_jd_schema(
            {"company": jd.company, "role": jd.role, "location": jd.location,
             "experience_required": jd.experience_required, "skills": jd.skills,
             "description": jd.description}
        ),
        "soft_resume_relevance": soft_resume_relevance,
        "soft_jd_accuracy": soft_jd_accuracy,
    }
    pack.eval_results = eval_results

    try:
        artifact_paths: dict[str, str] = {}
        try:
            from core.artifacts import write_json_artifact
            from core.contracts import (
                build_eval_output_artifact,
                build_job_extraction_artifact,
                build_resume_output_artifact,
            )

            job_artifact = build_job_extraction_artifact(
                run_id=run_id,
                input_mode=input_mode,
                jd_hash=jd.jd_hash,
                jd={
                    "company": jd.company,
                    "role": jd.role,
                    "location": jd.location,
                    "experience_required": jd.experience_required,
                    "skills": jd.skills,
                    "description": jd.description,
                },
            )
            resume_artifact = build_resume_output_artifact(
                run_id=run_id,
                jd_hash=jd.jd_hash,
                resume_base=pack.resume_base,
                fit_score=fit_score_percent,
                compile_success=bool(pack.pdf_path and pack.pdf_path.exists()),
                compile_rollback_used=compile_rollback_used,
                condense_retries=condense_retries,
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
                single_page_target_met=single_page_target_met,
                single_page_status=single_page_status,
                compile_outcome=compile_outcome,
                fit_score_details=fit_score_details,
            )
            eval_artifact = build_eval_output_artifact(
                run_id=run_id,
                jd_hash=jd.jd_hash,
                eval_results=eval_results,
            )
            artifact_paths["job_extraction"] = str(
                write_json_artifact(
                    run_id,
                    "job_extraction.json",
                    job_artifact.to_dict(),
                    base_dir=settings.runs_dir / "artifacts",
                )
            )
            artifact_paths["resume_output"] = str(
                write_json_artifact(
                    run_id,
                    "resume_output.json",
                    resume_artifact.to_dict(),
                    base_dir=settings.runs_dir / "artifacts",
                )
            )
            artifact_paths["eval_output"] = str(
                write_json_artifact(
                    run_id,
                    "eval_output.json",
                    eval_artifact.to_dict(),
                    base_dir=settings.runs_dir / "artifacts",
                )
            )
        except Exception as artifact_err:
            pack.errors.append(f"Artifact persistence failed: {artifact_err}")

        run_context = {
            "company": jd.company,
            "role": jd.role,
            "jd_hash": jd.jd_hash,
            "resume_base": pack.resume_base,
            "fit_score": fit_score_percent,
            "fit_score_details": fit_score_details,
            "pdf_path": str(pack.pdf_path) if pack.pdf_path else None,
            "drive_link": pack.drive_link,
            "drive_uploads": pack.drive_uploads,
            "application_context_id": pack.application_context_id,
            "skip_upload": skip_upload,
            "skip_calendar": skip_calendar,
            "input_mode": input_mode,
            "selected_collateral": pack.selected_collateral,
            "generated_collateral": pack.generated_collateral,
            "collateral_generation_status": pack.collateral_generation_status,
            "collateral_generation_reason": pack.collateral_generation_reason,
            "collateral_files": pack.collateral_files,
            "error_count": len(pack.errors),
            "artifact_paths": artifact_paths,
            "single_page_status": single_page_status,
            "compile_outcome": compile_outcome,
        }
        pack.run_id = log_run(
            "inbox",
            eval_results,
            run_id=run_id,
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
