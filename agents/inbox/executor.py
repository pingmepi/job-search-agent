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
from collections import Counter
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

# Module-level imports for patchability (integration tests monkeypatch these)
from agents.inbox.jd import extract_jd_with_usage, get_cached_jd
from agents.inbox.planner import (
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
    ToolPlan,
    ToolStep,
)
from agents.inbox.resume import (
    apply_mutations,
    compile_latex,
    extract_bullet_occurrences,
    find_blank_bullets,
    get_pdf_page_count,
    parse_editable_regions,
    replace_bullet_at,
    select_base_resume_with_details,
)
from core.feedback import (
    TASK_TYPE_INBOX_APPLY,
    classify_error_types,
    derive_task_outcome,
    unique_in_order,
)
from core.json_utils import extract_first_json_object as _extract_first_json_object
from core.prompts import load_prompt

if TYPE_CHECKING:
    from agents.inbox.agent import ApplicationPack

logger = logging.getLogger(__name__)
_BLANK_BULLET_RECOVERY_SYSTEM = """
You repair one blank bullet in a resume.

Return JSON with exactly:
{
  "replacement": "one non-empty bullet line without the \\item prefix"
}

Rules:
- Ground the text only in the provided original bullet, same-role context, and JD context.
- Do not invent new companies, roles, metrics, dates, or named entities.
- Keep the bullet concise enough for a one-page resume.
- Output plain bullet text only, not LaTeX markup or a leading \\item.
""".strip()


# ── Step result ───────────────────────────────────────────────────────────────


class OutOfScopeError(Exception):
    """Raised when the JD has no overlap with any candidate resume template.

    Signals the pipeline should abort gracefully and emit task_outcome=out_of_scope
    rather than mutate a misaligned template into a misleading application.
    """


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
    last_step_audit: dict[str, Any] = field(default_factory=dict)  # extra data for audit trail
    prompt_versions: list[str] = field(default_factory=list)
    models_used: list[str] = field(default_factory=list)

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
    user_vetted: bool = False
    step_results: list[StepResult] = field(default_factory=list)
    mutation_summary: dict[str, Any] = field(default_factory=dict)
    out_of_scope: bool = False
    out_of_scope_reason: Optional[str] = None


# ── Helpers ───────────────────────────────────────────────────────────────────


