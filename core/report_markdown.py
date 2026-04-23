"""Render reviewer-facing markdown reports for application pipeline runs."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _line_items(items: list[str]) -> str:
    if not items:
        return "- None"
    return "\n".join(f"- {item}" for item in items)


def _safe_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def render_application_report(*, pack: Any, ctx: Any) -> str:
    """Build the A-F markdown report from pipeline state."""
    jd = pack.jd
    mutation_summary = dict(getattr(ctx, "mutation_summary", {}) or {})
    mutations = mutation_summary.get("mutations", []) or []
    mutation_types = mutation_summary.get("mutation_types", {}) or {}
    truthfulness = mutation_summary.get("truthfulness", {}) or {}

    changes_made: list[str] = []
    for mutation in mutations:
        mutation_type = _safe_text(mutation.get("type") or "REWRITE")
        original = _safe_text(mutation.get("original"))
        replacement = _safe_text(mutation.get("replacement"))
        if not original:
            continue
        snippet_original = original[:140]
        snippet_replacement = replacement[:140] if replacement else "[removed]"
        changes_made.append(
            f"{mutation_type}: `{snippet_original}` -> `{snippet_replacement}`"
        )

    strengths = []
    gaps = []
    fit_details = dict(getattr(ctx, "fit_score_details", {}) or {})
    for key in ("matched_tags", "matched_keywords"):
        values = fit_details.get(key)
        if isinstance(values, list):
            strengths.extend(str(v) for v in values if str(v).strip())
    for key in ("missing_tags", "gaps"):
        values = fit_details.get(key)
        if isinstance(values, list):
            gaps.extend(str(v) for v in values if str(v).strip())

    if not strengths and isinstance(jd.skills, list):
        strengths = [str(skill) for skill in jd.skills[:8] if str(skill).strip()]

    collateral_lines = []
    for key in ("email", "linkedin", "referral"):
        status = "generated" if key in (pack.generated_collateral or []) else "not_generated"
        path_value = (pack.collateral_files or {}).get(key)
        if path_value:
            status = f"{status} ({path_value})"
        collateral_lines.append(f"{key}: {status}")

    compile_lines = [
        f"compile_outcome: {_safe_text(getattr(ctx, 'compile_outcome', None) or 'unknown')}",
        f"single_page_status: {_safe_text(getattr(ctx, 'single_page_status', None) or 'unknown')}",
        f"compile_rollback_used: {bool(getattr(ctx, 'compile_rollback_used', False))}",
        f"pdf_path: {_safe_text(pack.pdf_path) or 'not_generated'}",
    ]

    if pack.drive_uploads:
        folder_path = _safe_text((pack.drive_uploads.get("folder") or {}).get("path"))
        if folder_path:
            compile_lines.append(f"drive_folder: {folder_path}")
        if pack.drive_link:
            compile_lines.append(f"drive_resume_link: {pack.drive_link}")
    else:
        compile_lines.append("drive_folder: pending_or_skipped")

    mutation_types_text = ", ".join(f"{k}={v}" for k, v in sorted(mutation_types.items()))
    if not mutation_types_text:
        mutation_types_text = "none"
    reverted = int(truthfulness.get("reverted_mutations", 0) or 0)

    lines = [
        "# Application Report",
        "",
        "## Metadata",
        f"- run_id: {_safe_text(pack.run_id) or 'pending'}",
        f"- created_at: {_now_iso()}",
        f"- company: {_safe_text(jd.company)}",
        f"- role: {_safe_text(jd.role)}",
        f"- jd_hash: {_safe_text(jd.jd_hash)}",
        f"- input_mode: {_safe_text(getattr(ctx, 'input_mode', 'text'))}",
        f"- fit_score: {int(round(float(getattr(ctx, 'fit_score', 0.0) * 100)))}",
        "",
        "## A) Role Summary",
        _line_items(
            [
                f"Company: {_safe_text(jd.company)}",
                f"Role: {_safe_text(jd.role)}",
                f"Location: {_safe_text(jd.location) or 'not_specified'}",
                f"Experience required: {_safe_text(jd.experience_required) or 'not_specified'}",
                f"Key skills: {', '.join(str(s) for s in (jd.skills or []) if str(s).strip()) or 'not_specified'}",
            ]
        ),
        "",
        "## B) Resume Base Selection",
        _line_items(
            [
                f"Selected base resume: {_safe_text(pack.resume_base)}",
                f"Selection details: {fit_details if fit_details else 'not_available'}",
                f"Fit score details: {fit_details if fit_details else 'not_available'}",
            ]
        ),
        "",
        "## C) Resume Changes Made",
        _line_items(
            [
                f"Mutation count: {len(mutations)}",
                f"Mutation types: {mutation_types_text}",
                f"Truthfulness reverted mutations: {reverted}",
            ]
        ),
        "",
        _line_items(changes_made),
        "",
        "## D) Match Analysis",
        _line_items([f"Strengths: {', '.join(strengths) if strengths else 'none'}"]),
        "",
        _line_items([f"Gaps: {', '.join(gaps) if gaps else 'none'}"]),
        "",
        "## E) Generated Collateral",
        _line_items(collateral_lines),
        "",
        "## F) Execution Summary",
        _line_items(compile_lines + [f"errors: {len(pack.errors or [])}"]),
    ]
    return "\n".join(lines).strip() + "\n"