def _is_transient_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    markers = (
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
    return any(m in msg for m in markers)


def _extract_bullets(text: str) -> list[str]:
    bullets: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(r"\item "):
            bullets.append(stripped.replace(r"\item ", "", 1).strip())
    return bullets


def _tokenize_bullet(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", (text or "").lower()))


@lru_cache(maxsize=32)
def _load_profile_json(profile_path: str) -> dict[str, Any]:
    """Load and cache the profile JSON for the lifetime of the process."""
    return json.loads(Path(profile_path).read_text(encoding="utf-8"))


def _load_profile(ctx: "ExecutionContext") -> dict:
    try:
        profile_data = _load_profile_json(str(Path(ctx.settings.profile_path)))
        return dict(profile_data)
    except Exception as exc:
        logger.warning("Failed to load profile: %s — mutations will lack profile context", exc)
        return {}


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


def _sanitize_mutations(raw: list[dict]) -> list[dict]:
    """Drop mutations where original/replacement are not strings or original is empty."""
    clean = []
    for m in raw:
        orig = m.get("original")
        repl = m.get("replacement")
        if not isinstance(orig, str) or not isinstance(repl, str):
            logger.warning("Dropping invalid mutation (original=%r, replacement=%r)", orig, repl)
            continue
        if not orig:
            logger.warning("Dropping mutation with empty original string")
            continue
        clean.append(m)
    return clean


def _record_prompt_version(ctx: "ExecutionContext", name: str, version: int) -> None:
    ctx.prompt_versions.append(f"{name}:v{version}")


def _record_inline_prompt(ctx: "ExecutionContext", label: str) -> None:
    ctx.prompt_versions.append(label)


def _record_model(ctx: "ExecutionContext", model: str | None) -> None:
    if model:
        ctx.models_used.append(model)


def _accumulate_llm_usage(
    ctx: "ExecutionContext",
    *,
    key: str,
    response: Any,
    generation_label: str,
) -> None:
    ctx.total_tokens += int(getattr(response, "total_tokens", 0) or 0)
    _record_model(ctx, getattr(response, "model", None))
    generation_id = getattr(response, "generation_id", None)
    if generation_id:
        ctx.generation_ids.append((generation_label, generation_id))

    existing = ctx.llm_usage_breakdown.get(
        key,
        {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "cost_estimate": 0.0,
        },
    )
    existing["prompt_tokens"] += int(getattr(response, "prompt_tokens", 0) or 0)
    existing["completion_tokens"] += int(getattr(response, "completion_tokens", 0) or 0)
    existing["total_tokens"] += int(getattr(response, "total_tokens", 0) or 0)
    existing["cost_estimate"] += float(getattr(response, "cost_estimate", 0.0) or 0.0)
    ctx.llm_usage_breakdown[key] = existing


def _load_relevant_bullet_bank_values(ctx: "ExecutionContext", jd: Any) -> list[str]:
    from agents.inbox.bullet_relevance import select_relevant_bullets

    bullet_bank_raw = json.loads(ctx.settings.bullet_bank_path.read_text(encoding="utf-8"))
    relevant_bullets = select_relevant_bullets(
        bullet_bank_raw,
        jd.skills,
        jd.description,
        top_n=12,
    )
    return [b["bullet"] for b in relevant_bullets if isinstance(b, dict) and b.get("bullet")]


def _select_swap_bullet(
    *,
    original_bullet: str,
    current_tex: str,
    bullet_bank_values: list[str],
) -> Optional[str]:
    current_normalized = {
        re.sub(r"\s+", " ", bullet).strip().lower() for bullet in _extract_bullets(current_tex)
    }
    original_tokens = _tokenize_bullet(original_bullet)
    best_candidate: Optional[str] = None
    best_score = -1.0

    for candidate in bullet_bank_values:
        normalized = re.sub(r"\s+", " ", candidate).strip().lower()
        if not normalized or normalized in current_normalized:
            continue
        candidate_tokens = _tokenize_bullet(candidate)
        if original_tokens:
            score = len(original_tokens & candidate_tokens) / len(original_tokens)
        else:
            score = 0.0
        if score > best_score or (
            score == best_score and best_candidate is not None and len(candidate) < len(best_candidate)
        ):
            best_candidate = candidate
            best_score = score

    return best_candidate


def _recover_blank_bullets(
    *,
    tex: str,
    original_tex: str,
    jd: Any,
    bullet_bank_values: list[str],
    ctx: "ExecutionContext",
    pack: "ApplicationPack",
    stage_label: str,
) -> tuple[str, dict[str, Any]]:
    stats: dict[str, Any] = {
        "blank_items_detected": 0,
        "blank_items_recovered": 0,
        "blank_items_restored": 0,
        "recovery_passes_used": 0,
        "recovery_strategy_counts": {"regen": 0, "swap": 0, "rewire": 0},
        "remaining_blank_items": 0,
    }

    detected = find_blank_bullets(tex)
    stats["blank_items_detected"] = len(detected)
    if not detected:
        return tex, stats

    _record_inline_prompt(ctx, "blank_bullet_recovery:inline_prompt:v1")
    original_map = {
        (occ.region_index, occ.bullet_index): occ for occ in extract_bullet_occurrences(original_tex)
    }

    for pass_no in range(1, 3):
        blanks = find_blank_bullets(tex)
        if not blanks:
            break
        stats["recovery_passes_used"] = pass_no

        current_occurrences = {
            (occ.region_index, occ.bullet_index): occ for occ in extract_bullet_occurrences(tex)
        }
        for blank in blanks:
            key = (blank.region_index, blank.bullet_index)
            original_occ = original_map.get(key)
            current_occ = current_occurrences.get(key)
            if current_occ is None:
                continue

            original_bullet = (original_occ.content if original_occ else "").strip()
            role_context = [
                occ.content
                for occ in current_occurrences.values()
                if occ.region_index == blank.region_index and occ.content.strip()
            ]

            replacement = ""
            if original_bullet:
                recovery_user = (
                    f"JD context:\n{jd.company} | {jd.role}\n"
                    f"Skills: {', '.join(s for s in jd.skills if s)}\n"
                    f"Description: {jd.description}\n\n"
                    f"Original bullet:\n{original_bullet}\n\n"
                    f"Other bullets in the same role:\n"
                    + "\n".join(f"- {line}" for line in role_context[:5])
                )
                try:
                    recovery_data, recovery_response = _chat_json_with_retry(
                        system=_BLANK_BULLET_RECOVERY_SYSTEM,
                        user_msg=recovery_user,
                        step_name="Blank bullet recovery",
                        max_attempts=2,
                    )
                    _accumulate_llm_usage(
                        ctx,
                        key="blank_bullet_recovery",
                        response=recovery_response,
                        generation_label="blank_bullet_recovery",
                    )
                    replacement = str(recovery_data.get("replacement") or "").strip()
                except Exception as exc:
                    pack.errors.append(f"{stage_label} blank bullet regen failed: {exc}")

            if replacement:
                tex = replace_bullet_at(
                    tex,
                    region_index=blank.region_index,
                    bullet_index=blank.bullet_index,
                    replacement=replacement,
                )
                stats["blank_items_recovered"] += 1
                stats["recovery_strategy_counts"]["regen"] += 1
                continue

            swap_candidate = _select_swap_bullet(
                original_bullet=original_bullet,
                current_tex=tex,
                bullet_bank_values=bullet_bank_values,
            )
            if swap_candidate:
                tex = replace_bullet_at(
                    tex,
                    region_index=blank.region_index,
                    bullet_index=blank.bullet_index,
                    replacement=swap_candidate,
                )
                stats["blank_items_recovered"] += 1
                stats["recovery_strategy_counts"]["swap"] += 1
                continue

            if original_bullet:
                tex = replace_bullet_at(
                    tex,
                    region_index=blank.region_index,
                    bullet_index=blank.bullet_index,
                    replacement=original_bullet,
                )
                stats["blank_items_recovered"] += 1
                stats["blank_items_restored"] += 1
                stats["recovery_strategy_counts"]["rewire"] += 1

    remaining = find_blank_bullets(tex)
    stats["remaining_blank_items"] = len(remaining)
    return tex, stats


def _ensure_markdown_report(pack: "ApplicationPack", ctx: ExecutionContext) -> Optional[Path]:
    """Write a structured A-F markdown report into the application artifacts directory."""
    if not pack.output_dir:
        return None
    report_path = pack.output_dir / "application_report.md"
    if report_path.exists():
        pack.report_md_path = report_path
        return report_path
    try:
        from core.report_markdown import render_application_report

        report_text = render_application_report(pack=pack, ctx=ctx)
        report_path.write_text(report_text, encoding="utf-8")
        pack.report_md_path = report_path
        return report_path
    except Exception as report_err:
        pack.errors.append(f"Markdown report generation failed: {report_err}")
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
        try:
            parsed = json.loads(extracted)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
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
    _record_inline_prompt(ctx, "ocr_cleanup:inline_prompt:v1")
    _record_model(ctx, usage.get("model"))
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
    _record_prompt_version(ctx, "jd_extract", 1)
    _record_model(ctx, usage.get("model"))
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
    from agents.inbox.resume import load_skill_index

    skill_index = load_skill_index(ctx.settings.skill_index_path)
    base_path, fit_score, details = select_base_resume_with_details(
        pack.jd.skills,
        ctx.settings.resumes_dir,
        skill_index=skill_index,
        jd_role=pack.jd.role,
        jd_description=pack.jd.description,
    )
    ctx.base_path = base_path
    ctx.fit_score = fit_score
    ctx.fit_score_details = details
    ctx.fit_score_percent = int(round(fit_score * 100))
    pack.resume_base = base_path.name
    logger.info("Selected resume: %s", base_path.name)

    # Min-fit-score gate: a near-zero signal across all templates means we have
    # no basis to tailor a resume. Mark out_of_scope and abort the pipeline
    # rather than silently picking by lex tie-break and producing a misaligned
    # application.
    #
    # Two thresholds:
    #   * skills-mode (real JD skills): zero overlap is the trigger.
    #   * fallback-mode (jd.skills empty → tokenized role + description): a
    #     single generic token ("the", a brand name) can yield a tiny positive
    #     score, so we require at least 15% of the fallback tokens to match
    #     before treating the JD as in-scope. The fallback ceiling is 0.5 in
    #     compute_keyword_overlap, so 0.075 == 15% of the cap.
    fallback_used = bool(details.get("fallback_signal_used"))
    FALLBACK_MIN_SCORE = 0.075
    out_of_scope = fit_score <= 0.0 or (fallback_used and fit_score < FALLBACK_MIN_SCORE)
    if out_of_scope:
        mode = "fallback" if fallback_used else "skills"
        reason = (
            f"out_of_scope: weak fit score ({fit_score:.3f}, mode={mode}) across all "
            f"{details.get('candidate_count', 0)} templates for role={pack.jd.role!r} "
            f"(skills={len(pack.jd.skills)}). "
            f"Insufficient JD signal — aborting before mutation to avoid persona drift."
        )
        logger.warning(reason)
        ctx.out_of_scope = True
        ctx.out_of_scope_reason = reason
        pack.errors.append(reason)
        raise OutOfScopeError(reason)
    return pack


def _handle_resume_mutate(
    step: ToolStep,
    pack: "ApplicationPack",
    ctx: ExecutionContext,
) -> "ApplicationPack":
    from agents.inbox.bullet_relevance import select_relevant_bullets
    from evals.hard import check_forbidden_claims_per_bullet

    assert ctx.base_path is not None
    original_tex = ctx.base_path.read_text(encoding="utf-8")
    ctx.original_tex = original_tex
    jd = pack.jd

    regions = parse_editable_regions(original_tex)
    if not regions:
        logger.error(
            "No editable regions (%%BEGIN_EDITABLE / %%END_EDITABLE markers) found in %s — "
            "mutation skipped and the base resume will be delivered unchanged. "
            "Add markers around summary/bullets/product descriptions.",
            ctx.base_path.name,
        )
        pack.errors.append(
            f"No editable regions in {ctx.base_path.name}; resume was NOT tailored "
            "(base delivered as-is). Missing %%BEGIN_EDITABLE markers."
        )
        ctx.last_step_audit = {
            "mutations_count": 0,
            "mutations": [],
            "skipped_reason": "no_editable_regions",
            "base_resume": ctx.base_path.name,
        }
        pack.mutated_tex = original_tex
        return pack

    editable_content = "\n".join(r.content for r in regions)

    bullet_bank_raw = json.loads(ctx.settings.bullet_bank_path.read_text(encoding="utf-8"))
    relevant_bullets = select_relevant_bullets(
        bullet_bank_raw,
        jd.skills,
        jd.description,
        top_n=12,
    )
    bullet_bank_values = [b["bullet"] for b in relevant_bullets if isinstance(b, dict) and "bullet" in b]

    bullet_bank_formatted = "\n".join(
        f"[{b.get('id', '?')}] (tags: {', '.join(b.get('tags', []))}) {b.get('bullet', '')}"
        for b in relevant_bullets
    )

    profile = _load_profile(ctx)
    allowed_tools = profile.get("allowed_tools", [])
    positioning = profile.get("positioning", {})
    profile_context = (
        f"Candidate positioning:\n{json.dumps(positioning, indent=2)}\n\n"
        f"Allowed tools: {', '.join(allowed_tools)}"
    )

    current_bullet_count = len(_extract_bullets(original_tex))

    _record_prompt_version(ctx, "resume_mutate", 3)
    system = load_prompt("resume_mutate", version=3)
    user_msg = (
        f"JD:\n{json.dumps({'company': jd.company, 'role': jd.role, 'skills': jd.skills, 'description': jd.description})}\n\n"
        f"Current editable bullets:\n{editable_content}\n\n"
        f"Current bullet count: {current_bullet_count}. "
        f"Do NOT exceed {current_bullet_count} total bullets — the resume must fit on 1 page.\n\n"
        f"Relevant bullet bank entries:\n{bullet_bank_formatted}\n\n"
        f"Profile context:\n{profile_context}"
    )

    mutations_data, response = _chat_json_with_retry(
        system=system,
        user_msg=user_msg,
        step_name="Resume mutation",
        max_attempts=step.max_attempts,
    )
    _accumulate_llm_usage(
        ctx,
        key="resume_mutation",
        response=response,
        generation_label="resume_mutation",
    )

    mutations = _sanitize_mutations(mutations_data.get("mutations", []))
    mutated_tex = apply_mutations(original_tex, mutations)

    mutation_types = dict(Counter(m.get("type", "REWRITE") for m in mutations))
    audit_blob = {
        "raw_llm_response": response.text[:5000] if hasattr(response, "text") else None,
        "mutations_count": len(mutations),
        "mutation_types": mutation_types,
        "mutations": mutations,
        "bank_bullets_sent": len(relevant_bullets),
        "bank_bullets_total": len(bullet_bank_raw),
    }
    ctx.last_step_audit = dict(audit_blob)
    ctx.mutation_summary = dict(audit_blob)

    original_bullets = _extract_bullets(original_tex)
    mutated_bullets = _extract_bullets(mutated_tex)
    jd_text = f"{jd.company} {jd.role} {jd.description} {' '.join(s for s in jd.skills if s)}"
    profile_text = json.dumps(positioning)

    per_bullet = check_forbidden_claims_per_bullet(
        original_bullets,
        mutated_bullets,
        bullet_bank_values,
        jd_text=jd_text,
        allowed_tools=allowed_tools,
        profile_text=profile_text,
    )
    flagged = [r for r in per_bullet if r["flagged"]]

    if flagged:
        flagged_texts = {r["bullet"] for r in flagged}
        clean_mutations = [
            m for m in mutations if (m.get("replacement") or "") not in flagged_texts
        ]

        reverted_count = len(mutations) - len(clean_mutations)
        if reverted_count > 0:
            ctx.truthfulness_fallback_used = True
            logger.warning(
                "Truthfulness safeguard: %d/%d mutations reverted (flagged bullets: %s)",
                reverted_count,
                len(mutations),
                "; ".join(f"{r['bullet'][:50]}... [{', '.join(r['reasons'])}]" for r in flagged),
            )
            pack.errors.append(
                f"Truthfulness safeguard reverted {reverted_count}/{len(mutations)} mutations "
                f"({len(flagged)} bullets had fabricated claims)."
            )
            mutated_tex = apply_mutations(original_tex, clean_mutations)

        truthfulness = {
            "per_bullet_results": per_bullet,
            "flagged_count": len(flagged),
            "reverted_mutations": reverted_count,
            "kept_mutations": len(clean_mutations),
        }
        ctx.last_step_audit["truthfulness"] = truthfulness
        ctx.mutation_summary["truthfulness"] = truthfulness

    mutated_tex, bullet_quality = _recover_blank_bullets(
        tex=mutated_tex,
        original_tex=original_tex,
        jd=jd,
        bullet_bank_values=bullet_bank_values,
        ctx=ctx,
        pack=pack,
        stage_label="resume_mutation",
    )
    if bullet_quality["blank_items_detected"]:
        ctx.last_step_audit["bullet_quality"] = bullet_quality
        ctx.mutation_summary["bullet_quality"] = bullet_quality

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
    bullet_bank_values = _load_relevant_bullet_bank_values(ctx, jd)

    def _compile_and_persist(tex_content: str, suffix: str = "") -> Path:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_tex = Path(tmp_dir) / base_path.name
            tmp_tex.write_text(tex_content, encoding="utf-8")
            try:
                compiled = compile_latex(tmp_tex, Path(tmp_dir))
            except Exception:
                # Persist the failing tex so post-mortem is possible —
                # tempdir gets wiped on exit otherwise.
                failing_tex = app_output_dir / f"{base_path.stem}{suffix}_FAILED.tex"
                failing_tex.write_text(tex_content, encoding="utf-8")
                # Also dump a unified diff against the base into pack.errors so
                # the offending string surfaces in Telegram / db logs without
                # needing shell access to the (ephemeral) container FS.
                try:
                    import difflib

                    base_text = base_path.read_text(encoding="utf-8")
                    diff_lines = list(
                        difflib.unified_diff(
                            base_text.splitlines(),
                            tex_content.splitlines(),
                            fromfile="base.tex",
                            tofile=f"failing{suffix}.tex",
                            n=1,
                            lineterm="",
                        )
                    )
                    if diff_lines:
                        # Truncate to keep error_text manageable.
                        diff_blob = "\n".join(diff_lines[:60])
                        if len(diff_lines) > 60:
                            diff_blob += f"\n... ({len(diff_lines) - 60} more diff lines)"
                        pack.errors.append(
                            f"Failing tex diff vs base (compile {suffix or 'mutated'}):\n{diff_blob}"
                        )
                except Exception as diff_err:
                    logger.warning("Could not build diff for failing tex: %s", diff_err)
                raise
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

    def _use_committed_master_pdf() -> Optional[Path]:
        """Copy the pre-compiled master PDF as terminal fallback.

        Masters in resumes/ are committed and pre-verified as 1-page, so this
        path guarantees a compliant artifact even when pdflatex is unavailable
        in the runtime environment.
        """
        committed_pdf = base_path.with_suffix(".pdf")
        if not committed_pdf.exists():
            return None
        _cleanup_pdfs(app_output_dir)
        dest = app_output_dir / f"{base_path.stem}_committed.pdf"
        shutil.copy2(committed_pdf, dest)
        return dest

    def _fallback_to_base_resume() -> None:
        try:
            base_tex = base_path.read_text(encoding="utf-8")
            pack.pdf_path = _compile_and_persist(base_tex, "_fallback")
            ctx.compile_rollback_used = True
            fb_pages = _safe_page_count(pack.pdf_path) if enforce else None
            if enforce and fb_pages is not None and fb_pages > 1:
                pack.errors.append(
                    f"Resume exceeds one page ({fb_pages} pages) and base fallback "
                    "also exceeds one page."
                )
                committed = _use_committed_master_pdf()
                if committed is not None:
                    pack.pdf_path = committed
                    ctx.compile_outcome = "fallback_success"
                    ctx.single_page_target_met = True
                    ctx.single_page_status = "committed_master_used"
                    pack.errors.append("Used pre-compiled committed master PDF as terminal fallback.")
                else:
                    pack.pdf_path = None
                    _cleanup_pdfs(app_output_dir)
                    ctx.single_page_status = "failed_multi_page_terminal"
                    ctx.compile_outcome = None
                    pack.errors.append("No committed master PDF available.")
            else:
                ctx.compile_outcome = "fallback_success"
                ctx.single_page_status = "fallback_base_used"
                pack.errors.append("LaTeX compile rollback applied: used base resume artifact.")
        except Exception as fallback_err:
            pack.errors.append(f"LaTeX compile fallback failed: {fallback_err}")
            committed = _use_committed_master_pdf()
            if committed is not None:
                pack.pdf_path = committed
                ctx.compile_outcome = "fallback_success"
                ctx.single_page_target_met = True
                ctx.single_page_status = "committed_master_used"
                pack.errors.append("Used pre-compiled committed master PDF as terminal fallback.")
            else:
                ctx.single_page_status = "fallback_failed"

    enforce = getattr(ctx.settings, "enforce_single_page", True)
    max_condense = getattr(ctx.settings, "max_condense_retries", 2)

    def _run_condense(tex: str, page_count: int, attempt: int = 1) -> Optional[str]:
        """Call the condense LLM and return condensed TeX, or None on failure."""
        try:
            _record_prompt_version(ctx, "resume_condense", 1)
            condense_system = load_prompt("resume_condense", version=1)
            regions = parse_editable_regions(tex)
            if not regions:
                return None
            editable_content = "\n".join(r.content for r in regions)
            bullet_count = len(_extract_bullets(tex))
            condense_user = (
                f"JD context: {jd.company} — {jd.role}\n"
                f"Skills: {', '.join(s for s in jd.skills if s)}\n\n"
                f"Current editable content:\n{editable_content}\n\n"
                f"Current page count: {page_count}\n"
                f"Current bullet count: {bullet_count}\n"
                f"Condense attempt: {attempt} of {max_condense}\n"
                f"{'BE MORE AGGRESSIVE — previous attempt did not reduce enough.' if attempt > 1 else ''}"
            )
            data, response = _chat_json_with_retry(
                system=condense_system,
                user_msg=condense_user,
                step_name="Resume condense",
                max_attempts=2,
            )
            _accumulate_llm_usage(
                ctx,
                key="resume_condense",
                response=response,
                generation_label="resume_condense",
            )
            # Build combined mutation list: rewrites + removals (empty replacement)
            mutations = data.get("mutations", [])
            for removed in data.get("bullets_removed", []):
                mutations.append(
                    {
                        "original": removed.get("original"),
                        "replacement": "",
                    }
                )
            mutations = _sanitize_mutations(mutations)
            condensed_tex = apply_mutations(tex, mutations)
            condensed_tex, bullet_quality = _recover_blank_bullets(
                tex=condensed_tex,
                original_tex=ctx.original_tex or tex,
                jd=jd,
                bullet_bank_values=bullet_bank_values,
                ctx=ctx,
                pack=pack,
                stage_label=f"resume_condense_attempt_{attempt}",
            )
            if bullet_quality["blank_items_detected"]:
                ctx.last_step_audit["bullet_quality"] = bullet_quality
                ctx.mutation_summary["bullet_quality"] = bullet_quality
            if bullet_quality["remaining_blank_items"] > 0:
                pack.errors.append(
                    f"Resume condense attempt {attempt} left "
                    f"{bullet_quality['remaining_blank_items']} blank bullets after recovery."
                )
                return None
            return condensed_tex
        except Exception as exc:
            pack.errors.append(f"Resume condense failed: {exc}")
            logger.warning("Condense LLM call failed: %s", exc)
            return None

    try:
        pack.pdf_path = _compile_and_persist(pack.mutated_tex)

        # Page count check + condense loop
        if pack.pdf_path and pack.pdf_path.exists():
            pages = _safe_page_count(pack.pdf_path)
            if pages is not None and pages <= 1:
                ctx.single_page_target_met = True
                ctx.single_page_status = "met"
                ctx.compile_outcome = "mutated_success"
            elif pages is not None and pages > 1 and enforce:
                # Condense loop
                current_tex = pack.mutated_tex
                condensed_ok = False
                for retry in range(1, max_condense + 1):
                    ctx.condense_retries = retry
                    condensed = _run_condense(current_tex, pages, attempt=retry)
                    if condensed is None:
                        break
                    try:
                        pack.pdf_path = _compile_and_persist(condensed, f"_condense{retry}")
                    except Exception as ce:
                        pack.errors.append(f"Condense recompile {retry} failed: {ce}")
                        break
                    pages = _safe_page_count(pack.pdf_path)
                    if pages is not None and pages <= 1:
                        pack.mutated_tex = condensed
                        ctx.single_page_target_met = True
                        ctx.single_page_status = "met"
                        ctx.compile_outcome = "mutated_success"
                        condensed_ok = True
                        break
                    current_tex = condensed

                if not condensed_ok:
                    # Fall back to base resume
                    logger.warning(
                        "Condense exhausted (%d retries); falling back to base.", max_condense
                    )
                    _fallback_to_base_resume()
            elif pages is None:
                ctx.single_page_status = "unknown"
                ctx.compile_outcome = "mutated_success"
            else:
                # pages > 1 but enforce is off
                ctx.single_page_target_met = False
                ctx.single_page_status = f"accepted_{pages}_pages"
                ctx.compile_outcome = "mutated_success"

    except Exception as e:
        pack.errors.append(f"LaTeX compile failed: {e}")
        _fallback_to_base_resume()

    logger.info(
        "Compile result jd_hash=%s success=%s rollback=%s condense=%d",
        jd.jd_hash,
        bool(pack.pdf_path),
        ctx.compile_rollback_used,
        ctx.condense_retries,
    )
    return pack


def _handle_calendar(
    step: ToolStep,
    pack: "ApplicationPack",
    ctx: ExecutionContext,
) -> "ApplicationPack":
    from integrations.calendar import create_application_events

    apply_id, followup_id = create_application_events(pack.jd.company, pack.jd.role)
    pack.calendar_apply_event_id = apply_id
    pack.calendar_followup_event_id = followup_id
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

    profile = _load_profile(ctx)
    identity = profile.get("identity", {})
    name = identity.get("name", "Karan")
    positioning = profile.get("positioning", {}).get("ai", "Product Manager")
    tool = step.tool
    jd = pack.jd

    if tool == TOOL_DRAFT_EMAIL:
        resp = generate_email_draft(name, positioning, jd.company, jd.role)
        _record_prompt_version(ctx, "draft_email", 1)
        _record_model(ctx, getattr(resp, "model", None))
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
        _record_prompt_version(ctx, "draft_linkedin", 1)
        _record_model(ctx, getattr(resp, "model", None))
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
        _record_prompt_version(ctx, "draft_referral", 1)
        _record_model(ctx, getattr(resp, "model", None))
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


def _derive_candidate_name(ctx: ExecutionContext) -> str:
    """Build 'Last_First' prefix from profile.name, falling back to default."""
    from integrations.drive import DEFAULT_CANDIDATE_NAME

    try:
        profile = _load_profile(ctx)
        full_name = (profile.get("identity", {}).get("name") or "").strip()
        parts = [re.sub(r"[^A-Za-z0-9]+", "", p) for p in full_name.split() if p.strip()]
        parts = [p for p in parts if p]
        if len(parts) >= 2:
            return f"{parts[-1]}_{parts[0]}"
        if parts:
            return parts[0]
    except Exception:
        pass
    return DEFAULT_CANDIDATE_NAME


def _handle_drive_upload(
    step: ToolStep,
    pack: "ApplicationPack",
    ctx: ExecutionContext,
) -> "ApplicationPack":
    from integrations.drive import upload_application_artifacts

    if not pack.pdf_path:
        return pack
    report_path = _ensure_markdown_report(pack, ctx)
    drive_files: dict[str, Path] = {"resume_pdf": pack.pdf_path}
    if report_path:
        drive_files["report_md"] = report_path
    for key, file_path in pack.collateral_files.items():
        if file_path:
            drive_files[key] = Path(file_path)
    pack.drive_uploads = upload_application_artifacts(
        files=drive_files,
        company=pack.jd.company,
        role=pack.jd.role,
        application_context_id=pack.application_context_id or ctx.run_id,
        run_id=ctx.run_id,
        candidate_name=_derive_candidate_name(ctx),
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
        pack.jd.company,
        pack.jd.role,
        pack.jd.jd_hash,
        user_vetted=ctx.user_vetted,
        fit_score=ctx.fit_score_percent,
        resume_used=pack.resume_base,
        drive_link=pack.drive_link,
        calendar_apply_event_id=getattr(pack, "calendar_apply_event_id", None),
        calendar_followup_event_id=getattr(pack, "calendar_followup_event_id", None),
    )
    pack.job_id = job_id
    return pack


def _resolve_costs(pack: "ApplicationPack", ctx: ExecutionContext) -> None:
    """Batch-resolve LLM costs from OpenRouter generation IDs."""
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


def _run_hard_evals(pack: "ApplicationPack", ctx: ExecutionContext) -> tuple[int, int]:
    """Run hard evals (edit scope, forbidden claims). Returns (forbidden_count, violations)."""
    from evals.hard import check_edit_scope, check_forbidden_claims

    forbidden_claims_count = 0
    edit_scope_violations = 0

    if ctx.original_tex and pack.mutated_tex:
        outside_changed = _outside_editable_content_changed(ctx.original_tex, pack.mutated_tex)
        edit_scope_ok = check_edit_scope(
            ctx.original_tex, pack.mutated_tex, outside_changed=outside_changed
        )
        edit_scope_violations = 0 if edit_scope_ok else 1

        original_bullets = _extract_bullets(ctx.original_tex)
        mutated_bullets = _extract_bullets(pack.mutated_tex)
        try:
            bb_raw = json.loads(ctx.settings.bullet_bank_path.read_text(encoding="utf-8"))
            bullet_bank = [b.get("bullet", "") for b in bb_raw if isinstance(b, dict)]
        except Exception:
            bullet_bank = []
        jd = pack.jd
        jd_text = f"{jd.company} {jd.role} {jd.description} {' '.join(s for s in jd.skills if s)}"
        profile = _load_profile(ctx)
        forbidden_claims_count = check_forbidden_claims(
            original_bullets,
            mutated_bullets,
            bullet_bank,
            jd_text=jd_text,
            allowed_tools=profile.get("allowed_tools", []),
            profile_text=json.dumps(profile.get("positioning", {})),
        )

    if ctx.truthfulness_fallback_used and forbidden_claims_count == 0:
        forbidden_claims_count = 1

    return forbidden_claims_count, edit_scope_violations


def _run_soft_evals(
    pack: "ApplicationPack", ctx: ExecutionContext
) -> tuple[Optional[float], Optional[float]]:
    """Run LLM-based soft evals. Returns (resume_relevance, jd_accuracy)."""
    soft_resume_relevance: Optional[float] = None
    soft_jd_accuracy: Optional[float] = None
    try:
        from evals.soft import score_jd_accuracy, score_resume_relevance

        jd = pack.jd
        if pack.mutated_tex:
            soft_resume_relevance = score_resume_relevance(jd.description, pack.mutated_tex)
        soft_jd_accuracy = score_jd_accuracy(
            ctx.plan.raw_text,
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
    return soft_resume_relevance, soft_jd_accuracy


def _persist_artifacts(
    pack: "ApplicationPack", ctx: ExecutionContext, eval_results: dict
) -> dict[str, str]:
    """Write JSON artifacts to disk. Returns artifact path map."""
    from core.artifacts import write_json_artifact
    from core.contracts import (
        build_eval_output_artifact,
        build_job_extraction_artifact,
        build_resume_output_artifact,
    )

    artifact_paths: dict[str, str] = {}
    jd = pack.jd
    task_outcome = derive_task_outcome(
        status="completed",
        eval_results=eval_results,
        errors=pack.errors,
        out_of_scope=ctx.out_of_scope,
    )
    error_types = classify_error_types(pack.errors)
    try:
        job_artifact = build_job_extraction_artifact(
            run_id=ctx.run_id,
            input_mode=ctx.input_mode,
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
            run_id=ctx.run_id,
            jd_hash=jd.jd_hash,
            resume_base=pack.resume_base,
            fit_score=ctx.fit_score_percent,
            compile_success=bool(pack.pdf_path and pack.pdf_path.exists()),
            compile_rollback_used=ctx.compile_rollback_used,
            condense_retries=ctx.condense_retries,
            pdf_path=str(pack.pdf_path) if pack.pdf_path else None,
            output_dir=str(pack.output_dir) if pack.output_dir else None,
            report_md_path=str(pack.report_md_path) if pack.report_md_path else None,
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
            mutation_summary=ctx.mutation_summary,
        )
        eval_artifact = build_eval_output_artifact(
            run_id=ctx.run_id,
            jd_hash=jd.jd_hash,
            task_type=TASK_TYPE_INBOX_APPLY,
            task_outcome=task_outcome,
            error_types=error_types,
            prompt_versions=unique_in_order(ctx.prompt_versions),
            models_used=unique_in_order(ctx.models_used),
            eval_results=eval_results,
        )
        base_dir = ctx.settings.runs_dir / "artifacts"
        artifact_paths["job_extraction"] = str(
            write_json_artifact(
                ctx.run_id, "job_extraction.json", job_artifact.to_dict(), base_dir=base_dir
            )
        )
        artifact_paths["resume_output"] = str(
            write_json_artifact(
                ctx.run_id, "resume_output.json", resume_artifact.to_dict(), base_dir=base_dir
            )
        )
        artifact_paths["eval_output"] = str(
            write_json_artifact(
                ctx.run_id, "eval_output.json", eval_artifact.to_dict(), base_dir=base_dir
            )
        )
    except Exception as ae:
        pack.errors.append(f"Artifact persistence failed: {ae}")
    return artifact_paths


def _complete_run_record(
    pack: "ApplicationPack",
    ctx: ExecutionContext,
    eval_results: dict,
    artifact_paths: dict[str, str],
    latency_ms: int,
) -> None:
    """Write the final run record to the database."""
    from evals.logger import log_run

    jd = pack.jd
    run_context = {
        "company": jd.company,
        "role": jd.role,
        "jd_hash": jd.jd_hash,
        "resume_base": pack.resume_base,
        "fit_score": ctx.fit_score_percent,
        "fit_score_details": ctx.fit_score_details,
        "pdf_path": str(pack.pdf_path) if pack.pdf_path else None,
        "report_md_path": str(pack.report_md_path) if pack.report_md_path else None,
        "drive_link": pack.drive_link,
        "drive_uploads": pack.drive_uploads,
        "application_context_id": pack.application_context_id,
        "skip_upload": ctx.plan.skip_upload,
        "skip_calendar": ctx.plan.skip_calendar,
        "input_mode": ctx.input_mode,
        "user_vetted": ctx.user_vetted,
        "selected_collateral": pack.selected_collateral,
        "generated_collateral": pack.generated_collateral,
        "collateral_generation_status": pack.collateral_generation_status,
        "collateral_generation_reason": pack.collateral_generation_reason,
        "collateral_files": pack.collateral_files,
        "error_count": len(pack.errors),
        "artifact_paths": artifact_paths,
        "single_page_status": ctx.single_page_status,
        "compile_outcome": ctx.compile_outcome,
        "mutation_summary": ctx.mutation_summary,
    }
    task_outcome = derive_task_outcome(
        status="completed",
        eval_results=eval_results,
        errors=pack.errors,
        out_of_scope=ctx.out_of_scope,
    )
    run_context["out_of_scope"] = ctx.out_of_scope
    if ctx.out_of_scope_reason:
        run_context["out_of_scope_reason"] = ctx.out_of_scope_reason
    error_types = classify_error_types(pack.errors)
    pack.run_id = log_run(
        "inbox",
        eval_results,
        run_id=ctx.run_id,
        job_id=pack.job_id,
        tokens_used=ctx.total_tokens,
        cost_estimate=ctx.total_cost,
        latency_ms=latency_ms,
        input_mode=ctx.input_mode,
        skip_upload=ctx.plan.skip_upload,
        skip_calendar=ctx.plan.skip_calendar,
        errors=pack.errors,
        task_type=TASK_TYPE_INBOX_APPLY,
        task_outcome=task_outcome,
        error_types=error_types,
        prompt_versions=unique_in_order(ctx.prompt_versions),
        models_used=unique_in_order(ctx.models_used),
        context=run_context,
    )


def _handle_eval_log(
    step: ToolStep,
    pack: "ApplicationPack",
    ctx: ExecutionContext,
) -> "ApplicationPack":
    from evals.hard import check_cost, check_draft_length, check_jd_schema

    jd = pack.jd
    latency_ms = int((time.time() - ctx.start_time) * 1000)
    _ensure_markdown_report(pack, ctx)

    _resolve_costs(pack, ctx)
    forbidden_claims_count, edit_scope_violations = _run_hard_evals(pack, ctx)
    soft_resume_relevance, soft_jd_accuracy = _run_soft_evals(pack, ctx)

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
        "report_md_path": str(pack.report_md_path) if pack.report_md_path else None,
        "mutation_summary": ctx.mutation_summary,
        "llm_total_tokens": ctx.total_tokens,
        "llm_total_cost": ctx.total_cost,
        "llm_usage_breakdown": ctx.llm_usage_breakdown,
        "jd_schema_valid": check_jd_schema(
            {
                "company": jd.company,
                "role": jd.role,
                "location": jd.location,
                "experience_required": jd.experience_required,
                "skills": jd.skills,
                "description": jd.description,
            }
        ),
        "soft_resume_relevance": soft_resume_relevance,
        "soft_jd_accuracy": soft_jd_accuracy,
    }
    pack.eval_results = eval_results

    # Soft-eval hard floor: if the LLM judge scored resume relevance below the
    # quality threshold, append an error so derive_task_outcome demotes the
    # outcome from success → partial. Prevents low-quality artifacts from
    # silently shipping (see run-144b1afaef4a where soft=0.0 was informational).
    SOFT_RELEVANCE_FLOOR = 0.4
    if (
        soft_resume_relevance is not None
        and soft_resume_relevance < SOFT_RELEVANCE_FLOOR
        and not ctx.out_of_scope
    ):
        msg = (
            f"soft_eval_below_floor: resume_relevance={soft_resume_relevance:.2f} "
            f"< {SOFT_RELEVANCE_FLOOR} — artifact may be misaligned with JD"
        )
        logger.warning(msg)
        pack.errors.append(msg)

    artifact_paths = _persist_artifacts(pack, ctx, eval_results)
    _complete_run_record(pack, ctx, eval_results, artifact_paths, latency_ms)

    logger.info(
        "Run logged run_id=%s jd_hash=%s pdf_path=%s errors=%d",
        pack.run_id,
        jd.jd_hash,
        str(pack.pdf_path) if pack.pdf_path else None,
        len(pack.errors),
    )
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


def _eval_log_completed(ctx: ExecutionContext) -> bool:
    """Return True if the eval_log step ran successfully.

    step_results is appended in lockstep with plan.steps until the dispatch
    loop breaks, so we can pair indices to look up each result's tool.
    """
    for i, result in enumerate(ctx.step_results):
        if i >= len(ctx.plan.steps):
            break
        if result.success and ctx.plan.steps[i].tool == TOOL_EVAL_LOG:
            return True
    return False


def _log_out_of_scope_run(pack: "ApplicationPack", ctx: ExecutionContext) -> None:
    """Persist a minimal run record when OutOfScopeError aborted the pipeline.

    Without this, task_outcome=out_of_scope never reaches the DB (the eval_log
    step is unreachable after a fatal-step abort). The regression runner and
    Telegram pack.run_id lookups depend on the row existing.
    """
    from evals.logger import log_run

    latency_ms = int((time.time() - ctx.start_time) * 1000)
    jd = pack.jd
    eval_results: dict[str, Any] = {
        "compile_success": False,
        "out_of_scope": True,
        "fit_score": ctx.fit_score_percent,
        "fit_score_details": ctx.fit_score_details,
        "llm_total_tokens": ctx.total_tokens,
        "llm_total_cost": ctx.total_cost,
        "llm_usage_breakdown": ctx.llm_usage_breakdown,
    }
    pack.eval_results = eval_results
    run_context: dict[str, Any] = {
        "company": getattr(jd, "company", None),
        "role": getattr(jd, "role", None),
        "jd_hash": getattr(jd, "jd_hash", None),
        "resume_base": pack.resume_base,
        "fit_score": ctx.fit_score_percent,
        "fit_score_details": ctx.fit_score_details,
        "input_mode": ctx.input_mode,
        "user_vetted": ctx.user_vetted,
        "out_of_scope": True,
        "out_of_scope_reason": ctx.out_of_scope_reason,
        "error_count": len(pack.errors),
        "aborted_step": next((r.step_name for r in ctx.step_results if not r.success), None),
    }
    error_types = classify_error_types(pack.errors)
    try:
        pack.run_id = log_run(
            "inbox",
            eval_results,
            run_id=ctx.run_id,
            job_id=pack.job_id,
            tokens_used=ctx.total_tokens,
            cost_estimate=ctx.total_cost,
            latency_ms=latency_ms,
            input_mode=ctx.input_mode,
            skip_upload=ctx.plan.skip_upload,
            skip_calendar=ctx.plan.skip_calendar,
            errors=pack.errors,
            task_type=TASK_TYPE_INBOX_APPLY,
            task_outcome=derive_task_outcome(
                status="completed",
                eval_results=eval_results,
                errors=pack.errors,
                out_of_scope=True,
            ),
            error_types=error_types,
            prompt_versions=unique_in_order(ctx.prompt_versions),
            models_used=unique_in_order(ctx.models_used),
            context=run_context,
        )
    except Exception as exc:
        logger.error("Failed to persist out-of-scope run record: %s", exc)


def _build_step_input(
    step: ToolStep, pack: "ApplicationPack", ctx: ExecutionContext
) -> dict[str, Any]:
    """Build a lightweight input snapshot for the audit trail."""
    data: dict[str, Any] = {"tool": step.tool}
    if pack.jd:
        data["company"] = pack.jd.company
        data["role"] = pack.jd.role
        data["jd_hash"] = pack.jd.jd_hash
    if ctx.base_path:
        data["base_resume"] = ctx.base_path.name
    if step.params:
        data["params"] = {k: str(v)[:200] for k, v in step.params.items()}
    return data


def _build_step_output(
    step: ToolStep, pack: "ApplicationPack", ctx: ExecutionContext
) -> dict[str, Any]:
    """Build a lightweight output snapshot for the audit trail."""
    data: dict[str, Any] = {}
    if step.tool == "jd_extract" and pack.jd:
        data["jd_schema"] = {
            "company": pack.jd.company,
            "role": pack.jd.role,
            "skills": pack.jd.skills,
            "location": pack.jd.location,
        }
    elif step.tool == "resume_select":
        data["selected"] = pack.resume_base
        data["fit_score"] = ctx.fit_score_percent
        data["details"] = ctx.fit_score_details
    elif step.tool == "resume_mutate":
        data["mutated_length"] = len(pack.mutated_tex) if pack.mutated_tex else 0
        data["truthfulness_fallback"] = ctx.truthfulness_fallback_used
        if ctx.last_step_audit:
            data.update(ctx.last_step_audit)
            ctx.last_step_audit = {}
    elif step.tool == "compile":
        data["pdf_path"] = str(pack.pdf_path) if pack.pdf_path else None
        data["compile_outcome"] = ctx.compile_outcome
        data["single_page_status"] = ctx.single_page_status
    elif step.tool in ("draft_email", "draft_linkedin", "draft_referral"):
        kind = step.tool.replace("draft_", "")
        draft = getattr(pack, f"{kind}_draft", None)
        data["draft_length"] = len(draft) if draft else 0
    elif step.tool == "eval_log":
        data["run_id"] = pack.run_id
        data["job_id"] = pack.job_id
        data["total_tokens"] = ctx.total_tokens
        data["total_cost"] = ctx.total_cost
    # Include LLM usage if it was updated during this step
    step_usage = ctx.llm_usage_breakdown.get(step.tool) or ctx.llm_usage_breakdown.get(step.name)
    if step_usage:
        data["llm_usage"] = step_usage
    return data


def _run_step_with_retry(
    step: ToolStep,
    pack: "ApplicationPack",
    ctx: ExecutionContext,
) -> StepResult:
    """Execute a single step, retrying transient errors as configured."""
    from core.db import complete_step, insert_step

    handler = _HANDLERS.get(step.tool)
    if handler is None:
        return StepResult(
            step_name=step.name,
            success=False,
            error=f"Unknown tool: {step.tool!r}",
        )

    # Audit: record step start
    step_start = time.time()
    try:
        insert_step(ctx.run_id, step.name, input_data=_build_step_input(step, pack, ctx))
    except Exception:
        logger.debug("Failed to insert audit step for %s (non-fatal)", step.name)

    last_error: Optional[Exception] = None
    for attempt in range(1, step.max_attempts + 1):
        try:
            pack = handler(step, pack, ctx)
            duration_ms = int((time.time() - step_start) * 1000)
            # Audit: record step success
            try:
                complete_step(
                    ctx.run_id,
                    step.name,
                    output_data=_build_step_output(step, pack, ctx),
                    duration_ms=duration_ms,
                )
            except Exception:
                logger.debug("Failed to complete audit step for %s (non-fatal)", step.name)
            return StepResult(step_name=step.name, success=True, attempts=attempt)
        except OutOfScopeError as exc:
            # Out-of-scope is a deterministic decision, not a transient error.
            # Do not retry; let the dispatch loop abort the pipeline.
            last_error = exc
            break
        except Exception as exc:
            last_error = exc
            if step.retry_on_transient and attempt < step.max_attempts and _is_transient_error(exc):
                logger.warning(
                    "Step %s transient error (attempt %d/%d): %s",
                    step.name,
                    attempt,
                    step.max_attempts,
                    exc,
                )
                time.sleep(0.3 * attempt)
                continue
            break

    err_msg = f"{step.name} failed: {last_error}"
    duration_ms = int((time.time() - step_start) * 1000)
    # Audit: record step failure
    try:
        complete_step(ctx.run_id, step.name, error=err_msg, duration_ms=duration_ms)
    except Exception:
        logger.debug("Failed to complete audit step for %s (non-fatal)", step.name)
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
    *,
    user_vetted: bool = False,
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
        user_vetted=user_vetted,
        llm_usage_breakdown={
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

    # If the pipeline aborted on out-of-scope before eval_log ran, write a
    # minimal run record so task_outcome=out_of_scope reaches the DB and the
    # regression runner / Telegram replies can resolve pack.run_id.
    if ctx.out_of_scope and not _eval_log_completed(ctx):
        _log_out_of_scope_run(pack, ctx)

    return pack
